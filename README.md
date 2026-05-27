# Personal Gemini Vocabulary App

A runnable MVP for a personal vocabulary notebook with Google Gemini explanation generation and daily adaptive multiple-choice reviews.

## Features

- Add English words, phrases, idioms, and expressions
- Generate structured explanations using Google Gemini
  - Type
  - Primary English meaning
  - Primary Traditional Chinese explanation
  - Multiple meaning entries when a word has several meanings
  - Example sentence
  - Example translation
  - Usage note
  - Similar expressions
  - Difficulty
  - Tags
- Save, search, edit, and delete vocabulary items
- Daily multiple-choice review task
- Two question types:
  - Choose the correct meaning for a word
  - Choose the correct word for a meaning
- Familiarity-based review frequency
- Review summary after daily review:
  - Total questions answered
  - Correct count
  - Incorrect count
  - Words improved
  - Time spent
- Seed script with 50 sample vocabulary items
- Automated tests with `pytest`

## Tech Stack

- Backend: FastAPI
- Database: SQLite
- Frontend: HTML/CSS/JavaScript served by FastAPI
- Environment: Anaconda / Conda
- AI: Google Gemini API through `google-genai`
- Fallback: deterministic local generator if no Gemini API key is configured

## Run locally with venv

From the project root:

```bash
# one-time setup
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Copy the example env file and fill in your API key:

```bash
cp .env.example .env
# edit .env and set GEMINI_API_KEY
```

Start the app:

```bash
source .env
.venv/bin/uvicorn app.main:app --reload
```

Then open:

```text
http://127.0.0.1:8000
```

## Run locally with Anaconda

From the project root:

```bash
conda env create -f environment.yml
conda activate personal-vocab-app
source .env   # load your GEMINI_API_KEY
uvicorn app.main:app --reload
```

Then open:

```text
http://127.0.0.1:8000
```

## Enable Gemini generation

Create a Gemini API key in Google AI Studio, then set one of these environment variables before running the app:

```bash
export GEMINI_API_KEY="your_gemini_api_key_here"
```

Alternative:

```bash
export GOOGLE_API_KEY="your_google_api_key_here"
```

Optional model override:

```bash
export GEMINI_MODEL="gemini-2.5-flash"
```

The app still works without an API key by using a local fallback generator.

## Authentication (for public deployments)

If you deploy this app to the public internet, set both `APP_USERNAME` and
`APP_PASSWORD` env vars. When both are present, every request — including
the page itself, static assets, and every API endpoint — requires HTTP
Basic Auth matching those credentials.

```bash
export APP_USERNAME="me"
export APP_PASSWORD="$(openssl rand -base64 24)"
```

The browser handles the login prompt natively and caches the credentials
per-device, so each device only prompts on first visit. If either variable
is unset, the app runs with **no auth** — fine for local dev, unsafe for a
public deployment.

> **Always serve over HTTPS in production.** Basic Auth credentials are
> base64-encoded plaintext on every request; without TLS anyone on the
> network can read them.

## Seed sample vocabulary

The package already includes a sample local SQLite database with 50 vocabulary items. To recreate or add sample items manually:

```bash
conda activate personal-vocab-app
python scripts/seed_sample_vocab.py
```

The seed script is idempotent: it skips words that already exist.

## Run tests

With venv:

```bash
.venv/bin/python -m pytest tests/ -v
```

With Anaconda:

```bash
conda activate personal-vocab-app
pytest
```

Current test coverage includes:

- Creating, listing, updating, and deleting vocabulary
- Daily review task generation
- Familiarity/count updates after answering a question
- Review summary generation
- Multiple-meaning vocabulary handling

## Main API Endpoints

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

## Project Structure

```text
personal-vocab-app/
├── app/
│   ├── static/
│   │   ├── index.html
│   │   ├── styles.css
│   │   └── app.js
│   ├── ai_service.py
│   ├── database.py
│   ├── main.py
│   ├── models.py
│   ├── review_service.py
│   └── vocab_service.py
├── data/
│   └── vocab.db
├── scripts/
│   └── seed_sample_vocab.py
├── tests/
│   ├── conftest.py
│   ├── test_review_service.py
│   └── test_vocab_service.py
├── environment.yml
├── requirements.txt
├── pyproject.toml
├── SPEC.md
└── README.md
```

## Notes

The database file is created automatically at:

```text
data/vocab.db
```

For a clean database, delete `data/vocab.db`, restart the app, and run the seed script again.
