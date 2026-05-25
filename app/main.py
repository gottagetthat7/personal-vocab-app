from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
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

app = FastAPI(title="Personal AI Vocabulary App")
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
