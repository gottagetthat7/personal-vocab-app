from __future__ import annotations

from app.models import VocabCreate, VocabUpdate
from app.vocab_service import create_vocab, delete_vocab, get_vocab, list_vocab, update_vocab


def test_create_list_update_delete_vocab(temp_db):
    item = create_vocab(
        VocabCreate(
            input_text="subtle",
            type="adjective",
            english_meaning="Not easy to notice.",
            chinese_explanation="細微的。",
            tags=["academic"],
        )
    )

    assert item["id"] > 0
    assert item["input_text"] == "subtle"
    assert item["familiarity"] == 0
    assert item["tags"] == ["academic"]

    results = list_vocab("sub")
    assert len(results) == 1

    updated = update_vocab(item["id"], VocabUpdate(familiarity=5, tags=["common", "academic"]))
    assert updated is not None
    assert updated["familiarity"] == 5
    assert updated["tags"] == ["common", "academic"]

    assert get_vocab(item["id"]) is not None
    assert delete_vocab(item["id"]) is True
    assert get_vocab(item["id"]) is None
