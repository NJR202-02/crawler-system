import os, time, re, requests, json
import math
import time
import numpy as np
import pandas as pd
from datetime import datetime, timezone

from data_ingestion.transform import safe_int

URL_DETAIL = "https://store.steampowered.com/api/appdetails"

def fetch_app_detail(appid: int) -> dict | None:
    """呼叫 appdetails 取得單一 app 的 data；失敗/非成功回 None"""
    try:
        r = requests.get(URL_DETAIL, params={"appids": appid}, headers=HEADERS, timeout=30)
        r.raise_for_status()
        raw = r.json()
        node = raw.get(str(appid)) or raw.get(appid) or {}
        if not node.get("success"):
            return None
        return node.get("data") or None
    except Exception as e:
        print(f"[warn] appid={appid} fetch detail error: {e}")
        return None

# def get_app_list() -> list[dict]:
#     URL_LIST= "https://api.steampowered.com/ISteamApps/GetAppList/v2/"
#     HEADERS = {"User-Agent": "Mozilla/5.0 Chrome/138.0.0.0"}
#     r = requests.get(URL_LIST, headers=HEADERS, timeout=30)
#     r.raise_for_status()
#     return r.json().get("applist", {}).get("apps", [])

def get_app_list(limit: int | None = 1000) -> list[dict]:
    URL_LIST = "https://api.steampowered.com/ISteamApps/GetAppList/v2/"
    HEADERS  = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/138.0.0.0 Safari/537.36"}
    r = requests.get(URL_LIST, headers=HEADERS, timeout=30)
    r.raise_for_status()
    apps = r.json().get("applist", {}).get("apps", [])
    return apps[:limit] if limit is not None else apps

def get_app_detail(appid: int, retries: int = 2, pause: float = 0.2) -> dict | None:

    URL_DETAIL = "https://store.steampowered.com/api/appdetails"
    HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/138.0.0.0 Safari/537.36"}
    """回傳 appdetails 的 data（或 None）"""
    for t in range(retries + 1):
        try:
            r = requests.get(URL_DETAIL, params={"appids": appid}, headers=HEADERS, timeout=30)
            r.raise_for_status()
            raw = r.json()
            node = raw.get(str(appid)) or {}
            if not node.get("success"):
                return None
            return node.get("data") or None
        except Exception:
            if t == retries:
                return None
            time.sleep(pause * (t + 1))