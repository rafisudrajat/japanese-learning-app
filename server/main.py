import random
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import sudachipy
import jamdict

import fsrs

from server.analyze import Token, analyze
from server.db import connect, delete_vocab, load_card, save_card, update_card, upsert_vocab
from server.quiz import (
    Question,
    VocabEntry,
    grade,
    make_cloze_question,
    make_meaning_question,
    make_reading_question,
    split_sentences,
)
from server.render import _contains_kanji
from server.scheduler import review
from server.export import export_apkg
from server.stats import compute_stats
from server.importer.extract import extract_text, fetch_and_extract
from server.importer.vocab_intake import collect_candidates

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"

app = FastAPI()
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

_tokenizer = sudachipy.Dictionary().create()
_thread_local = threading.local()


def _get_dictionary() -> jamdict.Jamdict:
    if not hasattr(_thread_local, "dictionary"):
        _thread_local.dictionary = jamdict.Jamdict()
    return _thread_local.dictionary


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


class StatsResponse(BaseModel):
    accuracy: float
    total_reviews: int
    reviews_per_day: dict[str, int]


class TriageRequest(BaseModel):
    lemma: str
    reading: str
    meaning: str
    pos: str
    decision: str


class TriageResponse(BaseModel):
    vocab_id: int
    status: str


class PasteImportRequest(BaseModel):
    title: str
    text: str


class CandidateResponse(BaseModel):
    lemma: str
    reading: str
    meanings: list[str]
    pos: str
    frequency: int


class ImportResponse(BaseModel):
    text_id: int
    tokens: list[TokenResponse]
    candidates: list[CandidateResponse]


class UrlImportRequest(BaseModel):
    url: str


class DomImportRequest(BaseModel):
    html: str


class QuizQuestionResponse(BaseModel):
    question_id: str
    kind: str
    prompt: str
    choices: list[str]
    context_html: str | None


class QuizAnswerRequest(BaseModel):
    question_id: str
    choice_index: int


class QuizAnswerResponse(BaseModel):
    correct: bool
    correct_index: int
    correct_answer: str


_pending: dict[str, Question] = {}


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
    tokens: list[Token] = analyze(req.text, _tokenizer, _get_dictionary(), known_lemmas=known)
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
        like = f"%{q}%"
        rows = conn.execute(
            "SELECT id, lemma, reading, primary_meaning, status FROM vocab "
            "WHERE lemma LIKE ? OR reading LIKE ? OR primary_meaning LIKE ?",
            (like, like, like),
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


@app.delete("/vocab/{vocab_id}")
def remove_vocab(vocab_id: int, conn: sqlite3.Connection = Depends(get_db)) -> dict[str, bool]:
    if not delete_vocab(conn, vocab_id):
        raise HTTPException(status_code=404, detail="Vocab not found")
    return {"deleted": True}


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


@app.post("/triage")
def triage_word(req: TriageRequest, conn: sqlite3.Connection = Depends(get_db)) -> TriageResponse:
    now = datetime.now(timezone.utc).isoformat()
    status = "learning" if req.decision == "keep" else "known"
    vocab_id = upsert_vocab(conn, req.lemma, req.reading, req.meaning, req.pos, now=now)
    conn.execute("UPDATE vocab SET status = ? WHERE id = ?", (status, vocab_id))
    conn.commit()
    if req.decision == "keep":
        existing = conn.execute("SELECT id FROM cards WHERE vocab_id = ?", (vocab_id,)).fetchone()
        if existing is None:
            save_card(conn, vocab_id, fsrs.Card())
    return TriageResponse(vocab_id=vocab_id, status=status)


@app.get("/stats-page")
def stats_page() -> FileResponse:
    return FileResponse(WEB_DIR / "stats.html")


@app.get("/stats")
def get_stats(conn: sqlite3.Connection = Depends(get_db)) -> StatsResponse:
    s = compute_stats(conn)
    return StatsResponse(
        accuracy=s.accuracy,
        total_reviews=s.total_reviews,
        reviews_per_day=s.reviews_per_day,
    )


@app.get("/import-page")
def import_page() -> FileResponse:
    return FileResponse(WEB_DIR / "import.html")


def _build_import_response(conn: sqlite3.Connection, text_id: int, text: str) -> ImportResponse:
    known = {row[0] for row in conn.execute("SELECT lemma FROM vocab").fetchall()}
    tokens: list[Token] = analyze(text, _tokenizer, _get_dictionary(), known_lemmas=known)
    candidates = collect_candidates(conn, tokens)
    return ImportResponse(
        text_id=text_id,
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
        ],
        candidates=[
            CandidateResponse(
                lemma=c.lemma,
                reading=c.reading,
                meanings=c.meanings,
                pos=c.pos,
                frequency=c.frequency,
            )
            for c in candidates
        ],
    )


@app.post("/import/paste")
def import_paste(
    req: PasteImportRequest, conn: sqlite3.Connection = Depends(get_db)
) -> ImportResponse:
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO texts (title, source_type, raw_text, created_at) VALUES (?, 'paste', ?, ?)",
        (req.title, req.text, now),
    )
    conn.commit()
    text_id = cur.lastrowid
    return _build_import_response(conn, text_id, req.text)


@app.post("/import/url")
def import_url(req: UrlImportRequest, conn: sqlite3.Connection = Depends(get_db)) -> ImportResponse:
    text = fetch_and_extract(req.url)
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO texts (title, source_type, source_url, raw_text, created_at) "
        "VALUES (?, 'url', ?, ?, ?)",
        (req.url, req.url, text, now),
    )
    conn.commit()
    text_id = cur.lastrowid
    return _build_import_response(conn, text_id, text)


@app.post("/import/dom")
def import_dom(req: DomImportRequest, conn: sqlite3.Connection = Depends(get_db)) -> ImportResponse:
    text = extract_text(req.html)
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO texts (title, source_type, raw_text, created_at) VALUES (?, 'dom', ?, ?)",
        ("Browser import", text, now),
    )
    conn.commit()
    text_id = cur.lastrowid
    return _build_import_response(conn, text_id, text)


@app.get("/export/apkg")
def export_apkg_route(conn: sqlite3.Connection = Depends(get_db)) -> FileResponse:
    import tempfile

    tmp = Path(tempfile.mkdtemp())
    path = tmp / "vocab.apkg"
    export_apkg(conn, path)
    return FileResponse(path, media_type="application/octet-stream", filename="vocab.apkg")


@app.get("/quiz/next")
def quiz_next(
    type: str = "meaning", conn: sqlite3.Connection = Depends(get_db)
) -> QuizQuestionResponse:
    rows = conn.execute(
        "SELECT lemma, reading, primary_meaning, pos FROM vocab "
        "WHERE status IN ('learning', 'known')",
    ).fetchall()
    pool = [
        VocabEntry(lemma=r[0], reading=r[1] or "", meaning=r[2] or "", pos=r[3] or "") for r in rows
    ]

    if len(pool) < 4:
        raise HTTPException(
            status_code=400, detail="Not enough vocabulary for a quiz (need at least 4)"
        )

    rng = random.Random()
    if type == "reading":
        kanji_pool = [e for e in pool if _contains_kanji(e.lemma)]
        if len(kanji_pool) < 4:
            raise HTTPException(
                status_code=400, detail="Not enough kanji vocabulary for a reading quiz"
            )
        target = rng.choice(kanji_pool)
        question = make_reading_question(target, pool, rng)
    elif type == "cloze":
        target = rng.choice(pool)
        text_row = conn.execute(
            "SELECT t.raw_text FROM texts t JOIN vocab v ON v.first_seen_text_id = t.id "
            "WHERE v.lemma = ?",
            (target.lemma,),
        ).fetchone()
        if text_row is None:
            text_row = conn.execute(
                "SELECT raw_text FROM texts ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if text_row is None:
            raise HTTPException(status_code=400, detail="No texts available for cloze quiz")
        sentences = split_sentences(text_row[0])
        matching = [s for s in sentences if target.lemma in s]
        if not matching:
            raise HTTPException(
                status_code=400, detail="No sentence found containing the target word"
            )
        sentence = rng.choice(matching)
        question = make_cloze_question(target, sentence, pool, _tokenizer, rng)
    else:
        target = rng.choice(pool)
        question = make_meaning_question(target, pool, rng)

    qid = str(uuid.uuid4())
    _pending[qid] = question

    return QuizQuestionResponse(
        question_id=qid,
        kind=question.kind,
        prompt=question.prompt,
        choices=list(question.choices),
        context_html=question.context_html,
    )


@app.post("/quiz/answer")
def quiz_answer(req: QuizAnswerRequest) -> QuizAnswerResponse:
    question = _pending.pop(req.question_id, None)
    if question is None:
        raise HTTPException(status_code=404, detail="Unknown or expired question_id")
    correct = grade(question, req.choice_index)
    return QuizAnswerResponse(
        correct=correct,
        correct_index=question.answer_index,
        correct_answer=question.choices[question.answer_index],
    )
