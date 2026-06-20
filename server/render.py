import html
import json

from server.analyze import Token


def _contains_kanji(text: str) -> bool:
    return any("一" <= c <= "鿿" for c in text)


def render_ruby(token: Token) -> str:
    escaped = html.escape(token.surface)
    if not _contains_kanji(token.surface):
        return escaped
    return f"<ruby>{escaped}<rt>{html.escape(token.reading_hiragana)}</rt></ruby>"


def render_word(token: Token) -> str:
    ruby = render_ruby(token)
    lemma_attr = html.escape(token.lemma, quote=True)
    reading_attr = html.escape(token.reading_hiragana, quote=True)
    meanings_attr = html.escape(json.dumps(token.meanings, ensure_ascii=False), quote=True)
    return (
        f'<span class="word" '
        f'data-lemma="{lemma_attr}" '
        f'data-reading="{reading_attr}" '
        f'data-meanings="{meanings_attr}">'
        f"{ruby}</span>"
    )
