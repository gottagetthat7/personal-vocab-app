from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from .database import get_connection, row_to_vocab


def get_home_stats() -> dict[str, Any]:
    today = date.today()
    labels = [(today - timedelta(days=29 - i)).isoformat() for i in range(30)]
    start = labels[0]

    with get_connection() as conn:
        # Familiarity distribution: one count per level 0-5
        dist_rows = conn.execute(
            "SELECT familiarity, COUNT(*) AS cnt FROM vocabulary_items GROUP BY familiarity"
        ).fetchall()
        dist = [0] * 6
        for row in dist_rows:
            lvl = int(row["familiarity"] or 0)
            if 0 <= lvl <= 5:
                dist[lvl] = row["cnt"]

        # Words added per day (last 30 days)
        added_rows = conn.execute(
            "SELECT date(created_at) AS day, COUNT(*) AS cnt "
            "FROM vocabulary_items "
            "WHERE date(created_at) >= ? "
            "GROUP BY day ORDER BY day",
            (start,),
        ).fetchall()
        added_by_day = {row["day"]: row["cnt"] for row in added_rows}

        # Words whose familiarity improved per day (distinct vocab_id per day)
        improved_rows = conn.execute(
            "SELECT date(answered_at) AS day, COUNT(DISTINCT vocab_id) AS cnt "
            "FROM review_questions "
            "WHERE familiarity_after > familiarity_before "
            "  AND date(answered_at) >= ? "
            "GROUP BY day ORDER BY day",
            (start,),
        ).fetchall()
        improved_by_day = {row["day"]: row["cnt"] for row in improved_rows}

        # Words that first reached expert (familiarity 5) per day
        expert_rows = conn.execute(
            "SELECT date(fh.first_at) AS day, COUNT(*) AS cnt "
            "FROM (SELECT vocab_id, MIN(answered_at) AS first_at "
            "      FROM review_questions WHERE familiarity_after = 5 "
            "      GROUP BY vocab_id) AS fh "
            "WHERE date(fh.first_at) >= ? "
            "GROUP BY day ORDER BY day",
            (start,),
        ).fetchall()
        expert_by_day = {row["day"]: row["cnt"] for row in expert_rows}

        # Words needing practice (familiarity 0 or 1), most recently added first
        practice_rows = conn.execute(
            "SELECT * FROM vocabulary_items "
            "WHERE familiarity <= 1 "
            "ORDER BY created_at DESC LIMIT 6",
        ).fetchall()
        needs_practice = [row_to_vocab(row) for row in practice_rows]

    return {
        "familiarity_distribution": dist,
        "activity": {
            "labels": labels,
            "added":    [added_by_day.get(d, 0)    for d in labels],
            "improved": [improved_by_day.get(d, 0) for d in labels],
            "expert":   [expert_by_day.get(d, 0)   for d in labels],
        },
        "needs_practice": needs_practice,
    }
