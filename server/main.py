from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import sudachipy
import jamdict

from server.analyze import Token, analyze

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI()
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

_tokenizer = sudachipy.Dictionary().create()
_dictionary = jamdict.Jamdict()

HOST = "127.0.0.1"


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


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.post("/analyze")
def analyze_endpoint(req: AnalyzeRequest) -> AnalyzeResponse:
    tokens: list[Token] = analyze(req.text, _tokenizer, _dictionary)
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
