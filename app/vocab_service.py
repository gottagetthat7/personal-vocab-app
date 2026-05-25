from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from .database import get_connection, row_to_vocab
from .models import VocabCreate, VocabUpdate


def _as_plain(value: Any) -> Any:
    if isinstance(value, list):
        return [v.model_dump() if hasattr(v, "model_dump") else v for v in value]
    return value


def list_vocab(search: str | None = None) -> list[dict[str, Any]]:
    query = "SELECT * FROM vocabulary_items"
    params: list[Any] = []
    if search:
        like = f"%{search.lower()}%"
        # meanings_json contains the JSON-encoded english_meaning / chinese_explanation / examples / usage notes,
        # so a LIKE against it covers all per-meaning text in a single condition.
        query += " WHERE lower(input_text) LIKE ? OR lower(meanings_json) LIKE ? OR lower(tags_json) LIKE ?"
        params = [like, like, like]
    query += " ORDER BY datetime(created_at) DESC, id DESC"
    with get_connection() as conn:
        return [row_to_vocab(row) for row in conn.execute(query, params).fetchall()]


def get_vocab(vocab_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM vocabulary_items WHERE id = ?", (vocab_id,)).fetchone()
        return row_to_vocab(row) if row else None


def create_vocab(item: VocabCreate) -> dict[str, Any]:
    meanings = [m.model_dump() for m in item.meanings]
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO vocabulary_items (
                input_text, type, meanings_json, pronunciation,
                similar_expressions_json, difficulty, tags_json, familiarity, next_review_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.input_text.strip(), item.type,
                json.dumps(meanings, ensure_ascii=False),
                item.pronunciation,
                json.dumps(item.similar_expressions, ensure_ascii=False),
                item.difficulty, json.dumps(item.tags, ensure_ascii=False),
                max(0, min(5, item.familiarity)), date.today().isoformat(),
            ),
        )
        vocab_id = cursor.lastrowid
    created = get_vocab(vocab_id)
    assert created is not None
    return created


def update_vocab(vocab_id: int, update: VocabUpdate) -> dict[str, Any] | None:
    existing = get_vocab(vocab_id)
    if not existing:
        return None
    data = update.model_dump(exclude_unset=True)
    if not data:
        return existing

    columns = []
    params: list[Any] = []
    for key, value in data.items():
        value = _as_plain(value)
        if key == "similar_expressions":
            columns.append("similar_expressions_json = ?")
            params.append(json.dumps(value or [], ensure_ascii=False))
        elif key == "tags":
            columns.append("tags_json = ?")
            params.append(json.dumps(value or [], ensure_ascii=False))
        elif key == "meanings":
            columns.append("meanings_json = ?")
            params.append(json.dumps(value or [], ensure_ascii=False))
        elif key == "familiarity":
            columns.append("familiarity = ?")
            params.append(max(0, min(5, int(value))))
        else:
            columns.append(f"{key} = ?")
            params.append(value)
    columns.append("updated_at = ?")
    params.append(datetime.now().isoformat(timespec="seconds"))
    params.append(vocab_id)

    with get_connection() as conn:
        conn.execute(f"UPDATE vocabulary_items SET {', '.join(columns)} WHERE id = ?", params)
    return get_vocab(vocab_id)


def delete_vocab(vocab_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM vocabulary_items WHERE id = ?", (vocab_id,))
        return cursor.rowcount > 0
