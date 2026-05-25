# SPEC.md — Personal Gemini Vocabulary App

## 1. Project Goal

Build a private vocabulary app for one user. The app lets the user add any English word, phrase, idiom, or expression. It uses the Google Gemini API to generate structured explanations and stores the vocabulary for later review.

The app also provides a daily adaptive multiple-choice review system. Review frequency depends on the user's familiarity with each vocabulary item.

## 2. Target User

The target user is the app owner. The app is designed as a personal English learning tool, not as a multi-user public product.

## 3. Core Vocabulary Workflow

1. User enters a word, phrase, idiom, or expression.
2. Backend calls Gemini to generate an explanation.
3. The generated result is shown in an editable form.
4. User edits if needed.
5. User saves the item to the vocabulary list.
6. User can search, edit, or delete saved items later.

## 4. Generated Vocabulary Fields

Each vocabulary item has a small set of top-level metadata fields plus a single `meanings` array that holds **all** per-meaning content:

Top-level:

- `input_text`
- `type` — overall classification: word / phrase / idiom / expression / phrasal verb
- `meanings` — array of meaning objects (see section 5)
- `pronunciation`
- `similar_expressions`
- `difficulty`
- `tags`
- `familiarity`
- review metadata (`review_count`, `correct_count`, `wrong_count`, `last_reviewed_at`, `next_review_at`)

Per-meaning content (`english_meaning`, `chinese_translation`, `chinese_explanation`, `example_sentence`, `example_translation`, `usage_note`) lives **only** inside `meanings`. There are no duplicate top-level copies — `meanings_json` is the single source of truth.

## 5. Multiple Meanings

Some English words have multiple meanings. The app handles this with a `meanings` array.

Each meaning entry contains:

```json
{
  "part_of_speech": "verb",
  "english_meaning": "To operate or manage something.",
  "chinese_translation": "經營；管理",
  "chinese_explanation": "用在管理公司、團隊、會議、系統等使其正常運作的情境。",
  "example_sentence": "She runs a small software company.",
  "example_translation": "她經營一家小型軟體公司。",
  "usage_note": "Common with businesses, systems, meetings, and programs."
}
```

Two distinct Chinese fields:

- `chinese_translation` — the SHORTEST direct rendering of the English word for this meaning (1–3 short equivalents joined by `、` or `；`). Displayed prominently. May be empty for idioms without a direct equivalent.
- `chinese_explanation` — a longer Traditional Chinese sentence describing nuance, context, or connotation. Should not just repeat the translation.

The Vocabulary, Flashcards, and Needs Practice views render the concise `chinese_translation` first (large, bold, primary color), then the longer 說明 below.

## 6. Gemini API Integration

The app uses the Google Gemini API through the Python `google-genai` package.

Environment variables:

```bash
GEMINI_API_KEY="your_gemini_api_key_here"
# or
GOOGLE_API_KEY="your_google_api_key_here"
```

Optional model setting:

```bash
GEMINI_MODEL="gemini-2.5-flash"
```

If no Gemini API key is configured, the app uses a deterministic local fallback generator so the app remains runnable.

## 7. Review System

The user can start multiple review sessions per day. Each session creates a new review task. Sessions are independent and do not block each other.

Question types:

1. Choose the correct meaning for a word.
2. Choose the correct word for a meaning.

Each question has:

- one correct answer
- three distractors
- question type
- user answer
- correctness
- familiarity before answering
- familiarity after answering

Questions are shown one at a time. After each answer, the correct answer is highlighted before advancing to the next question.

When all questions in a session are answered, a summary modal appears with the session results.

For words with multiple meanings, the question text and the correct answer enumerate **all** meanings (numbered `1.`, `2.`, …) so the learner is tested on every sense of the word in a single question. The concise `chinese_translation` is preferred for display; older entries without it fall back to `chinese_explanation`.

## 8. Familiarity System

Each vocabulary item has a familiarity score from 0 to 5.

| Score | Meaning | Review Interval |
|---:|---|---:|
| 0 | New | 1 day |
| 1 | Very unfamiliar | 1 day |
| 2 | Unfamiliar | 2 days |
| 3 | Medium | 4 days |
| 4 | Familiar | 7 days |
| 5 | Mastered | 14 days |

Update rule:

```text
Correct answer   -> familiarity + 1
Incorrect answer -> familiarity - 1
```

The score is clamped to the range 0 to 5.

## 9. Review Session Generation

Each call to `POST /api/review/daily` creates a new session. Multiple sessions per day are allowed.

Word selection rule:

```text
1. Load all words whose next_review_at is today or earlier.
2. Sort by lower familiarity first, then by last reviewed date.
3. Select up to MAX_DAILY_QUESTIONS.
4. Generate one multiple-choice question per selected word.
```

Current default:

```text
MAX_DAILY_QUESTIONS = 20
```

`GET /api/review/today` returns the most recent session for today, or null if none exists.

## 10. Review Summary

After all questions in a session are answered, a summary modal pops up automatically.

The summary includes:

- Total questions answered
- Correct count
- Incorrect count
- Words improved
- Time spent

From the summary modal, the user can start another review session immediately or close to return to the start screen.

Definition of `words improved`:

```text
Number of answered questions where familiarity_after > familiarity_before
```

Time spent is calculated from the review task's start time to completion time. If the review is still in progress, it is calculated from start time to the current time.

## 10b. UI Tabs

The single-page app has four tabs:

1. **Home** — Overview dashboard with two charts and a Needs Practice list:
   - Pie chart of the familiarity distribution across all words (0–5).
   - Line chart for the last 30 days showing words *added*, words *improved* (familiarity went up), and words that *reached expert* (familiarity 5 for the first time).
   - Needs Practice grid: up to 6 words at familiarity 0 or 1, each rendered as a full card with concise Chinese translation, longer 說明, every meaning, and example sentences with translations.
   Chart.js is self-hosted under `/static/chart.umd.min.js` to avoid CDN-block issues.

2. **Add** — Generate an explanation via Gemini (or the local fallback) and save it. The form exposes only metadata fields (input_text, type, pronunciation, difficulty, similar, tags) plus a single JSON editor for the `meanings` array. There are no duplicate primary-meaning text fields.

3. **Vocabulary** — Searchable list of saved words. Each card shows every meaning with all per-meaning fields.

4. **Flashcards** — Click-to-flip cards ordered by ascending familiarity (least familiar first), tie-broken by oldest `last_reviewed_at`. Front shows the word; back shows every meaning. Keyboard shortcuts: `←` prev, `→` next, `Space`/`Enter` flip.

5. **Daily Review** — see sections 7–10.

## 11. Database Tables

### `vocabulary_items`

Stores vocabulary and review metadata. All per-meaning content (English, Chinese translation, Chinese explanation, examples, usage notes) lives inside `meanings_json` as the single source of truth — there are no duplicate columns.

Columns:

- `input_text`
- `type`
- `meanings_json` — JSON array of meaning objects (see section 5)
- `pronunciation`
- `similar_expressions_json`
- `difficulty`
- `tags_json`
- `familiarity`
- `review_count`
- `correct_count`
- `wrong_count`
- `last_reviewed_at`
- `next_review_at`
- `created_at`
- `updated_at`

A startup migration backfills `meanings_json` from any legacy per-meaning columns and drops them, so older databases upgrade in place on first run.

### `review_tasks`

Stores review sessions. Multiple rows per day are allowed.

Important fields:

- `review_date` (ISO datetime string used as unique identifier per session)
- `status`
- `total_questions`
- `correct_questions`
- `created_at`
- `started_at`
- `completed_at`

### `review_questions`

Stores generated review questions.

Important fields:

- `task_id`
- `vocab_id`
- `question_type`
- `question_text`
- `correct_answer`
- `options_json`
- `user_answer`
- `is_correct`
- `answered_at`
- `familiarity_before`
- `familiarity_after`

## 12. API Endpoints

```text
GET    /api/home/stats
POST   /api/vocab/generate
POST   /api/vocab
GET    /api/vocab
GET    /api/vocab/{id}
PUT    /api/vocab/{id}
DELETE /api/vocab/{id}
POST   /api/review/daily
GET    /api/review/today
POST   /api/review/questions/{question_id}/answer
GET    /api/review/tasks/{task_id}/summary
GET    /api/review/history
```

`GET /api/home/stats` returns the data backing the Home page:

```json
{
  "familiarity_distribution": [12, 4, 3, 6, 2, 1],
  "activity": {
    "labels": ["2026-04-26", "..."],
    "added":    [0, 1, ...],
    "improved": [0, 0, ...],
    "expert":   [0, 0, ...]
  },
  "needs_practice": [ /* up to 6 vocab items at familiarity 0 or 1 */ ]
}
```

## 13. Seed Data

The app includes a seed script with 50 vocabulary items.

Run:

```bash
python scripts/seed_sample_vocab.py
```

The script is idempotent and skips words that already exist.

## 14. Software Engineering Features

The project includes:

- Conda environment file
- Clear backend/frontend structure
- SQLite persistence
- Pydantic validation
- API routes separated from services
- Idempotent seed script
- Automated tests using pytest
- Local fallback generator for development
- README documentation
- SPEC documentation

## 15. Run Commands

Create environment:

```bash
conda env create -f environment.yml
conda activate personal-vocab-app
```

Run app:

```bash
uvicorn app.main:app --reload
```

Run tests:

```bash
pytest
```
