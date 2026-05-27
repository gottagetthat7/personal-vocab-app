from __future__ import annotations

import base64
import binascii
import logging
import os
import secrets
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from .ai_service import generate_explanation
from .database import init_db
from .models import AnswerRequest, GenerateRequest, VocabCreate, VocabUpdate
from .review_service import answer_question, create_daily_task, get_task_summary, get_today_task, review_history
from .stats_service import get_home_stats
from .vocab_service import create_vocab, delete_vocab, get_vocab, list_vocab, update_vocab

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

logger = logging.getLogger("uvicorn.error")

# ---------------------------------------------------------------------------
# Optional HTTP Basic Auth (single shared account)
#
# If APP_USERNAME and APP_PASSWORD are both set in the environment, every
# request — including /, /static/*, and every /api/* — must carry a matching
# Authorization: Basic header. The browser handles the login prompt and
# caches the credentials per-device, so each device just enters it once.
#
# If either env var is unset, the middleware becomes a no-op so local
# development keeps working unchanged.
#
# Always serve over HTTPS in production: Basic Auth credentials travel as
# base64-encoded plaintext on every request.
# ---------------------------------------------------------------------------
_AUTH_USERNAME = os.getenv("APP_USERNAME") or ""
_AUTH_PASSWORD = os.getenv("APP_PASSWORD") or ""
_AUTH_ENABLED = bool(_AUTH_USERNAME and _AUTH_PASSWORD)


def _check_basic_auth(header_value: str | None) -> bool:
    """Return True iff the Authorization header matches the configured creds.

    Uses secrets.compare_digest to avoid timing side-channels.
    """
    if not header_value or not header_value.lower().startswith("basic "):
        return False
    try:
        decoded = base64.b64decode(header_value.split(" ", 1)[1], validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, IndexError):
        return False
    if ":" not in decoded:
        return False
    user, _, pw = decoded.partition(":")
    user_ok = secrets.compare_digest(user.encode("utf-8"), _AUTH_USERNAME.encode("utf-8"))
    pw_ok = secrets.compare_digest(pw.encode("utf-8"), _AUTH_PASSWORD.encode("utf-8"))
    return user_ok and pw_ok


app = FastAPI(title="Personal AI Vocabulary App")


@app.middleware("http")
async def basic_auth_middleware(request: Request, call_next):
    if _AUTH_ENABLED and not _check_basic_auth(request.headers.get("authorization")):
        return Response(
            status_code=401,
            content="Not authenticated",
            headers={"WWW-Authenticate": 'Basic realm="Personal Vocab App"'},
        )
    return await call_next(request)


if _AUTH_ENABLED:
    logger.info("HTTP Basic Auth enabled for all routes (user: %s).", _AUTH_USERNAME)
else:
    logger.warning(
        "HTTP Basic Auth is DISABLED — set APP_USERNAME and APP_PASSWORD env "
        "vars to require login. Safe for local dev; unsafe for public deployment."
    )

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/home/stats")
def api_home_stats():
    return get_home_stats()


@app.post("/api/vocab/generate")
def api_generate(req: GenerateRequest):
    return generate_explanation(req.text)


@app.post("/api/vocab")
def api_create_vocab(item: VocabCreate):
    try:
        return create_vocab(item)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/vocab")
def api_list_vocab(search: str | None = Query(default=None)):
    return list_vocab(search)


@app.get("/api/vocab/{vocab_id}")
def api_get_vocab(vocab_id: int):
    item = get_vocab(vocab_id)
    if not item:
        raise HTTPException(status_code=404, detail="Vocabulary item not found")
    return item


@app.put("/api/vocab/{vocab_id}")
def api_update_vocab(vocab_id: int, update: VocabUpdate):
    item = update_vocab(vocab_id, update)
    if not item:
        raise HTTPException(status_code=404, detail="Vocabulary item not found")
    return item


@app.delete("/api/vocab/{vocab_id}")
def api_delete_vocab(vocab_id: int):
    if not delete_vocab(vocab_id):
        raise HTTPException(status_code=404, detail="Vocabulary item not found")
    return {"ok": True}


@app.post("/api/review/daily")
def api_create_daily_review():
    return create_daily_task()


@app.get("/api/review/today")
def api_get_today_review():
    return get_today_task()


@app.post("/api/review/questions/{question_id}/answer")
def api_answer_question(question_id: int, req: AnswerRequest):
    result = answer_question(question_id, req.user_answer)
    if not result:
        raise HTTPException(status_code=404, detail="Question not found")
    return result


@app.get("/api/review/tasks/{task_id}/summary")
def api_review_summary(task_id: int):
    summary = get_task_summary(task_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Review task not found")
    return summary


@app.get("/api/review/history")
def api_review_history():
    return review_history()
