from server.analyze import Token
from server.render import render_ruby, render_word


def _make_token(surface: str, reading_hiragana: str, **kw: object) -> Token:
    return Token(
        surface=surface,
        reading_hiragana=reading_hiragana,
        lemma=kw.get("lemma", surface),
        meanings=kw.get("meanings", []),
        pos=kw.get("pos", ("名詞",)),
        known=kw.get("known", False),
    )


def test_ruby_for_kanji_word() -> None:
    t = _make_token("猫", "ねこ")
    assert render_ruby(t) == "<ruby>猫<rt>ねこ</rt></ruby>"


def test_no_ruby_for_kana() -> None:
    t = _make_token("ねこ", "ねこ")
    assert render_ruby(t) == "ねこ"


def test_surface_is_escaped() -> None:
    t = _make_token("<猫>", "ねこ")
    result = render_ruby(t)
    assert "&lt;" in result
    assert "&gt;" in result
    assert "<猫>" not in result


def test_word_payload_carries_meanings() -> None:
    t = _make_token("猫", "ねこ", meanings=["cat"])
    result = render_word(t)
    assert 'data-lemma="猫"' in result
    assert 'data-reading="ねこ"' in result
    assert "cat" in result


def test_empty_meanings_payload() -> None:
    t = _make_token("猫", "ねこ", meanings=[])
    result = render_word(t)
    assert 'data-meanings="[]"' in result
