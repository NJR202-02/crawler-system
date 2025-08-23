# get_game_ids_streaming_with_names.py
import requests
import time
import json
import os
from typing import Set, Dict, Tuple

URL_ALL = "https://api.steampowered.com/ISteamApps/GetAppList/v2/"
URL_DETAIL = "https://store.steampowered.com/api/appdetails"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
}

PAUSE = 0.12                 # 每顆之間停一下，禮貌一點
RETRY = 2                    # 失敗重試次數（不含第一次）
CHECKPOINT_EVERY = 100       # 每處理幾筆就存一次檢查點

CHECKPOINT_FILE = "checkpoint.json"                    # 存「跑到第幾筆」
RESULT_JSONL = "steam_games.jsonl"                     # 每行一筆 {"appid":..., "name":"..."}
RESULT_SNAPSHOT = "steam_games_snapshot.json"          # 週期性輸出一份陣列快照


# ---------- 基礎函式 ----------
def get_all_apps():
    # 取得全部 app 清單（每筆含 appid 與 name）。
    resp = requests.get(URL_ALL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json().get("applist", {}).get("apps", [])


def is_game(appid: int) -> bool:
    # 查一顆 appid，告訴你是不是 'game'。含簡單重試與防呆。
    params = {"appids": appid}
    tries = 1 + RETRY
    for _ in range(tries):
        try:
            r = requests.get(URL_DETAIL, params=params, headers=HEADERS, timeout=30)
            if r.status_code != 200:
                time.sleep(0.5); continue
            try:
                payload = r.json()
            except ValueError:
                time.sleep(0.5); continue
            if not isinstance(payload, dict):
                time.sleep(0.5); continue
            root = payload.get(str(appid), {})
            if not root.get("success"):
                return False
            info = root.get("data", {})
            return info.get("type") == "game"
        except requests.RequestException:
            time.sleep(0.5)
    return False


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
                name = v.get("name", "")
                if isinstance(appid, int):
                    ids.add(appid)
                    if name:
                        id2name[appid] = name
    return ids, id2name


def append_record_jsonl(path: str, appid: int, name: str):
    # 把單一 {appid, name} 以 JSON Lines 方式追加一行，並立刻 flush。
    record = {"appid": int(appid), "name": name or ""}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()


def write_snapshot_array(path: str, id2name: Dict[int, str]):
    # 把目前累積的 {appid: name} 寫成陣列 JSON，排序後好讀。
    rows = [{"appid": appid, "name": id2name.get(appid, "")} for appid in sorted(id2name)]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


# ---------- 主流程（可中斷續跑） ----------
def main():
    print("1) 載入全部 app 清單…")
    apps = get_all_apps()
    total = len(apps)
    print("   總數：", total)

    # 讀上次 checkpoint 與已寫入紀錄
    start_idx = load_checkpoint()
    found_ids, id2name = load_existing_from_jsonl(RESULT_JSONL)
    print(f"2) 從索引 {start_idx} 續跑；已累積遊戲數：{len(found_ids)}")

    processed = 0
    try:
        for i in range(start_idx, total):
            app = apps[i]
            appid = app["appid"]
            name = app.get("name", "")

            if is_game(appid):
                if appid not in found_ids:
                    append_record_jsonl(RESULT_JSONL, appid, name)
                    found_ids.add(appid)
                    id2name[appid] = name  # 記住名字，之後快照會用到

            processed += 1
            if processed % CHECKPOINT_EVERY == 0:
                save_checkpoint(next_index=i+1, processed=processed, found=len(found_ids))
                write_snapshot_array(RESULT_SNAPSHOT, id2name)
                print(f"   [checkpoint] 跑到 {i+1}/{total}，已找到 {len(found_ids)}")

            time.sleep(PAUSE)

    except KeyboardInterrupt:
        print("\n偵測到中斷（Ctrl+C），先幫你存檢查點…")
        save_checkpoint(next_index=i, processed=processed, found=len(found_ids))
        write_snapshot_array(RESULT_SNAPSHOT, id2name)
        print("已存檢查點，隨時可再執行續跑。")
        return

    # 跑完收尾
    save_checkpoint(next_index=total, processed=processed, found=len(found_ids))
    write_snapshot_array(RESULT_SNAPSHOT, id2name)
    print("完成！總遊戲數：", len(found_ids))
    print("結果（逐行 JSON）在：", RESULT_JSONL)
    print("快照（陣列 JSON）在：", RESULT_SNAPSHOT)


if __name__ == "__main__":
    main()
