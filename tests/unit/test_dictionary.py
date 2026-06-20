from jamdict import Jamdict

from server.dictionary import lookup_meanings


def test_known_word_has_meaning(dictionary: Jamdict) -> None:
    glosses: list[str] = lookup_meanings("猫", dictionary)
    assert any("cat" in g.lower() for g in glosses)


def test_unknown_word_returns_empty(dictionary: Jamdict) -> None:
    glosses: list[str] = lookup_meanings("ぬるぽぽぽ", dictionary)
    assert glosses == []
