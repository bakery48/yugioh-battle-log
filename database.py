"""SQLite database layer for Yu-Gi-Oh! Master Duel battle log."""

import sqlite3
import os
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "battle_log.db")


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = _get_conn()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS tags (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT    UNIQUE NOT NULL
            );

            CREATE TABLE IF NOT EXISTS decks (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT    UNIQUE NOT NULL
            );

            CREATE TABLE IF NOT EXISTS deck_tags (
                deck_id INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
                tag_id  INTEGER NOT NULL REFERENCES tags(id)  ON DELETE CASCADE,
                PRIMARY KEY (deck_id, tag_id)
            );

            CREATE TABLE IF NOT EXISTS weakness_tags (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT    UNIQUE NOT NULL
            );

            CREATE TABLE IF NOT EXISTS deck_weakness_tags (
                deck_id         INTEGER NOT NULL REFERENCES decks(id)         ON DELETE CASCADE,
                weakness_tag_id INTEGER NOT NULL REFERENCES weakness_tags(id) ON DELETE CASCADE,
                PRIMARY KEY (deck_id, weakness_tag_id)
            );

            CREATE TABLE IF NOT EXISTS battles (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                date          TEXT    NOT NULL,
                rank          TEXT    NOT NULL,
                first_second  TEXT    NOT NULL,
                result        TEXT    NOT NULL,
                defeat_reason TEXT    NOT NULL DEFAULT '',
                deck_id       INTEGER REFERENCES decks(id) ON DELETE SET NULL,
                opponent_deck TEXT    NOT NULL
            );
        """)
        conn.commit()
    finally:
        conn.close()


# ── Tags ──────────────────────────────────────────────────────────────────────

def get_all_tags() -> list:
    conn = _get_conn()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM tags ORDER BY name")]
    finally:
        conn.close()


def add_tag(name: str) -> int:
    conn = _get_conn()
    try:
        cur = conn.execute("INSERT INTO tags (name) VALUES (?)", (name,))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def rename_tag(tag_id: int, new_name: str) -> None:
    conn = _get_conn()
    try:
        conn.execute("UPDATE tags SET name = ? WHERE id = ?", (new_name, tag_id))
        conn.commit()
    finally:
        conn.close()


def delete_tag(tag_id: int) -> None:
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
        conn.commit()
    finally:
        conn.close()


# ── Decks ─────────────────────────────────────────────────────────────────────

def get_all_decks() -> list:
    conn = _get_conn()
    try:
        rows = conn.execute("SELECT * FROM decks ORDER BY name").fetchall()
        result = []
        for row in rows:
            deck = dict(row)
            tags = conn.execute(
                """SELECT t.id, t.name FROM tags t
                   JOIN deck_tags dt ON t.id = dt.tag_id
                   WHERE dt.deck_id = ?
                   ORDER BY t.name""",
                (deck["id"],),
            ).fetchall()
            deck["tags"] = [dict(t) for t in tags]
            weakness_tags = conn.execute(
                """SELECT wt.id, wt.name FROM weakness_tags wt
                   JOIN deck_weakness_tags dwt ON wt.id = dwt.weakness_tag_id
                   WHERE dwt.deck_id = ?
                   ORDER BY wt.name""",
                (deck["id"],),
            ).fetchall()
            deck["weakness_tags"] = [dict(t) for t in weakness_tags]
            result.append(deck)
        return result
    finally:
        conn.close()


def _sync_weakness_tags(conn: sqlite3.Connection, deck_id: int, weakness_tag_names: list) -> None:
    """Upsert weakness tags and link them to the deck."""
    conn.execute("DELETE FROM deck_weakness_tags WHERE deck_id = ?", (deck_id,))
    for name in weakness_tag_names:
        conn.execute("INSERT OR IGNORE INTO weakness_tags (name) VALUES (?)", (name,))
        wt_id = conn.execute(
            "SELECT id FROM weakness_tags WHERE name = ?", (name,)
        ).fetchone()["id"]
        conn.execute(
            "INSERT OR IGNORE INTO deck_weakness_tags (deck_id, weakness_tag_id) VALUES (?, ?)",
            (deck_id, wt_id),
        )


def get_all_weakness_tags() -> list:
    conn = _get_conn()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM weakness_tags ORDER BY name")]
    finally:
        conn.close()


def add_deck(name: str, tag_ids: Optional[list] = None,
             weakness_tag_names: Optional[list] = None) -> int:
    conn = _get_conn()
    try:
        cur = conn.execute("INSERT INTO decks (name) VALUES (?)", (name,))
        deck_id = cur.lastrowid
        if tag_ids:
            conn.executemany(
                "INSERT INTO deck_tags (deck_id, tag_id) VALUES (?, ?)",
                [(deck_id, tid) for tid in tag_ids],
            )
        if weakness_tag_names:
            _sync_weakness_tags(conn, deck_id, weakness_tag_names)
        conn.commit()
        return deck_id
    finally:
        conn.close()


def update_deck(deck_id: int, name: str, tag_ids: Optional[list] = None,
                weakness_tag_names: Optional[list] = None) -> None:
    conn = _get_conn()
    try:
        conn.execute("UPDATE decks SET name = ? WHERE id = ?", (name, deck_id))
        conn.execute("DELETE FROM deck_tags WHERE deck_id = ?", (deck_id,))
        if tag_ids:
            conn.executemany(
                "INSERT INTO deck_tags (deck_id, tag_id) VALUES (?, ?)",
                [(deck_id, tid) for tid in tag_ids],
            )
        _sync_weakness_tags(conn, deck_id, weakness_tag_names or [])
        conn.commit()
    finally:
        conn.close()


def delete_deck(deck_id: int) -> None:
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM decks WHERE id = ?", (deck_id,))
        conn.commit()
    finally:
        conn.close()


# ── Battles ───────────────────────────────────────────────────────────────────

def _build_battle_query(filters: Optional[dict]) -> tuple:
    query = """
        SELECT b.id, b.date, b.rank, b.first_second, b.result,
               b.defeat_reason, b.deck_id, b.opponent_deck,
               d.name AS deck_name
        FROM battles b
        LEFT JOIN decks d ON b.deck_id = d.id
        WHERE 1=1
    """
    params = []
    if not filters:
        return query + " ORDER BY b.date DESC, b.id DESC", params

    if filters.get("date_from"):
        query += " AND b.date >= ?"
        params.append(filters["date_from"])
    if filters.get("date_to"):
        query += " AND b.date <= ?"
        params.append(filters["date_to"])
    if filters.get("ranks"):
        ph = ",".join(["?"] * len(filters["ranks"]))
        query += f" AND b.rank IN ({ph})"
        params.extend(filters["ranks"])
    if filters.get("deck_ids"):
        ph = ",".join(["?"] * len(filters["deck_ids"]))
        query += f" AND b.deck_id IN ({ph})"
        params.extend(filters["deck_ids"])
    if filters.get("tag_ids"):
        ph = ",".join(["?"] * len(filters["tag_ids"]))
        query += f"""
            AND b.deck_id IN (
                SELECT DISTINCT deck_id FROM deck_tags WHERE tag_id IN ({ph})
            )"""
        params.extend(filters["tag_ids"])
    query += " ORDER BY b.date DESC, b.id DESC"
    return query, params


def get_battles(filters: Optional[dict] = None) -> list:
    conn = _get_conn()
    try:
        query, params = _build_battle_query(filters)
        return [dict(r) for r in conn.execute(query, params)]
    finally:
        conn.close()


def add_battle(
    date: str,
    rank: str,
    first_second: str,
    result: str,
    defeat_reason: str,
    deck_id: Optional[int],
    opponent_deck: str,
) -> None:
    conn = _get_conn()
    try:
        conn.execute(
            """INSERT INTO battles
               (date, rank, first_second, result, defeat_reason, deck_id, opponent_deck)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (date, rank, first_second, result, defeat_reason, deck_id, opponent_deck),
        )
        conn.commit()
    finally:
        conn.close()


def update_battle(
    battle_id: int,
    date: str,
    rank: str,
    first_second: str,
    result: str,
    defeat_reason: str,
    deck_id: Optional[int],
    opponent_deck: str,
) -> None:
    conn = _get_conn()
    try:
        conn.execute(
            """UPDATE battles
               SET date=?, rank=?, first_second=?, result=?,
                   defeat_reason=?, deck_id=?, opponent_deck=?
               WHERE id=?""",
            (date, rank, first_second, result, defeat_reason, deck_id, opponent_deck, battle_id),
        )
        conn.commit()
    finally:
        conn.close()


def delete_battle(battle_id: int) -> None:
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM battles WHERE id = ?", (battle_id,))
        conn.commit()
    finally:
        conn.close()
