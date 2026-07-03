"""AI Financial Advisor — Groq-powered chat endpoint."""

from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from advisor import nlp_engine
from database.db_manager import DatabaseManager
from webapp.backend.auth import get_current_user, get_db

router = APIRouter(prefix="/api/advisor", tags=["advisor"])


class HistoryMessage(BaseModel):
    role: str      # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: List[HistoryMessage] = []


@router.post("/chat")
def chat(req: ChatRequest, user=Depends(get_current_user),
         db: DatabaseManager = Depends(get_db)):
    history = [{"role": h.role, "content": h.content} for h in req.history]
    response = nlp_engine.answer(user["user_id"], req.message, history, db)
    return {"response": response}
