import random
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
import sudachipy
import jamdict

import fsrs

from server.analyze import Token, analyze
from server.db import (
    add_vocab_meanings,
    connect,
    delete_vocab,
    get_setting,
    get_vocab_meanings,
    load_card,
    save_card,
    set_setting,
    set_vocab_meanings,
    update_card,
    update_vocab,
    upsert_vocab,
)
from server.quiz import (
    Question,
    VocabEntry,
    grade,
    make_cloze_question,
    make_meaning_question,
    make_mixed_question,
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


class NoCacheStaticMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store"
        return response


app.add_middleware(NoCacheStaticMiddleware)
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
    meanings: list[str]
    pos: str
    text_id: int | None = None


class SaveWordResponse(BaseModel):
    id: int
    created: bool


class VocabItem(BaseModel):
    id: int
    lemma: str
    reading: str | None
    meanings: list[str]
    status: str


class VocabListResponse(BaseModel):
    vocab: list[VocabItem]


class UpdateVocabRequest(BaseModel):
    reading: str | None = None
    meanings: list[str] | None = None
    pos: str | None = None


class ReviewCardItem(BaseModel):
    card_db_id: int
    lemma: str
    reading: str | None
    meanings: list[str]


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
    meanings: list[str]
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
    count_as_review: bool = False


class QuizAnswerResponse(BaseModel):
    correct: bool
    correct_index: int
    correct_answer: str


class ThemeRequest(BaseModel):
    theme: Literal["light", "dark"]


class ThemeResponse(BaseModel):
    theme: str


_pending: dict[str, Question] = {}


def _lookup_frequency(lemma: str) -> int:
    jmd = _get_dictionary()
    try:
        result = jmd.lookup(lemma)
    except ValueError:
        return 0
    for entry in result.entries:
        for form in list(entry.kanji_forms) + list(entry.kana_forms):
            for tag in form.pri:
                if tag.startswith("nf"):
                    try:
                        return int(tag[2:])
                    except ValueError:
                        continue
    return 0


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


def _vocab_item(conn: sqlite3.Connection, row: tuple) -> VocabItem:
    return VocabItem(
        id=row[0], lemma=row[1], reading=row[2],
        meanings=get_vocab_meanings(conn, row[0]), status=row[3],
    )


@app.post("/vocab")
def save_word(req: SaveWordRequest, conn: sqlite3.Connection = Depends(get_db)) -> SaveWordResponse:
    existing = conn.execute("SELECT id FROM vocab WHERE lemma = ?", (req.lemma,)).fetchone()
    now = datetime.now(timezone.utc).isoformat()
    vocab_id = upsert_vocab(conn, req.lemma, req.reading, req.pos, req.text_id, now)
    add_vocab_meanings(conn, vocab_id, req.meanings)
    return SaveWordResponse(id=vocab_id, created=existing is None)


@app.get("/vocab")
def list_vocab(
    q: str | None = None, conn: sqlite3.Connection = Depends(get_db)
) -> VocabListResponse:
    if q:
        like = f"%{q}%"
        rows = conn.execute(
            "SELECT DISTINCT v.id, v.lemma, v.reading, v.status FROM vocab v "
            "LEFT JOIN vocab_meanings vm ON v.id = vm.vocab_id "
            "LEFT JOIN meanings m ON vm.meaning_id = m.id "
            "WHERE v.lemma LIKE ? OR v.reading LIKE ? OR m.text LIKE ?",
            (like, like, like),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, lemma, reading, status FROM vocab"
        ).fetchall()
    return VocabListResponse(vocab=[_vocab_item(conn, r) for r in rows])


@app.put("/vocab/{vocab_id}")
def edit_vocab(
    vocab_id: int, req: UpdateVocabRequest, conn: sqlite3.Connection = Depends(get_db)
) -> VocabItem:
    exists = conn.execute("SELECT id FROM vocab WHERE id = ?", (vocab_id,)).fetchone()
    if not exists:
        raise HTTPException(status_code=404, detail="Vocab not found")
    update_vocab(conn, vocab_id, reading=req.reading, pos=req.pos)
    if req.meanings is not None:
        set_vocab_meanings(conn, vocab_id, req.meanings)
    row = conn.execute(
        "SELECT id, lemma, reading, status FROM vocab WHERE id = ?",
        (vocab_id,),
    ).fetchone()
    return _vocab_item(conn, row)


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
        SELECT c.id, v.id, v.lemma, v.reading
        FROM cards c JOIN vocab v ON c.vocab_id = v.id
        WHERE c.due <= ?
        """,
        (ts,),
    ).fetchall()
    return ReviewQueueResponse(
        cards=[
            ReviewCardItem(
                card_db_id=r[0], lemma=r[2], reading=r[3],
                meanings=get_vocab_meanings(conn, r[1]),
            )
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
    vocab_id = upsert_vocab(conn, req.lemma, req.reading, req.pos, now=now)
    add_vocab_meanings(conn, vocab_id, req.meanings)
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


@app.get("/api/settings/theme")
def get_theme(conn: sqlite3.Connection = Depends(get_db)) -> ThemeResponse:
    theme = get_setting(conn, "theme", "light")
    return ThemeResponse(theme=theme)


@app.put("/api/settings/theme")
def set_theme(req: ThemeRequest, conn: sqlite3.Connection = Depends(get_db)) -> ThemeResponse:
    set_setting(conn, "theme", req.theme)
    return ThemeResponse(theme=req.theme)


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


@app.get("/quiz-page")
def quiz_page() -> FileResponse:
    return FileResponse(WEB_DIR / "quiz.html")


@app.get("/quiz/next")
def quiz_next(
    type: str = "meaning", conn: sqlite3.Connection = Depends(get_db)
) -> QuizQuestionResponse:
    rows = conn.execute(
        "SELECT id, lemma, reading, pos FROM vocab "
        "WHERE status IN ('learning', 'known')",
    ).fetchall()
    pool = [
        VocabEntry(
            lemma=r[1],
            reading=r[2] or "",
            meaning="; ".join(get_vocab_meanings(conn, r[0])),
            pos=r[3] or "",
            frequency=_lookup_frequency(r[1]),
        )
        for r in rows
    ]

    if len(pool) < 4:
        raise HTTPException(
            status_code=400, detail="Not enough vocabulary for a quiz (need at least 4)"
        )

    rng = random.Random()
    if type == "mixed":
        question = make_mixed_question(pool, rng)
    elif type == "reading":
        kanji_pool = [e for e in pool if _contains_kanji(e.lemma)]
        if len(kanji_pool) < 4:
            raise HTTPException(
                status_code=400, detail="Not enough kanji vocabulary for a reading quiz"
            )
        target = rng.choice(kanji_pool)
        question = make_reading_question(target, pool, rng)
    elif type == "cloze":
        all_texts = conn.execute("SELECT raw_text FROM texts").fetchall()
        if not all_texts:
            raise HTTPException(status_code=400, detail="No texts available for cloze quiz")
        all_sentences = []
        for row in all_texts:
            all_sentences.extend(split_sentences(row[0]))

        candidates = list(pool)
        rng.shuffle(candidates)
        question = None
        for target in candidates:
            matching = [s for s in all_sentences if target.lemma in s]
            if matching:
                sentence = rng.choice(matching)
                question = make_cloze_question(target, sentence, pool, _tokenizer, rng)
                break
        if question is None:
            raise HTTPException(
                status_code=400,
                detail="No sentence found containing any vocabulary word",
            )
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
def quiz_answer(
    req: QuizAnswerRequest, conn: sqlite3.Connection = Depends(get_db)
) -> QuizAnswerResponse:
    question = _pending.pop(req.question_id, None)
    if question is None:
        raise HTTPException(status_code=404, detail="Unknown or expired question_id")
    correct = grade(question, req.choice_index)

    if req.count_as_review and question.target_lemma:
        row = conn.execute(
            "SELECT c.id FROM cards c JOIN vocab v ON c.vocab_id = v.id WHERE v.lemma = ?",
            (question.target_lemma,),
        ).fetchone()
        if row:
            card_db_id = row[0]
            card = load_card(conn, card_db_id)
            now = datetime.now(timezone.utc)
            rating = fsrs.Rating(3 if correct else 1)
            new_card, _ = review(card, rating, now)
            update_card(conn, card_db_id, new_card)
            conn.execute(
                "INSERT INTO review_logs (card_id, rating, reviewed_at) VALUES (?, ?, ?)",
                (card_db_id, rating.value, now.isoformat()),
            )
            conn.commit()

    return QuizAnswerResponse(
        correct=correct,
        correct_index=question.answer_index,
        correct_answer=question.choices[question.answer_index],
    )
