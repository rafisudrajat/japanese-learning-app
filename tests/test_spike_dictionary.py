def test_lookup_returns_english_gloss(dictionary):
    result = dictionary.lookup("猫")
    glosses = [
        str(g) for entry in result.entries for sense in entry.senses for g in sense.gloss
    ]
    assert any("cat" in g.lower() for g in glosses)

    result2 = dictionary.lookup("食べる")
    glosses2 = [
        str(g) for entry in result2.entries for sense in entry.senses for g in sense.gloss
    ]
    assert any("eat" in g.lower() for g in glosses2)


def test_lemma_lookup_beats_surface(dictionary):
    result = dictionary.lookup("食べる")
    assert len(result.entries) > 0
