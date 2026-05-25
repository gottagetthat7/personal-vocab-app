from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.ai_service import generate_explanation, _fallback_generate, _normalize

REQUIRED_FIELDS = {
    "input_text", "type", "english_meaning", "chinese_explanation",
    "meanings", "example_sentence", "example_translation",
    "pronunciation", "usage_note", "similar_expressions", "difficulty", "tags",
}


def _assert_valid_result(result: dict, expected_text: str | None = None) -> None:
    assert REQUIRED_FIELDS <= result.keys(), f"Missing fields: {REQUIRED_FIELDS - result.keys()}"
    assert isinstance(result["meanings"], list)
    assert len(result["meanings"]) >= 1
    assert isinstance(result["similar_expressions"], list)
    assert isinstance(result["tags"], list)
    assert isinstance(result["difficulty"], str)
    if expected_text:
        assert result["input_text"] == expected_text
    for m in result["meanings"]:
        assert "english_meaning" in m
        assert "chinese_explanation" in m


# ── Fallback: known words ────────────────────────────────────────────────────

def test_fallback_known_word_subtle():
    result = _fallback_generate("subtle")
    _assert_valid_result(result, "subtle")
    assert "subtle" in result["english_meaning"].lower() or result["english_meaning"]
    assert result["chinese_explanation"]


def test_fallback_known_phrase_come_up_with():
    result = _fallback_generate("come up with")
    _assert_valid_result(result, "come up with")
    assert result["type"]


def test_fallback_known_word_run_has_multiple_meanings():
    result = _fallback_generate("run")
    _assert_valid_result(result, "run")
    assert len(result["meanings"]) >= 2


def test_fallback_known_words_are_case_insensitive():
    lower = _fallback_generate("subtle")
    upper = _fallback_generate("Subtle")
    assert lower["input_text"] == "subtle"
    assert upper["input_text"] == "Subtle"
    assert lower["english_meaning"] == upper["english_meaning"]


# ── Fallback: unknown words ──────────────────────────────────────────────────

def test_fallback_unknown_single_word():
    result = _fallback_generate("ephemeral")
    _assert_valid_result(result, "ephemeral")
    assert result["type"] == "word"
    assert len(result["meanings"]) == 1


def test_fallback_unknown_phrase_infers_type():
    result = _fallback_generate("keep an eye on")
    _assert_valid_result(result, "keep an eye on")
    assert result["type"] == "phrase / expression"


def test_fallback_strips_whitespace():
    result = _fallback_generate("  subtle  ")
    assert result["input_text"] == "subtle"


# ── _normalize ───────────────────────────────────────────────────────────────

def test_normalize_builds_meanings_from_top_level_fields_when_array_empty():
    data = {
        "type": "adjective",
        "english_meaning": "Hard to detect.",
        "chinese_explanation": "難以察覺的。",
        "example_sentence": "A subtle hint.",
        "example_translation": "一個細微的暗示。",
        "usage_note": "Often used with 'difference'.",
        "similar_expressions": ["slight"],
        "difficulty": "medium",
        "tags": ["academic"],
    }
    result = _normalize(data, "subtle")
    assert result["meanings"][0]["english_meaning"] == "Hard to detect."
    assert result["meanings"][0]["chinese_explanation"] == "難以察覺的。"


def test_normalize_non_list_meanings_is_treated_as_empty():
    data = {"meanings": "not a list", "english_meaning": "Fallback."}
    result = _normalize(data, "test")
    assert isinstance(result["meanings"], list)
    assert result["meanings"][0]["english_meaning"] == "Fallback."


def test_normalize_non_list_similar_expressions_defaults_to_empty():
    result = _normalize({"similar_expressions": "slight, delicate"}, "test")
    assert result["similar_expressions"] == []


def test_normalize_non_list_tags_defaults_to_personal():
    result = _normalize({"tags": "academic"}, "test")
    assert result["tags"] == ["personal"]


def test_normalize_preserves_all_meaning_fields():
    meanings = [{
        "part_of_speech": "verb",
        "english_meaning": "To run.",
        "chinese_explanation": "跑。",
        "example_sentence": "She runs fast.",
        "example_translation": "她跑得很快。",
        "usage_note": "Physical motion.",
    }]
    result = _normalize({"meanings": meanings}, "run")
    m = result["meanings"][0]
    assert m["part_of_speech"] == "verb"
    assert m["example_sentence"] == "She runs fast."
    assert m["usage_note"] == "Physical motion."


# ── generate_explanation: no API key (uses fallback) ─────────────────────────

def test_generate_explanation_without_api_key_uses_fallback(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    result = generate_explanation("subtle")
    _assert_valid_result(result, "subtle")


def test_generate_explanation_empty_text_raises(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(ValueError, match="empty"):
        generate_explanation("   ")


# ── generate_explanation: Gemini API path (mocked) ───────────────────────────

MOCK_GEMINI_RESPONSE = {
    "input_text": "ephemeral",
    "type": "adjective",
    "english_meaning": "Lasting for a very short time.",
    "chinese_explanation": "短暫的；轉瞬即逝的。",
    "meanings": [{
        "part_of_speech": "adjective",
        "english_meaning": "Lasting for a very short time.",
        "chinese_explanation": "短暫的；轉瞬即逝的。",
        "example_sentence": "Fame can be ephemeral.",
        "example_translation": "名聲可能是短暫的。",
        "usage_note": "Often describes trends, feelings, or moments.",
    }],
    "example_sentence": "Fame can be ephemeral.",
    "example_translation": "名聲可能是短暫的。",
    "pronunciation": "/ɪˈfem.ər.əl/",
    "usage_note": "Often describes trends, feelings, or moments.",
    "similar_expressions": ["transient", "fleeting"],
    "difficulty": "hard",
    "tags": ["academic"],
}


def _make_mock_client(response_json: dict):
    mock_response = MagicMock()
    mock_response.text = json.dumps(response_json)
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response
    return mock_client


def test_generate_explanation_calls_gemini_when_api_key_set(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    mock_client = _make_mock_client(MOCK_GEMINI_RESPONSE)

    import app.ai_service as ai_mod
    with patch.object(ai_mod, "genai", create=True) as mock_genai, \
         patch.object(ai_mod, "types", create=True):
        mock_genai.Client.return_value = mock_client
        result = generate_explanation("ephemeral")

    _assert_valid_result(result, "ephemeral")
    assert result["pronunciation"] == "/ɪˈfem.ər.əl/"
    assert result["difficulty"] == "hard"
    assert "transient" in result["similar_expressions"]
    mock_client.models.generate_content.assert_called_once()


def test_generate_explanation_falls_back_when_gemini_raises(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    import app.ai_service as ai_mod
    with patch.object(ai_mod, "genai", create=True) as mock_genai, \
         patch.object(ai_mod, "types", create=True):
        mock_genai.Client.return_value = MagicMock(
            models=MagicMock(generate_content=MagicMock(side_effect=Exception("API error")))
        )
        result = generate_explanation("subtle")

    _assert_valid_result(result, "subtle")


def test_generate_explanation_falls_back_on_invalid_json(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    mock_response = MagicMock()
    mock_response.text = "this is not json {"
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    import app.ai_service as ai_mod
    with patch.object(ai_mod, "genai", create=True) as mock_genai, \
         patch.object(ai_mod, "types", create=True):
        mock_genai.Client.return_value = mock_client
        result = generate_explanation("subtle")

    _assert_valid_result(result, "subtle")
