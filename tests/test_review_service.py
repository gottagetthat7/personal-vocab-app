from __future__ import annotations

from datetime import date, timedelta

from app.database import get_connection
from app.models import MeaningEntry, VocabCreate
from app.review_service import answer_question, create_daily_task, get_task_summary, get_today_task
from app.vocab_service import create_vocab, get_vocab


def _add_vocab(input_text: str, meaning: str, familiarity: int = 0, meanings=None):
    return create_vocab(
        VocabCreate(
            input_text=input_text,
            english_meaning=meaning,
            chinese_explanation=f"{input_text} 的中文解釋",
            meanings=meanings or [MeaningEntry(part_of_speech="word", english_meaning=meaning, chinese_explanation=f"{input_text} 的中文解釋")],
            familiarity=familiarity,
        )
    )


def test_create_daily_task_uses_due_words(temp_db):
    due = _add_vocab("subtle", "Not easy to notice.", familiarity=0)
    future = _add_vocab("inevitable", "Impossible to avoid.", familiarity=5)

    with get_connection() as conn:
        conn.execute(
            "UPDATE vocabulary_items SET next_review_at = ? WHERE id = ?",
            ((date.today() + timedelta(days=7)).isoformat(), future["id"]),
        )

    task = create_daily_task()
    assert task["review_date"].startswith(date.today().isoformat())
    assert task["total_questions"] == 1
    assert task["questions"][0]["vocab_id"] == due["id"]
    assert len(task["questions"][0]["options"]) == 4


def test_multiple_sessions_can_be_created_in_one_day(temp_db):
    _add_vocab("subtle", "Not easy to notice.", familiarity=0)
    _add_vocab("massive", "Very large.", familiarity=0)

    task1 = create_daily_task()
    task2 = create_daily_task()

    assert task1["id"] != task2["id"]
    assert task1["review_date"].startswith(date.today().isoformat())
    assert task2["review_date"].startswith(date.today().isoformat())

    # get_today_task returns the most recent one
    today = get_today_task()
    assert today is not None
    assert today["id"] == task2["id"]


def test_answer_question_updates_familiarity_counts_and_summary(temp_db):
    item = _add_vocab("subtle", "Not easy to notice.", familiarity=0)
    _add_vocab("massive", "Very large.", familiarity=0)
    task = create_daily_task()
    question = next(q for q in task["questions"] if q["vocab_id"] == item["id"])

    result = answer_question(question["id"], question["correct_answer"])

    assert result is not None
    assert result["is_correct"] is True
    assert result["new_familiarity"] == 1
    assert result["summary"]["answered_questions"] >= 1
    assert result["summary"]["correct_count"] >= 1
    assert result["summary"]["words_improved"] >= 1
    assert "time_spent_seconds" in result["summary"]

    updated = get_vocab(item["id"])
    assert updated is not None
    assert updated["review_count"] == 1
    assert updated["correct_count"] == 1
    assert updated["wrong_count"] == 0

    summary = get_task_summary(task["id"])
    assert summary is not None
    assert summary["answered_questions"] >= 1


def test_re_answering_does_not_corrupt_stats(temp_db):
    item = _add_vocab("subtle", "Not easy to notice.", familiarity=0)
    _add_vocab("massive", "Very large.", familiarity=0)
    task = create_daily_task()
    question = next(q for q in task["questions"] if q["vocab_id"] == item["id"])

    answer_question(question["id"], question["correct_answer"])
    # answering the same question again must not change any counts
    answer_question(question["id"], question["correct_answer"])

    updated = get_vocab(item["id"])
    assert updated is not None
    assert updated["review_count"] == 1
    assert updated["correct_count"] == 1


def test_summary_is_completed_when_all_questions_answered(temp_db):
    _add_vocab("subtle", "Not easy to notice.", familiarity=0)
    _add_vocab("massive", "Very large.", familiarity=0)
    task = create_daily_task()

    last_result = None
    for q in task["questions"]:
        last_result = answer_question(q["id"], q["correct_answer"])

    assert last_result is not None
    assert last_result["summary"]["completed"] is True
    assert last_result["summary"]["answered_questions"] == task["total_questions"]


def test_multiple_meanings_are_used_in_question_text_or_options(temp_db):
    _add_vocab("massive", "Very large.", familiarity=0)
    run = _add_vocab(
        "run",
        "To move quickly on foot.",
        familiarity=0,
        meanings=[
            MeaningEntry(part_of_speech="verb", english_meaning="To move quickly on foot.", chinese_explanation="跑步。"),
            MeaningEntry(part_of_speech="verb", english_meaning="To operate or manage something.", chinese_explanation="經營或管理。"),
        ],
    )
    task = create_daily_task()
    q = next(q for q in task["questions"] if q["vocab_id"] == run["id"])
    joined = q["question_text"] + " " + " ".join(q["options"])
    assert "跑步" in joined or "經營" in joined or "move quickly" in joined or "operate" in joined or "run" in joined
