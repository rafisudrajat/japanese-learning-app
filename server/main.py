import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import sudachipy
import jamdict

import fsrs

from server.analyze import Token, analyze
from server.db import connect, load_card, update_card, upsert_vocab
from server.scheduler import review

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"

app = FastAPI()
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

_tokenizer = sudachipy.Dictionary().create()
_dictionary = jamdict.Jamdict()

HOST = "127.0.0.1"


def get_db() -> sqlite3.Connection:
    return connect(DB_PATH)


class AnalyzeRequest(BaseModel):
    text: str


class TokenResponse(BaseModel):
    surface: str
    reading_hiragana: str
    lemma: str
    meanings: list[str]
    pos: list[str]
    known: bool


class AnalyzeResponse(BaseModel):
    tokens: list[TokenResponse]


class SaveWordRequest(BaseModel):
    lemma: str
    reading: str
    meaning: str
    pos: str
    text_id: int | None = None


class SaveWordResponse(BaseModel):
    id: int
    created: bool


class VocabItem(BaseModel):
    id: int
    lemma: str
    reading: str | None
    primary_meaning: str | None
    status: str


class VocabListResponse(BaseModel):
    vocab: list[VocabItem]


class ReviewCardItem(BaseModel):
    card_db_id: int
    lemma: str
    reading: str | None
    primary_meaning: str | None


class ReviewQueueResponse(BaseModel):
    cards: list[ReviewCardItem]


class AnswerRequest(BaseModel):
    card_db_id: int
    rating: int


class AnswerResponse(BaseModel):
    next_due: str


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/vocab-page")
def vocab_page() -> FileResponse:
    return FileResponse(WEB_DIR / "vocab.html")


@app.post("/analyze")
def analyze_endpoint(
    req: AnalyzeRequest, conn: sqlite3.Connection = Depends(get_db)
) -> AnalyzeResponse:
    known = {row[0] for row in conn.execute("SELECT lemma FROM vocab").fetchall()}
    tokens: list[Token] = analyze(req.text, _tokenizer, _dictionary, known_lemmas=known)
    return AnalyzeResponse(
        tokens=[
            TokenResponse(
                surface=t.surface,
                reading_hiragana=t.reading_hiragana,
                lemma=t.lemma,
                meanings=t.meanings,
                pos=list(t.pos),
                known=t.known,
            )
            for t in tokens
        ]
    )


@app.post("/vocab")
def save_word(req: SaveWordRequest, conn: sqlite3.Connection = Depends(get_db)) -> SaveWordResponse:
    existing = conn.execute("SELECT id FROM vocab WHERE lemma = ?", (req.lemma,)).fetchone()
    now = datetime.now(timezone.utc).isoformat()
    vocab_id = upsert_vocab(conn, req.lemma, req.reading, req.meaning, req.pos, req.text_id, now)
    return SaveWordResponse(id=vocab_id, created=existing is None)


@app.get("/vocab")
def list_vocab(
    q: str | None = None, conn: sqlite3.Connection = Depends(get_db)
) -> VocabListResponse:
    if q:
        rows = conn.execute(
            "SELECT id, lemma, reading, primary_meaning, status FROM vocab WHERE lemma LIKE ?",
            (f"%{q}%",),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, lemma, reading, primary_meaning, status FROM vocab"
        ).fetchall()
    return VocabListResponse(
        vocab=[
            VocabItem(id=r[0], lemma=r[1], reading=r[2], primary_meaning=r[3], status=r[4])
            for r in rows
        ]
    )


@app.get("/review-page")
def review_page() -> FileResponse:
    return FileResponse(WEB_DIR / "review.html")


@app.get("/review/queue")
def review_queue(
    now: str | None = None, conn: sqlite3.Connection = Depends(get_db)
) -> ReviewQueueResponse:
    ts = now or datetime.now(timezone.utc).isoformat()
    rows = conn.execute(
        """
        SELECT c.id, v.lemma, v.reading, v.primary_meaning
        FROM cards c JOIN vocab v ON c.vocab_id = v.id
        WHERE c.due <= ?
        """,
        (ts,),
    ).fetchall()
    return ReviewQueueResponse(
        cards=[
            ReviewCardItem(card_db_id=r[0], lemma=r[1], reading=r[2], primary_meaning=r[3])
            for r in rows
        ]
    )


@app.post("/review/answer")
def review_answer(req: AnswerRequest, conn: sqlite3.Connection = Depends(get_db)) -> AnswerResponse:
    card = load_card(conn, req.card_db_id)
    now = datetime.now(timezone.utc)
    rating = fsrs.Rating(req.rating)
    new_card, log = review(card, rating, now)
    update_card(conn, req.card_db_id, new_card)
    conn.execute(
        "INSERT INTO review_logs (card_id, rating, reviewed_at) VALUES (?, ?, ?)",
        (req.card_db_id, req.rating, now.isoformat()),
    )
    conn.commit()
    return AnswerResponse(next_due=new_card.due.isoformat())
