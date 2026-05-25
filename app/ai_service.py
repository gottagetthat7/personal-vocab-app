from __future__ import annotations

import json
import os
from typing import Any

try:
    from google import genai
    from google.genai import types
except Exception:  # optional dependency
    genai = None
    types = None

SYSTEM_PROMPT = """You explain English vocabulary for a Taiwanese English learner.
Return only valid JSON. Use Traditional Chinese, not Simplified Chinese.
Support words with multiple meanings by returning a meanings array.
Each meaning should be clearly distinct and include part_of_speech, english_meaning,
chinese_translation, chinese_explanation, example_sentence, example_translation, and usage_note.
For each meaning, chinese_translation must be the SHORTEST direct Chinese rendering of the English
word (one to three short equivalents separated by 、 or ；, e.g. "微妙的；細微的"), and
chinese_explanation must be a longer sentence that elaborates on nuance, usage context, or
connotation. Do NOT repeat chinese_translation verbatim inside chinese_explanation.
Keep explanations clear, concise, and useful for review questions.
"""


def _meaning(part: str, en: str, zh_trans: str, zh: str, ex: str, tr: str, note: str) -> dict[str, str]:
    return {
        "part_of_speech": part,
        "english_meaning": en,
        "chinese_translation": zh_trans,
        "chinese_explanation": zh,
        "example_sentence": ex,
        "example_translation": tr,
        "usage_note": note,
    }


FALLBACK_EXAMPLES: dict[str, dict[str, Any]] = {
    "come up with": {
        "type": "phrasal verb",
        "meanings": [_meaning(
            "phrasal verb",
            "To think of or produce an idea, plan, solution, or answer.",
            "想出；提出",
            "用於想出新的點子、方法、計畫或答案，強調思考後產生具體的構想。",
            "She came up with a clever solution to the problem.",
            "她想出了一個聰明的方法來解決這個問題。",
            "Commonly used with idea, solution, plan, answer, and strategy.",
        )],
        "similar_expressions": ["think of", "devise", "propose"],
        "tags": ["daily", "academic", "phrase"],
    },
    "subtle": {
        "type": "adjective",
        "meanings": [_meaning(
            "adjective",
            "Not obvious, strong, or easy to notice.",
            "細微的；微妙的",
            "用來形容不明顯、不容易立刻察覺的差異、暗示、情緒或變化。",
            "There is a subtle difference between the two designs.",
            "這兩個設計之間有一個細微的差異。",
            "Often used to describe small differences, hints, changes, emotions, or effects.",
        )],
        "similar_expressions": ["slight", "delicate", "nuanced"],
        "tags": ["academic", "common"],
    },
    "run": {
        "type": "verb / noun",
        "meanings": [
            _meaning("verb", "To move quickly on foot.", "跑；奔跑", "雙腳快速移動的基本動作，最常見、最具體的字義。", "He runs every morning before class.", "他每天早上上課前跑步。", "The most basic physical-action meaning."),
            _meaning("verb", "To operate or manage something.", "經營；管理", "用在管理公司、團隊、會議、系統等使其正常運作的情境。", "She runs a small software company.", "她經營一家小型軟體公司。", "Common with businesses, systems, meetings, and programs."),
            _meaning("verb", "For software or machines to work or execute.", "執行；運轉", "形容程式、應用、機器在某個環境中執行或運作。", "The app runs locally on your computer.", "這個 app 在你的電腦本機執行。", "Useful in software engineering contexts."),
        ],
        "similar_expressions": ["operate", "manage", "execute"],
        "tags": ["common", "multiple meanings", "software"],
    },
}


def _normalize(data: dict[str, Any], text: str) -> dict[str, Any]:
    meanings = data.get("meanings") or []
    if not isinstance(meanings, list):
        meanings = []
    normalized_meanings = []
    for m in meanings:
        if not isinstance(m, dict):
            continue
        normalized_meanings.append({
            "part_of_speech": str(m.get("part_of_speech") or m.get("type") or ""),
            "english_meaning": str(m.get("english_meaning") or ""),
            "chinese_translation": str(m.get("chinese_translation") or ""),
            "chinese_explanation": str(m.get("chinese_explanation") or ""),
            "example_sentence": str(m.get("example_sentence") or ""),
            "example_translation": str(m.get("example_translation") or ""),
            "usage_note": str(m.get("usage_note") or ""),
        })
    if not normalized_meanings:
        normalized_meanings = [_meaning(
            str(data.get("type") or ""),
            str(data.get("english_meaning") or ""),
            str(data.get("chinese_translation") or ""),
            str(data.get("chinese_explanation") or ""),
            str(data.get("example_sentence") or ""),
            str(data.get("example_translation") or ""),
            str(data.get("usage_note") or ""),
        )]

    _GENERIC_TYPES = {"vocabulary", "word", "term", "entry", "language", "expression"}
    raw_type = str(data.get("type") or "").strip()
    primary = normalized_meanings[0]
    resolved_type = (
        raw_type
        if raw_type and raw_type.lower() not in _GENERIC_TYPES
        else str(primary.get("part_of_speech") or "")
        or ("phrase / expression" if " " in text.strip() else "word")
    )
    # If the model returned legacy top-level english_meaning/chinese_explanation/etc.
    # without putting them inside meanings, fold them into the primary meaning so
    # meanings is the single source of truth.
    if not primary.get("english_meaning") and data.get("english_meaning"):
        primary["english_meaning"] = str(data["english_meaning"])
    if not primary.get("chinese_translation") and data.get("chinese_translation"):
        primary["chinese_translation"] = str(data["chinese_translation"])
    if not primary.get("chinese_explanation") and data.get("chinese_explanation"):
        primary["chinese_explanation"] = str(data["chinese_explanation"])
    if not primary.get("example_sentence") and data.get("example_sentence"):
        primary["example_sentence"] = str(data["example_sentence"])
    if not primary.get("example_translation") and data.get("example_translation"):
        primary["example_translation"] = str(data["example_translation"])
    if not primary.get("usage_note") and data.get("usage_note"):
        primary["usage_note"] = str(data["usage_note"])
    return {
        "input_text": str(data.get("input_text") or text),
        "type": resolved_type,
        "meanings": normalized_meanings,
        "pronunciation": str(data.get("pronunciation") or ""),
        "similar_expressions": data.get("similar_expressions") if isinstance(data.get("similar_expressions"), list) else [],
        "difficulty": str(data.get("difficulty") or "medium"),
        "tags": data.get("tags") if isinstance(data.get("tags"), list) else ["personal"],
    }


def _fallback_generate(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    lowered = cleaned.lower()
    base = FALLBACK_EXAMPLES.get(lowered)
    if base:
        return _normalize({"input_text": cleaned, **base, "difficulty": base.get("difficulty", "medium")}, cleaned)

    guess_type = "phrase / expression" if " " in cleaned else "word"
    return _normalize({
        "input_text": cleaned,
        "type": guess_type,
        "meanings": [_meaning(
            guess_type,
            f"A useful English {guess_type}. Edit this meaning after checking Gemini or a dictionary.",
            "",
            f"「{cleaned}」的中文解釋可在儲存後手動編輯。若設定 GEMINI_API_KEY 或 GOOGLE_API_KEY，系統會產生更完整的繁體中文解釋。",
            f"I want to learn how to use '{cleaned}' correctly.",
            f"我想學會如何正確使用「{cleaned}」。",
            "This fallback result is editable. Enable Gemini for higher-quality explanations.",
        )],
        "difficulty": "medium",
        "tags": ["personal"],
    }, cleaned)


def generate_explanation(text: str) -> dict[str, Any]:
    text = text.strip()
    if not text:
        raise ValueError("Input text cannot be empty")

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key or genai is None or types is None:
        return _fallback_generate(text)

    try:
        client = genai.Client(api_key=api_key)
        model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        prompt = f"""
{SYSTEM_PROMPT}

Vocabulary item: {text}

Return JSON with exactly these top-level fields:
input_text, type, meanings, pronunciation, similar_expressions, difficulty, tags.

Field definitions:
- type: the overall classification of the item. Use one of: word, phrase, idiom, expression, phrasal verb.
- meanings: an array of meaning objects. Each meaning MUST contain part_of_speech, english_meaning, chinese_translation, chinese_explanation, example_sentence, example_translation, usage_note. Include 2-4 meanings if the item has multiple common ones, otherwise include one. Each meaning's part_of_speech should be specific (noun, verb, adjective, adverb, etc.).
  * chinese_translation: the SHORT direct Chinese rendering of the English word for THIS meaning. 1-3 short equivalents joined by 、 or ；. Examples: "細微的；微妙的", "經營；管理", "邊界案例". For idioms with no direct equivalent, leave it empty.
  * chinese_explanation: a longer Traditional Chinese sentence explaining nuance, context, or connotation. Should NOT just repeat chinese_translation.
  This is the ONLY place where meaning content belongs — do not duplicate any per-meaning fields at the top level.
- difficulty: one of easy, medium, hard, advanced.
- tags: short descriptive labels useful for filtering (e.g. academic, business, informal, idiom, daily).
"""
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.25,
            ),
        )
        raw = response.text or "{}"
        return _normalize(json.loads(raw), text)
    except Exception:
        return _fallback_generate(text)
