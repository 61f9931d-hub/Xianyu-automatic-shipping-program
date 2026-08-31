"""SQLite 数据层：商品、发货记录、设置。"""
import json
import re
import sqlite3
import threading
from datetime import datetime

from . import config

_lock = threading.Lock()


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    with _lock, _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS goods (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,             -- 商品名称
                keywords    TEXT NOT NULL DEFAULT '',  -- 匹配关键词，逗号分隔
                content     TEXT NOT NULL,             -- 发货内容（网盘链接+提取码）
                price       TEXT NOT NULL DEFAULT '',  -- 商品价格（如 0.30），价格匹配用
                enabled     INTEGER NOT NULL DEFAULT 1,
                created_at  TEXT DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS shipments (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_key TEXT NOT NULL UNIQUE,      -- 会话去重标识
                buyer       TEXT DEFAULT '',
                goods_name  TEXT DEFAULT '',
                status      TEXT NOT NULL,             -- success / unmatched / failed / skipped
                detail      TEXT DEFAULT '',
                shipped_at  TEXT DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
            """
        )
        # 旧库兼容：补充 price 列
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(goods)").fetchall()]
        if "price" not in cols:
            conn.execute("ALTER TABLE goods ADD COLUMN price TEXT NOT NULL DEFAULT ''")
        for k, v in config.DEFAULT_SETTINGS.items():
            conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)", (k, str(v)))


# ---------------- 设置 ----------------
def get_setting(key: str, default=None):
    with _lock, _conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value) -> None:
    with _lock, _conn() as conn:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )


def all_settings() -> dict:
    with _lock, _conn() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {r["key"]: r["value"] for r in rows}


# ---------------- 商品 ----------------
def add_goods(name: str, keywords: str, content: str, price: str = "") -> int:
    with _lock, _conn() as conn:
        cur = conn.execute(
            "INSERT INTO goods(name, keywords, content, price, enabled) VALUES(?,?,?,?,1)",
            (name, keywords, content, price),
        )
        return cur.lastrowid


def update_goods(gid: int, name: str, keywords: str, content: str, enabled: bool, price: str = "") -> None:
    with _lock, _conn() as conn:
        conn.execute(
            "UPDATE goods SET name=?, keywords=?, content=?, enabled=?, price=? WHERE id=?",
            (name, keywords, content, 1 if enabled else 0, price, gid),
        )


def delete_goods(gid: int) -> None:
    with _lock, _conn() as conn:
        conn.execute("DELETE FROM goods WHERE id=?", (gid,))


def list_goods(only_enabled: bool = False) -> list[dict]:
    sql = "SELECT * FROM goods"
    if only_enabled:
        sql += " WHERE enabled=1"
    sql += " ORDER BY id"
    with _lock, _conn() as conn:
        rows = conn.execute(sql).fetchall()
    return [dict(r) for r in rows]


_PRICE_RE = re.compile(r"¥\s*(\d+(?:\.\d+)?)")


def extract_price(text: str) -> float | None:
    """从文本中提取价格（¥0.30 -> 0.30），找不到返回 None。"""
    if not text:
        return None
    m = _PRICE_RE.search(text)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def match_goods(text: str) -> dict | None:
    """匹配商品：优先按价格精确匹配（闲鱼卡片文本含价格），其次按关键词匹配。

    说明：PC 版聊天窗口不显示商品标题（网页版卖家订单功能也未上线），
    价格是当前最可靠的匹配信号，不同商品建议设置不同价格。
    """
    if not text:
        return None
    # 1) 价格匹配
    price = extract_price(text)
    if price is not None:
        for g in list_goods(only_enabled=True):
            p = (g.get("price") or "").strip()
            if p:
                try:
                    if abs(float(p) - price) < 0.001:
                        return g
                except ValueError:
                    continue
    # 2) 关键词匹配（兜底）
    for g in list_goods(only_enabled=True):
        for kw in [k.strip() for k in (g["keywords"] or "").split(",") if k.strip()]:
            if kw and kw in text:
                return g
    return None


# ---------------- 发货记录 ----------------
def add_shipment(session_key: str, buyer: str, goods_name: str, status: str, detail: str = "") -> None:
    with _lock, _conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO shipments(session_key, buyer, goods_name, status, detail) VALUES(?,?,?,?,?)",
            (session_key, buyer, goods_name, status, detail),
        )


def shipment_exists(session_key: str) -> bool:
    with _lock, _conn() as conn:
        row = conn.execute("SELECT 1 FROM shipments WHERE session_key=?", (session_key,)).fetchone()
    return row is not None


def list_shipments(limit: int = 500) -> list[dict]:
    with _lock, _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM shipments ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def clear_shipments() -> None:
    with _lock, _conn() as conn:
        conn.execute("DELETE FROM shipments")


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def export_goods() -> str:
    """导出商品到 JSON 字符串（备份用）。"""
    return json.dumps(list_goods(), ensure_ascii=False, indent=2)


def import_goods(json_text: str) -> int:
    """从 JSON 导入商品，返回导入数量。"""
    data = json.loads(json_text)
    count = 0
    for item in data:
        if isinstance(item, dict) and item.get("name") and item.get("content"):
            add_goods(item["name"], item.get("keywords", ""), item["content"])
            count += 1
    return count
