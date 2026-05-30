from __future__ import annotations

import json
import random
from datetime import date, datetime, timedelta
from typing import Any

from .database import get_connection, row_to_question, row_to_vocab

MAX_DAILY_QUESTIONS = 20
MAX_EXPERT_SPELL_PER_SESSION = 3
EXPERT_FAMILIARITY = 5
REVIEW_INTERVALS = {
    0: 1,
    1: 1,
    2: 2,
    3: 4,
    4: 7,
    5: 14,
}


def _today() -> str:
    return date.today().isoformat()


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _format_duration(seconds: int) -> str:
    seconds = max(0, seconds)
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m {sec}s"
    if minutes:
        return f"{minutes}m {sec}s"
    return f"{sec}s"


def _make_options(correct: str, candidates: list[str]) -> list[str]:
    clean = []
    seen = {correct.strip().lower()}
    for c in candidates:
        c = (c or "").strip()
        if c and c.lower() not in seen:
            clean.append(c)
            seen.add(c.lower())
    random.shuffle(clean)
    options = [correct] + clean[:3]
    while len(options) < 4:
        options.append(f"None of these ({len(options)})")
    random.shuffle(options)
    return options


def _format_meaning(m: dict[str, Any]) -> str:
    en = (m.get("english_meaning") or "").strip()
    zh_trans = (m.get("chinese_translation") or "").strip()
    zh = (m.get("chinese_explanation") or "").strip()
    part = (m.get("part_of_speech") or "").strip()
    pieces = []
    if part:
        pieces.append(f"({part})")
    if en:
        pieces.append(en)
    # Prefer the concise translation in the question; fall back to the longer explanation if absent.
    if zh_trans:
        pieces.append(f"中文：{zh_trans}")
    elif zh:
        pieces.append(f"中文：{zh}")
    return " ".join(pieces).strip()


def _meaning_text(vocab: dict[str, Any]) -> str:
    """Render all meanings of a vocab item as one string, numbered when there are several.

    Used both as the correct answer for "choose_meaning" questions and as the prompt
    text for "choose_word" questions, so the learner sees every meaning during review.
    """
    meanings = vocab.get("meanings") or []
    formatted = [_format_meaning(m) for m in meanings if isinstance(m, dict)]
    formatted = [f for f in formatted if f]
    if not formatted:
        return vocab.get("input_text", "")
    if len(formatted) == 1:
        return formatted[0]
    return " | ".join(f"{i + 1}. {p}" for i, p in enumerate(formatted))


def _question_for(vocab: dict[str, Any], all_vocab: list[dict[str, Any]]) -> dict[str, Any]:
    question_type = random.choice(["choose_meaning", "choose_word"])
    if question_type == "choose_meaning":
        correct = _meaning_text(vocab)
        candidates = [_meaning_text(v) for v in all_vocab if v["id"] != vocab["id"]]
        return {
            "vocab_id": vocab["id"],
            "question_type": question_type,
            "question_text": f'What does "{vocab["input_text"]}" mean?',
            "correct_answer": correct,
            "options": _make_options(correct, candidates),
        }
    correct = vocab["input_text"]
    candidates = [v["input_text"] for v in all_vocab if v["id"] != vocab["id"]]
    meaning = _meaning_text(vocab)
    return {
        "vocab_id": vocab["id"],
        "question_type": question_type,
        "question_text": f"Which word or phrase means: {meaning}",
        "correct_answer": correct,
        "options": _make_options(correct, candidates),
    }


def _spell_question_for(vocab: dict[str, Any]) -> dict[str, Any]:
    return {
        "vocab_id": vocab["id"],
        "question_type": "spell_word",
        "question_text": f"Spell the word or phrase that means: {_meaning_text(vocab)}",
        "correct_answer": vocab["input_text"],
        "options": [],
    }


def _summary_for(task: dict[str, Any], questions: list[dict[str, Any]]) -> dict[str, Any]:
    answered = [q for q in questions if q.get("is_correct") is not None]
    correct = [q for q in answered if q.get("is_correct") is True]
    incorrect = [q for q in answered if q.get("is_correct") is False]
    improved = [
        q for q in answered
        if q.get("familiarity_before") is not None
        and q.get("familiarity_after") is not None
        and int(q["familiarity_after"]) > int(q["familiarity_before"])
    ]
    start = _parse_dt(task.get("started_at")) or _parse_dt(task.get("created_at"))
    end = _parse_dt(task.get("completed_at")) or (datetime.now() if answered else start)
    seconds = int((end - start).total_seconds()) if start and end else 0
    return {
        "total_questions": int(task.get("total_questions") or len(questions)),
        "answered_questions": len(answered),
        "correct_count": len(correct),
        "incorrect_count": len(incorrect),
        "words_improved": len(improved),
        "time_spent_seconds": seconds,
        "time_spent_display": _format_duration(seconds),
        "completed": task.get("status") == "completed",
    }


def _load_task(task_id: int) -> dict[str, Any]:
    with get_connection() as conn:
        task = conn.execute("SELECT * FROM review_tasks WHERE id = ?", (task_id,)).fetchone()
        questions = conn.execute(
            "SELECT * FROM review_questions WHERE task_id = ? ORDER BY id ASC", (task_id,)
        ).fetchall()
    data = dict(task)
    data["questions"] = [row_to_question(q) for q in questions]
    data["summary"] = _summary_for(data, data["questions"])
    return data


def get_today_task() -> dict[str, Any] | None:
    prefix = _today() + "%"
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM review_tasks WHERE review_date LIKE ? ORDER BY id DESC LIMIT 1",
            (prefix,),
        ).fetchone()
    return _load_task(row["id"]) if row else None


def get_task_summary(task_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM review_tasks WHERE id = ?", (task_id,)).fetchone()
    return _load_task(row["id"])["summary"] if row else None


def create_daily_task() -> dict[str, Any]:
    today = _today()
    now = datetime.now().isoformat(timespec="microseconds")
    with get_connection() as conn:
        vocab_rows = conn.execute("SELECT * FROM vocabulary_items ORDER BY familiarity ASC, datetime(created_at) ASC").fetchall()
    all_vocab = [row_to_vocab(row) for row in vocab_rows]
    due = [v for v in all_vocab if not v.get("next_review_at") or v["next_review_at"] <= today]
    due.sort(key=lambda v: (v.get("familiarity", 0), v.get("last_reviewed_at") or ""))
    selected = due[:MAX_DAILY_QUESTIONS]

    # Sprinkle in a few expert (familiarity 5) words as spelling questions so
    # mastered vocabulary stays active even past its 14-day cadence.
    selected_ids = {v["id"] for v in selected}
    expert_pool = [
        v for v in all_vocab
        if int(v.get("familiarity") or 0) >= EXPERT_FAMILIARITY and v["id"] not in selected_ids
    ]
    random.shuffle(expert_pool)
    expert_sample = expert_pool[:MAX_EXPERT_SPELL_PER_SESSION]

    total = len(selected) + len(expert_sample)

    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO review_tasks (review_date, status, total_questions, started_at) VALUES (?, ?, ?, ?)",
            (now, "not_started", total, now),
        )
        task_id = cursor.lastrowid
        queue = [(_question_for(v, all_vocab)) for v in selected]
        queue.extend(_spell_question_for(v) for v in expert_sample)
        for q in queue:
            conn.execute(
                """
                INSERT INTO review_questions (
                    task_id, vocab_id, question_type, question_text,
                    correct_answer, options_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    q["vocab_id"],
                    q["question_type"],
                    q["question_text"],
                    q["correct_answer"],
                    json.dumps(q["options"], ensure_ascii=False),
                ),
            )
    return _load_task(task_id)


def answer_question(question_id: int, user_answer: str) -> dict[str, Any] | None:
    now = datetime.now().isoformat(timespec="seconds")
    with get_connection() as conn:
        question = conn.execute("SELECT * FROM review_questions WHERE id = ?", (question_id,)).fetchone()
        if not question:
            return None
        q = row_to_question(question)

        if q.get("is_correct") is not None:
            vocab = conn.execute("SELECT * FROM vocabulary_items WHERE id = ?", (q["vocab_id"],)).fetchone()
            if not vocab:
                return None
            v = row_to_vocab(vocab)
            task = _load_task(q["task_id"])
            return {
                "is_correct": q["is_correct"],
                "correct_answer": q["correct_answer"],
                "new_familiarity": int(v.get("familiarity") or 0),
                "next_review_at": v.get("next_review_at"),
                "summary": task["summary"],
            }

        if q.get("question_type") == "spell_word":
            is_correct = user_answer.strip().casefold() == q["correct_answer"].strip().casefold()
        else:
            is_correct = user_answer.strip() == q["correct_answer"].strip()

        vocab = conn.execute("SELECT * FROM vocabulary_items WHERE id = ?", (q["vocab_id"],)).fetchone()
        if not vocab:
            return None
        v = row_to_vocab(vocab)
        old_familiarity = int(v.get("familiarity") or 0)
        new_familiarity = old_familiarity + 1 if is_correct else old_familiarity - 1
        new_familiarity = max(0, min(5, new_familiarity))
        interval_days = REVIEW_INTERVALS[new_familiarity]
        next_review_at = (date.today() + timedelta(days=interval_days)).isoformat()

        conn.execute(
            """
            UPDATE review_questions
            SET user_answer = ?, is_correct = ?, answered_at = ?,
                familiarity_before = ?, familiarity_after = ?
            WHERE id = ?
            """,
            (user_answer, int(is_correct), now, old_familiarity, new_familiarity, question_id),
        )
        conn.execute(
            """
            UPDATE vocabulary_items
            SET familiarity = ?, review_count = review_count + 1,
                correct_count = correct_count + ?, wrong_count = wrong_count + ?,
                last_reviewed_at = ?, next_review_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_familiarity, int(is_correct), int(not is_correct), now, next_review_at, now, q["vocab_id"]),
        )
        counts = conn.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN is_correct IS NOT NULL THEN 1 ELSE 0 END) AS answered,
                   SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) AS correct
            FROM review_questions WHERE task_id = ?
            """,
            (q["task_id"],),
        ).fetchone()
        status = "completed" if counts["answered"] == counts["total"] else "in_progress"
        conn.execute(
            """
            UPDATE review_tasks
            SET status = ?, correct_questions = ?,
                started_at = COALESCE(started_at, ?),
                completed_at = CASE WHEN ? = 'completed' THEN ? ELSE completed_at END
            WHERE id = ?
            """,
            (status, counts["correct"] or 0, now, status, now, q["task_id"]),
        )

    task = _load_task(q["task_id"])
    return {
        "is_correct": is_correct,
        "correct_answer": q["correct_answer"],
        "new_familiarity": new_familiarity,
        "next_review_at": next_review_at,
        "summary": task["summary"],
    }


def review_history() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM review_tasks ORDER BY review_date DESC LIMIT 30").fetchall()
    history = []
    for row in rows:
        task = _load_task(row["id"])
        item = dict(row)
        item["summary"] = task["summary"]
        history.append(item)
    return history
