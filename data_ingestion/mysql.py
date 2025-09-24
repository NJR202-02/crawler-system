import time, json
from sqlalchemy import create_engine
from sqlalchemy import MetaData, Table, Column, Integer, String, Boolean, Text
from sqlalchemy.dialects.mysql import insert as mysql_insert

from data_ingestion.config import MYSQL_USERNAME, MYSQL_PASSWORD, MYSQL_HOST, MYSQL_PORT

MYSQL_DATABASE = "steam"
MYSQL_URI = f"mysql+pymysql://{MYSQL_USERNAME}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}?charset=utf8mb4"

engine   = create_engine(MYSQL_URI, pool_pre_ping=True)
metadata = MetaData()

# ---- 資料表定義 ----
game_app_ids = Table(
    "game_app_ids", metadata,
    Column("app_id", Integer, primary_key=True),
)

non_game_app_ids = Table(
    "non_game_app_ids", metadata,
    Column("app_id", Integer, primary_key=True),
)

failed_app_ids = Table(
    "failed_app_ids", metadata,
    Column("app_id", Integer, primary_key=True),
)

game_info = Table(
    "game_info", metadata,
    Column("app_id", Integer, primary_key=True, comment="文章ID"),     # 以 app_id 當 PK
    Column("steam_appid", Integer, comment="遊戲ID"),
    Column("name", String(255), comment="遊戲名稱"),
    Column("required_age", Integer, comment="年齡限制"),
    Column("is_free", Boolean, comment="是否免費"),
    Column("header_image", Text, comment="首圖"),
    Column("supported_languages", Text, comment="支援語言"),
    Column("developers", Text, comment="開發商"),     # list 以逗號或 JSON 存
    Column("publishers", Text, comment="發行商"),
    Column("price_initial", Integer, comment="初始價格"),
    Column("platform_win", Boolean, comment="支援win"),
    Column("platform_mac", Boolean, comment="支援mac"),
    Column("platform_linux", Boolean, comment="支援linux"),
    Column("release_date", String(64), comment="發行日期"),
)

# 一次性建表（若不存在）
def create_tables():
    metadata.create_all(engine)

def insert_ignore_ids(table_obj, ids: list[int]) -> int:
    if not ids: return 0
    stmt = mysql_insert(table_obj).prefix_with("IGNORE")
    with engine.begin() as conn:
        res = conn.execute(stmt, [{"app_id": int(x)} for x in ids])
    return res.rowcount

def upsert_game_info(rows: list[dict]) -> int:
    if not rows: return 0
    stmt = mysql_insert(game_info)
    update_map = {c.name: stmt.inserted[c.name] for c in game_info.columns if c.name != "app_id"}
    ondup = stmt.on_duplicate_key_update(**update_map)
    with engine.begin() as conn:
        res = conn.execute(ondup, rows)
    return res.rowcount
