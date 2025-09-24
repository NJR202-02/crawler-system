import requests, time, json, random
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python_operator import PythonOperator
from airflow.operators.bash_operator import BashOperator
from airflow.operators.dummy_operator import DummyOperator

from data_ingestion.transform import split_into_k, normalize_game_row
from data_ingestion.steam_crawler import fetch_app_detail, get_app_list, get_app_detail
from data_ingestion.mysql import insert_ignore_ids, upsert_game_info, game_app_ids, non_game_app_ids, failed_app_ids

# 預設參數
default_args = {
    'owner': 'NJR202_02_NA',
    'start_date': datetime(2024, 1, 1),
    'retries': 1,  # 失敗時最多重試 X 次
    'retry_delay': timedelta(minutes=1),  # 重試間隔 X 分鐘
    'execution_timeout': timedelta(hours=1),  # 執行超時時間 X 小時
}

# ===== Python Functions =====

URL_LIST= "https://api.steampowered.com/ISteamApps/GetAppList/v2/"
URL_DETAIL = "https://store.steampowered.com/api/appdetails"
HEADERS = {"User-Agent": "Mozilla/5.0 Chrome/138.0.0.0"}
K=10  # 決定切出多少task

def plan_chunks(**context):
    """取得 apps 長度，切 k 份，丟進 XCom"""
    apps = get_app_list(limit=100)
    n = len(apps)
    chunks = split_into_k(n, K)

    ti = context["task_instance"]
    ti.xcom_push(key="total", value=n)
    ti.xcom_push(key="chunks", value=chunks)

    print(f"總數: {n}, 分成 {K} 份")
    for c in chunks:
        print(f"Task{c['task_no']}: [{c['start']}, {c['end']}) (人類 {c['human_from']}~{c['human_to']})")

# def process_chunk(index: int, **context):
#     """取回第 index 段範圍，自己抓資料並處理 apps[start:end]"""
#     ti = context["task_instance"]
#     chunks = ti.xcom_pull(task_ids="plan_chunks", key="chunks") or []
#     total = ti.xcom_pull(task_ids="plan_chunks", key="total") or 0

#     # 防呆：n < 10 時，可能會有空段
#     if index >= len(chunks):
#         print(f"Task{index+1}: 無對應區段，跳過")
#         return "skip"

#     chunk = chunks[index]
#     start, end = chunk["start"], chunk["end"]
#     if start >= end:
#         print(f"Task{index+1}: 空區段 [{start}, {end}), 跳過")
#         return "empty"

#     # 建議每個 task 自己抓資料，避免 XCom 傳大物件
#     r = requests.get(URL_LIST, headers=HEADERS, timeout=30)
#     r.raise_for_status()
#     apps = r.json().get("applist", {}).get("apps", [])
#     part = apps[start:end]

#     print(f"Task{index+1} / total={total}，處理範圍 [{start}, {end})，大小={len(part)}")
#     print("Sample:", part[0] if part else None)
#     # TODO: 在這裡做實際處理

#     return f"done-{index+1}"

def process_chunk(index: int, **context):
    """
    取回第 index 段，逐一呼叫 appdetails
    - type == 'game'  → 寫入 game_app_ids + 明細寫入/更新 game_info
    - 其他/拿不到   → 寫入 non_game_app_ids
    """
    ti = context["task_instance"]
    chunks = ti.xcom_pull(task_ids="plan_chunks", key="chunks") or []
    total  = ti.xcom_pull(task_ids="plan_chunks", key="total") or 0

    if index >= len(chunks):
        print(f"Task{index+1}: 無對應區段，跳過")
        return "skip"

    chunk = chunks[index]
    start, end = chunk["start"], chunk["end"]

    print(f"📢 此 task 從第 {start+1} 個ID開始, 到第 {end} 個結束")

    if start >= end:
        print(f"Task{index+1}: 空區段 [{start}, {end}), 跳過")
        return "empty"

    # 取清單（這裡只用來拿 appid 範圍；真的明細在下面逐筆打）
    apps = get_app_list()
    part = apps[start:end]

    game_ids, non_game_ids, failed_ids, game_rows = [], [], []
    PAUSE = 0.2 + random.random()*0.2   # 禮貌性間隔，避免被風控

    for i, item in enumerate(part, start=1):
        appid = item.get("appid")
        if appid is None:
            continue

        data = get_app_detail(appid)
        if not data:
            failed_ids.append(int(appid))
            time.sleep(PAUSE)
            print(f"❓好像找不到 {appid} 。。。")
            continue

        typ = str(data.get("type", "")).lower()
        if typ == "game":
            game_ids.append(int(appid))
            print(f"✅ {appid} 是遊戲！寫入清單。。。")
            row = normalize_game_row(int(appid),data)
            if row.get("app_id") is not None:
                game_rows.append(row)
        else:
            non_game_ids.append(int(appid))
            print(f"❌ {appid} 不屬於遊戲，寫入清單。。。")

        # 節流
        time.sleep(PAUSE)

    # ---- 批量寫入 ----
    if game_ids:
        insert_ignore_ids(game_app_ids, game_ids)
    if non_game_ids:
        insert_ignore_ids(non_game_app_ids, non_game_ids)
    if failed_ids:
        insert_ignore_ids(failed_app_ids, failed_ids)
    if game_rows:
        upsert_game_info(game_rows)

    print(
        f"Task{index+1}/{total}: 範圍[{start},{end}) "
        f"→ game_ids={len(game_ids)}, non_game_ids={len(non_game_ids)}, failed_ids={len(failed_ids)}, game_info_rows={len(game_rows)}"
    )

    if game_rows:
        print("示例一筆：", json.dumps(game_rows[0], ensure_ascii=False)[:300])

    return f"done-{index+1}"


# ===== DAG Definition =====

# 使用 with DAG 語法
with DAG(
    dag_id='steam_crawler_dag',
    default_args=default_args,
    description='Steam遊戲數據爬取 DAG - 爬取遊戲資訊與玩家評論',
    schedule_interval=None,  # 手動觸發
    start_date=datetime(2024, 1, 1),
    catchup=False, # 不執行歷史任務
    max_active_runs=1,  # 同時只允許一個 DAG 實例運行
    # max_active_tasks=3,  # 同時只允許 3 個 task 運行
    tags=['steam', 'crawler', 'etl'],
) as dag:

    # ===== Tasks Definition =====
    
    # 開始任務
    start_task = DummyOperator(
        task_id='start',
    )
    
    plan_task = PythonOperator(
        task_id="plan_chunks",
        python_callable=plan_chunks,  # 會自動注入 **context
    )

    # 迴圈建立 10 個處理 task，透過 op_kwargs 傳 index
    info_tasks = []
    for i in range(K):
        task = PythonOperator(
            task_id=f"info_task_{i+1}",
            python_callable=process_chunk,
            op_kwargs={"index": i},
        )
        info_tasks.append(task)

    end_task = DummyOperator(
        task_id="end"
    )

    start_task >> plan_task >> info_tasks >> end_task
