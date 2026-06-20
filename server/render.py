import html
import json

from server.analyze import Token


def _is_kanji(c: str) -> bool:
    return "一" <= c <= "鿿"


def _contains_kanji(text: str) -> bool:
    return any(_is_kanji(c) for c in text)


def align_ruby(surface: str, reading_hiragana: str) -> list[tuple[str, str | None]]:
    if not _contains_kanji(surface):
        return [(surface, None)]

    runs: list[tuple[str, bool]] = []
    current = ""
    current_is_kanji: bool | None = None
    for c in surface:
        k = _is_kanji(c)
        if k != current_is_kanji:
            if current:
                runs.append((current, current_is_kanji or False))
            current = c
            current_is_kanji = k
        else:
            current += c
    if current:
        runs.append((current, current_is_kanji or False))

    if all(is_k for _, is_k in runs):
        return [(surface, reading_hiragana)]

    remaining = reading_hiragana
    result: list[tuple[str, str | None]] = []

    for text, is_k in runs:
        if not is_k:
            if remaining.endswith(text):
                remaining = remaining[: -len(text)]
            elif remaining.startswith(text):
                remaining = remaining[len(text) :]
                result.append((text, None))
                continue
            else:
                return [(surface, reading_hiragana)]
        else:
            result.append((text, None))

    final: list[tuple[str, str | None]] = []
    reading_idx = 0
    for text, is_k in runs:
        if not is_k:
            final.append((text, None))
        else:
            kana_after = ""
            for t2, k2 in runs[runs.index((text, is_k)) + 1 :]:
                if not k2:
                    kana_after = t2
                    break
            if kana_after and kana_after in remaining[reading_idx:]:
                pos = remaining.index(kana_after, reading_idx)
                kanji_reading = remaining[reading_idx:pos]
                final.append((text, kanji_reading))
                reading_idx = pos
            else:
                kanji_reading = remaining[reading_idx:]
                final.append((text, kanji_reading))
                reading_idx = len(remaining)

    return final


def render_ruby(token: Token) -> str:
    escaped = html.escape(token.surface)
    if not _contains_kanji(token.surface):
        return escaped
    segments = align_ruby(token.surface, token.reading_hiragana)
    parts: list[str] = []
    for base, rt in segments:
        escaped_base = html.escape(base)
        if rt is not None:
            parts.append(f"<ruby>{escaped_base}<rt>{html.escape(rt)}</rt></ruby>")
        else:
            parts.append(escaped_base)
    return "".join(parts)


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
