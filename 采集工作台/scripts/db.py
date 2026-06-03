"""SQLite 持久化：runs / products / notes / reviews / pain_points 五张表。

为什么不用 ORM：5 张扁平表，SELECT 模式固定，引入 SQLAlchemy 反而是负担。
按 run_id 分桶让"按时间复跑做趋势对比"成为简单的 GROUP BY 查询。
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

DEFAULT_DB = Path("采集工作台/outputs/selector.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    source     TEXT NOT NULL,
    keyword    TEXT NOT NULL,
    region     TEXT,
    fetched_at INTEGER NOT NULL,
    note       TEXT
);

CREATE TABLE IF NOT EXISTS products (
    run_id       INTEGER NOT NULL,
    source       TEXT NOT NULL,
    source_id    TEXT NOT NULL,
    title        TEXT,
    price        REAL,
    sold         INTEGER,
    rating       REAL,
    review_count INTEGER,
    shop         TEXT,
    brand        TEXT,
    score        REAL,
    extra_json   TEXT,
    fetched_at   INTEGER NOT NULL,
    PRIMARY KEY (run_id, source, source_id)
);
CREATE INDEX IF NOT EXISTS idx_products_source_id ON products(source, source_id);

CREATE TABLE IF NOT EXISTS notes (
    run_id     INTEGER NOT NULL,
    note_id    TEXT NOT NULL,
    xsec_token TEXT,
    title      TEXT,
    user_name  TEXT,
    likes      INTEGER,
    collects   INTEGER,
    comments   INTEGER,
    shares     INTEGER,
    score      REAL,
    extra_json TEXT,
    fetched_at INTEGER NOT NULL,
    PRIMARY KEY (run_id, note_id)
);

CREATE TABLE IF NOT EXISTS reviews (
    source     TEXT NOT NULL,
    target_id  TEXT NOT NULL,
    review_id  TEXT,
    rating     INTEGER,
    text       TEXT,
    ts         INTEGER,
    fetched_at INTEGER NOT NULL,
    extra_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_reviews_target ON reviews(source, target_id);

CREATE TABLE IF NOT EXISTS pain_points (
    run_id     INTEGER NOT NULL,
    source     TEXT NOT NULL,
    target_id  TEXT NOT NULL,
    kind       TEXT NOT NULL,        -- 'pain' / 'highlight'
    label      TEXT NOT NULL,
    freq       INTEGER,
    example    TEXT,
    fetched_at INTEGER NOT NULL
);
"""


def connect(db_path: Path | str = DEFAULT_DB) -> sqlite3.Connection:
    p = Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(p))
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def start_run(con: sqlite3.Connection, source: str, keyword: str,
              region: str | None = None, note: str | None = None) -> int:
    cur = con.execute(
        "INSERT INTO runs(source, keyword, region, fetched_at, note) VALUES (?,?,?,?,?)",
        (source, keyword, region, int(time.time()), note),
    )
    con.commit()
    return cur.lastrowid


def _now() -> int:
    return int(time.time())


def save_tiktok_products(con: sqlite3.Connection, run_id: int, scored: list[dict]) -> None:
    now = _now()
    rows = [(
        run_id, "tiktok", str(s.get("product_id") or ""), s.get("title"),
        s.get("price"), s.get("sold"), s.get("rating"), s.get("review_count"),
        s.get("shop"), s.get("brand"), s.get("score"),
        json.dumps(s.get("raw") or {}, ensure_ascii=False), now,
    ) for s in scored]
    con.executemany(
        "INSERT OR REPLACE INTO products VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    con.commit()


def save_xhs_products(con: sqlite3.Connection, run_id: int, scored: list[dict]) -> None:
    now = _now()
    rows = [(
        run_id, "xhs_product", str(s.get("sku_id") or ""), s.get("title"),
        s.get("price"), None, s.get("rating"), None,
        s.get("vendor"), None, s.get("score"),
        json.dumps(s.get("raw") or {}, ensure_ascii=False), now,
    ) for s in scored]
    con.executemany(
        "INSERT OR REPLACE INTO products VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    con.commit()


def save_xhs_notes(con: sqlite3.Connection, run_id: int, scored: list[dict]) -> None:
    now = _now()
    rows = [(
        run_id, str(s.get("note_id") or ""), s.get("xsec_token"),
        s.get("title"), s.get("user"),
        s.get("likes"), s.get("collects"), s.get("comments"), s.get("shares"),
        s.get("score"),
        json.dumps(s.get("raw") or {}, ensure_ascii=False), now,
    ) for s in scored]
    con.executemany(
        "INSERT OR REPLACE INTO notes VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    con.commit()


def save_reviews(con: sqlite3.Connection, source: str, target_id: str,
                 reviews: list[dict]) -> None:
    """reviews: [{review_id?, rating?, text, ts?, raw?}]"""
    if not reviews:
        return
    now = _now()
    rows = [(
        source, str(target_id), str(r.get("review_id") or ""),
        r.get("rating"), r.get("text"), r.get("ts"),
        now, json.dumps(r.get("raw") or {}, ensure_ascii=False),
    ) for r in reviews]
    con.executemany(
        "INSERT INTO reviews VALUES (?,?,?,?,?,?,?,?)", rows)
    con.commit()


def save_pain_points(con: sqlite3.Connection, run_id: int, source: str, target_id: str,
                     analysis: dict) -> None:
    """analysis: {pain_points:[{label,freq,example}], highlights:[...]}（analyze.py 输出）。"""
    now = _now()
    rows = []
    for kind in ("pain_points", "highlights"):
        for item in (analysis.get(kind) or []):
            rows.append((
                run_id, source, str(target_id),
                "pain" if kind == "pain_points" else "highlight",
                item.get("label") or "",
                int(item.get("freq") or 0),
                item.get("example") or "",
                now,
            ))
    if rows:
        con.executemany(
            "INSERT INTO pain_points VALUES (?,?,?,?,?,?,?,?)", rows)
        con.commit()


def trend(con: sqlite3.Connection, source: str, source_id: str) -> list[dict]:
    """同一 source_id 的历次快照，做趋势对比用。"""
    cur = con.execute(
        "SELECT r.run_id, r.fetched_at, p.price, p.sold, p.rating, p.review_count, p.score "
        "FROM products p JOIN runs r USING(run_id) "
        "WHERE p.source=? AND p.source_id=? ORDER BY r.fetched_at",
        (source, source_id))
    return [dict(row) for row in cur.fetchall()]
