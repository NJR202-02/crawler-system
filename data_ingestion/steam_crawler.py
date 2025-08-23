# get_game_ids_streaming_with_names.py
import requests
import time
import json
import os
from typing import Set, Dict, Tuple

URL_ALL = "https://api.steampowered.com/ISteamApps/GetAppList/v2/"
URL_DETAIL = "https://store.steampowered.com/api/appdetails"
URL_REVIEWS = "https://store.steampowered.com/appreviews/{appid}"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
}

PAUSE = 0.12                 # 每顆之間停頓
RETRY = 2                    # 失敗重試次數（不含第一次）
CHECKPOINT_EVERY = 100       # 每處理幾筆就存一次檢查點

CHECKPOINT_FILE = "checkpoint.json"                    # 存「跑到第幾筆」
RESULT_JSONL = "steam_games.jsonl"                     # 每行一筆遊戲資訊
RESULT_SNAPSHOT = "steam_games_snapshot.json"          # 週期性輸出一份陣列快照
REVIEWS_JSONL = "steam_reviews.jsonl"                  # 每行一筆評論
REVIEWS_CHECKPOINT_FILE = "reviews_checkpoint.json"    # 記錄抓到第幾個遊戲



# ---------- 基礎函式 ----------
def get_all_apps():
    # 取得全部 app 清單（每筆含 appid 與 name）。
    resp = requests.get(URL_ALL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json().get("applist", {}).get("apps", [])


def get_game_info_if_game(appid: int) -> dict | None:
    """
    全量 call appdetails（不帶 filters/cc/l）。
    若為 game，回傳只含指定欄位的 dict；否則回 None。
    """
    params = {"appids": str(appid)}
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

            # developers 兼容舊欄位 'developer'
            developers = info.get("developers")
            if not developers:
                dev = info.get("developer")
                developers = [dev] if dev else []

            return {
                "name": info.get("name"),
                "steam_gameid": info.get("steam_appid"),
                "is_free": info.get("is_free", False),
                "supported_languages": info.get("supported_languages"),
                "developers": developers,
                "price_overview": info.get("price_overview"),  # 免費/區不可售可能沒有
                "platforms": info.get("platforms"),
                "genres": info.get("genres") or [],
            }

        except requests.RequestException:
            time.sleep(0.5)
    return None


# 取已存遊戲 ID
def load_game_ids_from_result() -> list[int]:
    ids, _ = load_existing_from_jsonl(RESULT_JSONL)  # 會同時辨識 appid / steam_gameid
    return sorted(ids)


# 逐款抓評論
def fetch_reviews_for_app(appid: int, out_path: str, max_pages: int | None = None):
    """
    依 URL_REVIEWS 參數抓該 app 的所有頁（或到 max_pages），逐行寫 JSONL。
    寫入欄位示例：
      steam_gameid, recommendationid, steamid, playtime_forever_min, voted_up,
      language, review, timestamp_created
    """
    seen: set[str] = set()      # 去重（保險）
    cursor = "*"
    pages = 0

    while True:
        url = URL_REVIEWS.format(appid=appid)
        try:
            params = {                          # ← 補回固定參數
                "json": 1,
                "filter": "recent",
                "language": "all",
                "day_range": 30,
                "num_per_page": 100,
                "cursor": cursor,
            }            
            r = requests.get(url, params=params, headers=HEADERS, timeout=30)
            if r.status_code != 200:
                time.sleep(0.5); continue
            data = r.json()
        except requests.RequestException:
            time.sleep(0.5); continue
        except ValueError:
            time.sleep(0.5); continue

        reviews = data.get("reviews", []) or []
        if not reviews:
            break

        # 逐行落盤（不囤記憶體）
        with open(out_path, "a", encoding="utf-8") as f:
            for rv in reviews:
                rid = rv.get("recommendationid")
                if rid in seen:
                    continue
                seen.add(rid)

                row = {
                    "steam_gameid": int(appid),
                    "recommendationid": rid,
                    "steamid": rv.get("author", {}).get("steamid"),
                    "playtime_forever_min": rv.get("author", {}).get("playtime_forever"),
                    "voted_up": rv.get("voted_up"),
                    "language": rv.get("language"),
                    "review": rv.get("review"),
                    "timestamp_created": rv.get("timestamp_created"),
                }
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()

        pages += 1
        new_cursor = data.get("cursor")
        if not new_cursor or new_cursor == cursor:  # ← 防死循環
            break
        cursor = new_cursor

        if max_pages and pages >= max_pages:
            break
        time.sleep(PAUSE)


# ---------- 檔案/檢查點工具 ----------
def load_checkpoint() -> int:
    # 回傳上次處理到的 index（下一次要從這裡開始）。沒有就回 0。
    if not os.path.exists(CHECKPOINT_FILE):
        return 0
    try:
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            obj = json.load(f)
            return int(obj.get("next_index", 0))
    except Exception:
        return 0


def save_checkpoint(next_index: int, processed: int, found: int):
    obj = {"next_index": next_index, "processed": processed, "found_game_ids": found, "ts": time.time()}
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def load_existing_from_jsonl(path: str) -> Tuple[Set[int], Dict[int, str]]:
    
    # 讀取已經寫過的 jsonl，回傳：
    #   - 已存在的 appid 集合（避免重複）
    #   - 已存在的 {appid: name} 對照（方便重建快照）
    # 相容兩種行格式：
    #   1) 純整數： 570
    #   2) 物件行： {"appid": 570, "name": "Dota 2"}
    
    ids: Set[int] = set()
    id2name: Dict[int, str] = {}
    if not os.path.exists(path):
        return ids, id2name

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                v = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(v, int):
                ids.add(v)
            elif isinstance(v, dict):
                appid = v.get("appid")
                if not isinstance(appid, int):
                    appid = v.get("steam_gameid")      
                if isinstance(appid, int):
                    ids.add(appid)
                    name = v.get("name", "")
                    if name:
                        id2name[appid] = name
    return ids, id2name


def write_snapshot_array(path: str, id2name: Dict[int, str]):
    # 把目前累積的 {appid: name} 寫成陣列 JSON，排序後好讀。
    rows = [{"appid": appid, "name": id2name.get(appid, "")} for appid in sorted(id2name)]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


def append_jsonl(path: str, obj: dict):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        f.flush()


# 評論檢查點
def load_reviews_checkpoint() -> int:
    if not os.path.exists(REVIEWS_CHECKPOINT_FILE):
        return 0
    try:
        with open(REVIEWS_CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            return int((json.load(f) or {}).get("next_index", 0))
    except Exception:
        return 0


def save_reviews_checkpoint(next_index: int, processed_games: int):
    obj = {"next_index": next_index, "processed_games": processed_games, "ts": time.time()}
    with open(REVIEWS_CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


# 主流程：爬取遊戲資訊（可中斷續跑）
def main(limit_games: int | None = None, max_apps: int | None = None):
    print("1) 載入全部 app 清單…")
    apps = get_all_apps()
    total = len(apps)
    print("   總數：", total)

    # 讀上次 checkpoint 與已寫入紀錄
    start_idx = load_checkpoint()
    found_ids, id2name = load_existing_from_jsonl(RESULT_JSONL)
    print(f"2) 從索引 {start_idx} 續跑；已累積遊戲數：{len(found_ids)}")

    processed = 0
    found_this_run = 0
    try:
        for i in range(start_idx, total):
            if max_apps and processed >= max_apps:
                break  # 可選：只掃前 max_apps 個 app（更快）            
            app = apps[i]
            appid = app["appid"]
            name = app.get("name", "")
            info = get_game_info_if_game(appid)

            if info:
                sid = int(info.get("steam_gameid") or appid)
                if sid not in found_ids:               
                    append_jsonl(RESULT_JSONL, info)
                    found_ids.add(sid)
                    id2name[sid] = info.get("name") or name
                    found_this_run += 1
                    
                    if limit_games and found_this_run >= limit_games:
                        # 提前結束前做個小收尾，之後可無縫續跑
                        save_checkpoint(next_index=i+1, processed=processed+1, found=len(found_ids))
                        write_snapshot_array(RESULT_SNAPSHOT, id2name)
                        print(f"   已蒐集 {found_this_run} 款，達到上限 {limit_games}，先收。")
                        break
                                              
            processed += 1

            if processed % CHECKPOINT_EVERY == 0:
                save_checkpoint(next_index=i+1, processed=processed, found=len(found_ids))
                write_snapshot_array(RESULT_SNAPSHOT, id2name)
                print(f"   [checkpoint] 跑到 {i+1}/{total}，已找到 {len(found_ids)}")

            time.sleep(PAUSE)

    except KeyboardInterrupt:
        print("\n偵測到中斷（Ctrl+C），先幫你存檢查點…")
        next_i = (i + 1) if 'i' in locals() else start_idx
        save_checkpoint(next_index=next_i, processed=processed, found=len(found_ids))
        write_snapshot_array(RESULT_SNAPSHOT, id2name)
        print("已存檢查點，隨時可再執行續跑。")
        return


    # 跑完收尾
    save_checkpoint(next_index=total, processed=processed, found=len(found_ids))
    write_snapshot_array(RESULT_SNAPSHOT, id2name)
    print("完成！總遊戲數：", len(found_ids))
    print("結果（逐行 JSON）在：", RESULT_JSONL)
    print("快照（陣列 JSON）在：", RESULT_SNAPSHOT)


# 主流程：爬取遊戲評論（可中斷續跑）
def main_reviews(max_pages_per_app: int | None = None, limit_games: int | None = None):
    game_ids = load_game_ids_from_result()
    if limit_games:
        game_ids = game_ids[:limit_games]    
    total = len(game_ids)
    start_idx = load_reviews_checkpoint()
    print(f"[reviews] 從索引 {start_idx} 開始，共 {total} 款遊戲（已限制前 {limit_games} 款）" if limit_games else
          f"[reviews] 從索引 {start_idx} 開始，共 {total} 款遊戲")

    processed = 0
    try:
        for i in range(start_idx, total):
            appid = game_ids[i]
            fetch_reviews_for_app(appid, REVIEWS_JSONL, max_pages=max_pages_per_app)
            processed += 1

            if processed % CHECKPOINT_EVERY == 0:
                save_reviews_checkpoint(next_index=i+1, processed_games=processed)
                print(f"   [reviews checkpoint] 跑到 {i+1}/{total}")

            time.sleep(PAUSE)

    except KeyboardInterrupt:
        print("\n偵測到中斷（Ctrl+C），先幫你存評論檢查點…")
        next_i = (i + 1) if 'i' in locals() else start_idx
        save_reviews_checkpoint(next_index=next_i, processed_games=processed)
        print("已存評論檢查點，隨時可再續跑。")
        return

    save_reviews_checkpoint(next_index=total, processed_games=processed)
    print(f"[reviews] 完成，已處理 {processed} / {total} 款。輸出：{REVIEWS_JSONL}")


if __name__ == "__main__":
    main(limit_games=10, max_apps=10)
    main_reviews(max_pages_per_app=1, limit_games=10)