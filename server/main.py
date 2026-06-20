from fastapi import FastAPI
from pydantic import BaseModel
import sudachipy
import jamdict

from server.analyze import Token, analyze

app = FastAPI()

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
