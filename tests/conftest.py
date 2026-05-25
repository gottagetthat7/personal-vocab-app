from __future__ import annotations

import pytest

from app import database


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_vocab.db"
    monkeypatch.setattr(database, "DB_PATH", test_db)
    database.init_db()
    return test_db
