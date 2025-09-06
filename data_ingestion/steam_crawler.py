import os, time, json, requests
import pandas as pd
from typing import List, Dict
from datetime import datetime, timezone

from data_ingestion.mysql import upload_data_to_mysql, upload_data_to_mysql_upsert, game_info_table


URL_ALL    = "https://api.steampowered.com/ISteamApps/GetAppList/v2/"
URL_DETAIL = "https://store.steampowered.com/api/appdetails"
URL_REVIEWS= "https://store.steampowered.com/appreviews/{appid}"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/138.0.0.0 Safari/537.36"}

PAUSE = 0.12
RETRY = 2
CHECKPOINT_EVERY = 100

# --- 輸出 ---
OUTPUT_DIR   = "output"
GAMES_CSV    = os.path.join(OUTPUT_DIR, "steam_games.csv")
GENRES_CSV   = os.path.join(OUTPUT_DIR, "steam_game_genres.csv")
REVIEWS_CSV  = os.path.join(OUTPUT_DIR, "steam_reviews.csv")
CHECKPOINT_FILE = "checkpoint.json"
REVIEWS_CHECKPOINT_FILE = "reviews_checkpoint.json"

# ---------- 小工具 ----------
def ensure_output():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

def append_rows_csv(path: str, rows: List[Dict]):
    """用 pandas 追加寫入（自動判斷 header），避免一次吃爆記憶體。"""
    if not rows: 
        return
    df = pd.DataFrame(rows)
    df['uploaded_at'] = datetime.now(timezone.utc)  # 新增 uploaded_at 欄位，設為現在時間    
    header = not os.path.exists(path)
    df.to_csv(path, mode="a", index=False, header=header, encoding="utf-8-sig")
    upload_data_to_mysql(table_name="game_info", df=df, mode="append")
    print("寫入csv檔")


def load_existing_ids_from_csv(path: str) -> set[int]:
    if not os.path.exists(path):
        return set()
    try:
        s = pd.read_csv(path, usecols=["steam_gameid"])["steam_gameid"].dropna().astype(int)
        return set(s.tolist())
    except Exception:
        return set()

def save_checkpoint(next_index: int, processed: int, found: int):
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump({"next_index": next_index, "processed": processed, "found_game_ids": found, "ts": time.time()}, f)

def load_checkpoint() -> int:
    if not os.path.exists(CHECKPOINT_FILE):
        return 0
    try:
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            return int((json.load(f) or {}).get("next_index", 0))
    except Exception:
        return 0

def save_reviews_checkpoint(next_index: int, processed_games: int):
    with open(REVIEWS_CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump({"next_index": next_index, "processed_games": processed_games, "ts": time.time()}, f)

def load_reviews_checkpoint() -> int:
    if not os.path.exists(REVIEWS_CHECKPOINT_FILE):
        return 0
    try:
        with open(REVIEWS_CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            return int((json.load(f) or {}).get("next_index", 0))
    except Exception:
        return 0

# ---------- 抓資料 ----------
def get_all_apps():
    r = requests.get(URL_ALL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json().get("applist", {}).get("apps", [])

def get_game_info_if_game(appid: int) -> dict | None:
    params = {"appids": str(appid), "l": "tchinese", "cc": "TW"}
    tries = 1 + RETRY
    for _ in range(tries):
        try:
            r = requests.get(URL_DETAIL, params=params, headers=HEADERS, timeout=30)
            if r.status_code != 200:
                time.sleep(0.5); continue
            payload = r.json()
            root = payload.get(str(appid), {})
            if not root.get("success"):
                return None
            info = root.get("data") or {}
            if info.get("type") != "game":
                return None

            developers = info.get("developers") or ([info.get("developer")] if info.get("developer") else [])
            publishers = info.get("publishers") or []

            # 主表 row（扁平）
            game_row = {
                "steam_gameid": info.get("steam_appid"),
                "name": info.get("name"),
                "required_age": info.get("required_age"),
                "is_free": info.get("is_free", False),
                "header_image": info.get("header_image"),
                "supported_languages": info.get("supported_languages"),
                "developers": "|".join(map(str, developers)),
                "publishers": "|".join(map(str, publishers)),
                "price_final_formatted": (info.get("price_overview") or {}).get("final_formatted"),
                "platforms_windows": (info.get("platforms") or {}).get("windows"),
                "platforms_mac":     (info.get("platforms") or {}).get("mac"),
                "platforms_linux":   (info.get("platforms") or {}).get("linux"),
                "release_date": (info.get("release_date") or {}).get("date"),
            }

            # 關聯表 rows（多列）
            genre_rows = []
            for g in (info.get("genres") or []):
                genre_rows.append({
                    "steam_gameid": info.get("steam_appid"),
                    "genre_id": g.get("id"),
                    "genre_desc": g.get("description"),
                })

            return {"game_row": game_row, "genre_rows": genre_rows}

        except requests.RequestException:
            time.sleep(0.5)
    return None

def fetch_reviews_for_app(appid: int, max_pages: int | None = None):
    """回傳一個 app 的評論 rows（分頁逐批 append 到 CSV；不囤大量記憶體）。"""
    cursor = "*"
    pages  = 0
    seen   = set()
    while True:
        params = {
            "json": 1, "filter": "recent", "language": "all",
            "num_per_page": 100, "cursor": cursor
        }
        try:
            r = requests.get(URL_REVIEWS.format(appid=appid), params=params, headers=HEADERS, timeout=30)
            if r.status_code != 200:
                time.sleep(0.5); continue
            data = r.json()
        except (requests.RequestException, ValueError):
            time.sleep(0.5); continue

        reviews = data.get("reviews") or []
        if not reviews:
            break

        rows = []
        for rv in reviews:
            rid = rv.get("recommendationid")
            if not rid or rid in seen:
                continue
            seen.add(rid)
            rows.append({
                "steam_gameid": int(appid),
                "recommendationid": rid,
                "steamid": (rv.get("author") or {}).get("steamid"),
                "playtime_forever_min": (rv.get("author") or {}).get("playtime_forever"),
                "voted_up": rv.get("voted_up"),
                "language": rv.get("language"),
                "review": rv.get("review"),
                "timestamp_created": rv.get("timestamp_created"),
            })

        append_rows_csv(REVIEWS_CSV, rows)

        pages += 1
        nxt = data.get("cursor")
        if not nxt or nxt == cursor:
            break
        if max_pages and pages >= max_pages:
            break
        cursor = nxt
        time.sleep(PAUSE)

# ---------- 主流程 ----------
def main(limit_games: int | None = None, max_apps: int | None = None):
    ensure_output()
    apps = get_all_apps()
    total = len(apps)
    start_idx = load_checkpoint()
    existed_ids = load_existing_ids_from_csv(GAMES_CSV)

    print(f"[games] 總數 {total}，從索引 {start_idx} 續跑；已存在 {len(existed_ids)} 款")

    processed = 0
    found_this_run = 0
    buf_games: list[Dict] = []
    buf_genres: list[Dict] = []

    try:
        for i in range(start_idx, total):
            if max_apps and processed >= max_apps:
                break
            app = apps[i]
            appid = app["appid"]

            info = get_game_info_if_game(appid)
            if info:
                sid = int(info["game_row"].get("steam_gameid") or appid)
                if sid not in existed_ids:
                    buf_games.append(info["game_row"])
                    buf_genres.extend(info["genre_rows"])
                    existed_ids.add(sid)
                    found_this_run += 1

                    if limit_games and found_this_run >= limit_games:
                        append_rows_csv(GAMES_CSV, buf_games); buf_games.clear()
                        append_rows_csv(GENRES_CSV, buf_genres); buf_genres.clear()
                        save_checkpoint(next_index=i+1, processed=processed+1, found=len(existed_ids))
                        print(f"[games] 蒐集到 {found_this_run}/{limit_games}，先收。")
                        break

            processed += 1
            if processed % CHECKPOINT_EVERY == 0:
                append_rows_csv(GAMES_CSV, buf_games); buf_games.clear()
                append_rows_csv(GENRES_CSV, buf_genres); buf_genres.clear()
                save_checkpoint(next_index=i+1, processed=processed, found=len(existed_ids))
                print(f"[games] checkpoint @ {i+1}/{total}，累計 {len(existed_ids)}")

            time.sleep(PAUSE)

    except KeyboardInterrupt:
        print("\n[games] Ctrl+C，先存檢查點…")
        append_rows_csv(GAMES_CSV, buf_games); buf_games.clear()
        append_rows_csv(GENRES_CSV, buf_genres); buf_genres.clear()
        next_i = (i + 1) if 'i' in locals() else start_idx
        save_checkpoint(next_index=next_i, processed=processed, found=len(existed_ids))
        return

    append_rows_csv(GAMES_CSV, buf_games)
    append_rows_csv(GENRES_CSV, buf_genres)
    save_checkpoint(next_index=total, processed=processed, found=len(existed_ids))
    print(f"[games] 完成，總遊戲數：{len(existed_ids)}")
    print(f"  → {GAMES_CSV}")
    print(f"  → {GENRES_CSV}")

def load_game_ids_from_games_csv(limit: int | None = None) -> list[int]:
    ids = sorted(load_existing_ids_from_csv(GAMES_CSV))
    return ids[:limit] if limit else ids

def main_reviews(max_pages_per_app: int | None = None, limit_games: int | None = None):
    ensure_output()
    game_ids = load_game_ids_from_games_csv(limit_games)
    total = len(game_ids)
    start_idx = load_reviews_checkpoint()
    print(f"[reviews] 從索引 {start_idx} 開始，共 {total} 款")

    processed = 0
    try:
        for i in range(start_idx, total):
            appid = game_ids[i]
            fetch_reviews_for_app(appid, max_pages=max_pages_per_app)
            processed += 1
            if processed % CHECKPOINT_EVERY == 0:
                save_reviews_checkpoint(next_index=i+1, processed_games=processed)
                print(f"[reviews] checkpoint @ {i+1}/{total}")
            time.sleep(PAUSE)
    except KeyboardInterrupt:
        print("\n[reviews] Ctrl+C，先存檢查點…")
        next_i = (i + 1) if 'i' in locals() else start_idx
        save_reviews_checkpoint(next_index=next_i, processed_games=processed)
        return

    save_reviews_checkpoint(next_index=total, processed_games=processed)
    print(f"[reviews] 完成 → {REVIEWS_CSV}")

if __name__ == "__main__":
    # 先抓 10 款遊戲；也可以把兩個參數拿掉全跑
    main(limit_games=10, max_apps=10)
    # 每款抓 1 頁評論試跑
    main_reviews(max_pages_per_app=1, limit_games=10)
