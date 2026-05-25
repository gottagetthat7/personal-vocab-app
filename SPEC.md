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

Each vocabulary item contains:

- `input_text`
- `type`
- `english_meaning`
- `chinese_explanation`
- `meanings`
- `example_sentence`
- `example_translation`
- `pronunciation`
- `usage_note`
- `similar_expressions`
- `difficulty`
- `tags`
- `familiarity`
- review metadata

## 5. Multiple Meanings

Some English words have multiple meanings. The app handles this with a `meanings` array.

Each meaning entry contains:

```json
{
  "part_of_speech": "verb",
  "english_meaning": "To operate or manage something.",
  "chinese_explanation": "經營、管理或運作。",
  "example_sentence": "She runs a small software company.",
  "example_translation": "她經營一家小型軟體公司。",
  "usage_note": "Common with businesses, systems, meetings, and programs."
}
```

The top-level `english_meaning` and `chinese_explanation` store the primary meaning for quick display and backward compatibility. The `meanings` array stores richer meaning-level details.

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

## 11. Database Tables

### `vocabulary_items`

Stores vocabulary and review metadata.

Important fields:

- `input_text`
- `type`
- `english_meaning`
- `chinese_explanation`
- `meanings_json`
- `example_sentence`
- `example_translation`
- `pronunciation`
- `usage_note`
- `similar_expressions_json`
- `difficulty`
- `tags_json`
- `familiarity`
- `review_count`
- `correct_count`
- `wrong_count`
- `last_reviewed_at`
- `next_review_at`

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
