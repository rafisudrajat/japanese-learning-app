import html

from server.analyze import Token


def _contains_kanji(text: str) -> bool:
    return any("一" <= c <= "鿿" for c in text)


def render_ruby(token: Token) -> str:
    escaped = html.escape(token.surface)
    if not _contains_kanji(token.surface):
        return escaped
    return f"<ruby>{escaped}<rt>{html.escape(token.reading_hiragana)}</rt></ruby>"
