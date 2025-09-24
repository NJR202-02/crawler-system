def safe_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
    
def split_into_k(n: int, k: int):
    base, rem = divmod(n, k)
    chunks, start = [], 0
    for i in range(k):
        size = base + (1 if i < rem else 0)
        end = start + size
        chunks.append({
            "task_no": i + 1,
            "start": start,          # 0-based (含)
            "end": end,              # 0-based (不含)
            "human_from": start + 1, # 1-based (含)
            "human_to": end,         # 1-based (含)
        })
        start = end
    return chunks    

def normalize_game_row(app_id: int, d: dict) -> dict:
    """把 appdetails 的 data 攤平成一列對應 game_info 欄位"""
    price_initial = None
    p = d.get("price_overview") or {}
    if isinstance(p, dict):
        price_initial = p.get("initial")

    platforms = d.get("platforms") or {}
    devs = d.get("developers") or []
    pubs = d.get("publishers") or []
    
    return {
        "app_id":          int(app_id),
        "steam_appid":     d.get("steam_appid"),
        "name":            d.get("name"),
        "required_age":    safe_int(d.get("required_age")),
        "is_free":         bool(d.get("is_free")),
        "header_image":    d.get("header_image"),
        "supported_languages": d.get("supported_languages"),
        "developers":      ", ".join(devs) if isinstance(devs, list) else str(devs),
        "publishers":      ", ".join(pubs) if isinstance(pubs, list) else str(pubs),
        "price_initial":   safe_int(price_initial),
        "platform_win":    bool(platforms.get("windows")) if isinstance(platforms, dict) else None,
        "platform_mac":    bool(platforms.get("mac"))     if isinstance(platforms, dict) else None,
        "platform_linux":  bool(platforms.get("linux"))   if isinstance(platforms, dict) else None,
        "release_date":    (d.get("release_date") or {}).get("date"),
    }