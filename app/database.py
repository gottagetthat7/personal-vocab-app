from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "vocab.db"


VOCAB_EXTRA_COLUMNS = {
    "meanings_json": "TEXT DEFAULT '[]'",
}

REVIEW_TASK_EXTRA_COLUMNS = {
    "started_at": "TEXT",
}

REVIEW_QUESTION_EXTRA_COLUMNS = {
    "familiarity_before": "INTEGER",
    "familiarity_after": "INTEGER",
}


def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


LEGACY_VOCAB_COLUMNS = [
    "english_meaning",
    "chinese_explanation",
    "example_sentence",
    "example_translation",
    "usage_note",
]


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS vocabulary_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                input_text TEXT NOT NULL UNIQUE,
                type TEXT DEFAULT '',
                meanings_json TEXT DEFAULT '[]',
                pronunciation TEXT DEFAULT '',
                similar_expressions_json TEXT DEFAULT '[]',
                difficulty TEXT DEFAULT 'medium',
                tags_json TEXT DEFAULT '[]',
                familiarity INTEGER DEFAULT 0,
                review_count INTEGER DEFAULT 0,
                correct_count INTEGER DEFAULT 0,
                wrong_count INTEGER DEFAULT 0,
                last_reviewed_at TEXT,
                next_review_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS review_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                review_date TEXT NOT NULL UNIQUE,
                status TEXT DEFAULT 'not_started',
                total_questions INTEGER DEFAULT 0,
                correct_questions INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                started_at TEXT,
                completed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS review_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                vocab_id INTEGER NOT NULL,
                question_type TEXT NOT NULL,
                question_text TEXT NOT NULL,
                correct_answer TEXT NOT NULL,
                options_json TEXT NOT NULL,
                user_answer TEXT,
                is_correct INTEGER,
                answered_at TEXT,
                familiarity_before INTEGER,
                familiarity_after INTEGER,
                FOREIGN KEY (task_id) REFERENCES review_tasks(id) ON DELETE CASCADE,
                FOREIGN KEY (vocab_id) REFERENCES vocabulary_items(id) ON DELETE CASCADE
            );
            """
        )
        _ensure_columns(conn, "vocabulary_items", VOCAB_EXTRA_COLUMNS)
        _ensure_columns(conn, "review_tasks", REVIEW_TASK_EXTRA_COLUMNS)
        _ensure_columns(conn, "review_questions", REVIEW_QUESTION_EXTRA_COLUMNS)
        _migrate_unify_meanings(conn)


def _migrate_unify_meanings(conn: sqlite3.Connection) -> None:
    """Backfill the legacy per-meaning columns into meanings_json, then drop them.

    After this migration, meanings_json is the single source of truth for per-meaning
    content. Each row contains an array of objects with part_of_speech, english_meaning,
    chinese_explanation, example_sentence, example_translation, usage_note.
    """
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(vocabulary_items)").fetchall()}
    legacy_present = [c for c in LEGACY_VOCAB_COLUMNS if c in existing]
    if not legacy_present:
        return

    # 1. Backfill meanings_json from legacy columns where meanings_json is empty / missing primary content.
    select_cols = ["id", "type", "meanings_json"] + legacy_present
    rows = conn.execute(f"SELECT {', '.join(select_cols)} FROM vocabulary_items").fetchall()
    for row in rows:
        try:
            current = json.loads(row["meanings_json"] or "[]")
            if not isinstance(current, list):
                current = []
        except json.JSONDecodeError:
            current = []
        en = (row["english_meaning"] if "english_meaning" in row.keys() else "") or ""
        zh = (row["chinese_explanation"] if "chinese_explanation" in row.keys() else "") or ""
        ex = (row["example_sentence"] if "example_sentence" in row.keys() else "") or ""
        tr = (row["example_translation"] if "example_translation" in row.keys() else "") or ""
        note = (row["usage_note"] if "usage_note" in row.keys() else "") or ""
        has_legacy_content = bool(en or zh or ex or tr or note)
        if current:
            # If first meaning has no english_meaning but legacy does, hydrate it.
            first = current[0] if isinstance(current[0], dict) else {}
            if has_legacy_content and not (first.get("english_meaning") or first.get("chinese_explanation")):
                first.update({
                    "part_of_speech": first.get("part_of_speech") or (row["type"] or ""),
                    "english_meaning": en, "chinese_explanation": zh,
                    "example_sentence": ex, "example_translation": tr, "usage_note": note,
                })
                current[0] = first
                conn.execute("UPDATE vocabulary_items SET meanings_json = ? WHERE id = ?",
                             (json.dumps(current, ensure_ascii=False), row["id"]))
            continue
        if not has_legacy_content:
            continue
        meaning = {
            "part_of_speech": row["type"] or "",
            "english_meaning": en, "chinese_explanation": zh,
            "example_sentence": ex, "example_translation": tr, "usage_note": note,
        }
        conn.execute("UPDATE vocabulary_items SET meanings_json = ? WHERE id = ?",
                     (json.dumps([meaning], ensure_ascii=False), row["id"]))

    # 2. Drop the legacy columns (SQLite 3.35+ supports DROP COLUMN).
    for col in legacy_present:
        try:
            conn.execute(f"ALTER TABLE vocabulary_items DROP COLUMN {col}")
        except sqlite3.OperationalError:
            # SQLite too old or column has dependencies — leave it; the rest of the app ignores it.
            pass


def _loads_list(value: str | None) -> list[Any]:
    try:
        data = json.loads(value or "[]")
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def row_to_vocab(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    # Drop any lingering legacy columns so the API surface is clean.
    for legacy in LEGACY_VOCAB_COLUMNS:
        item.pop(legacy, None)
    item["similar_expressions"] = _loads_list(item.pop("similar_expressions_json", "[]"))
    item["tags"] = _loads_list(item.pop("tags_json", "[]"))
    item["meanings"] = _loads_list(item.pop("meanings_json", "[]"))
    return item


def row_to_question(row: sqlite3.Row) -> dict[str, Any]:
    q = dict(row)
    q["options"] = _loads_list(q.pop("options_json", "[]"))
    if q.get("is_correct") is not None:
        q["is_correct"] = bool(q["is_correct"])
    return q


def fetchone(query: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(query, tuple(params)).fetchone()


def fetchall(query: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(query, tuple(params)).fetchall()
