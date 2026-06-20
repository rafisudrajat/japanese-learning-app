def test_dictionary_form_differs_from_surface(tokenizer):
    morphemes = tokenizer.tokenize("今日は寿司を食べた")
    verb = [m for m in morphemes if m.surface() == "食べ"][0]
    assert verb.dictionary_form() == "食べる"
    assert verb.reading_form() == "タベ"


def test_pos_identifies_particle(tokenizer):
    morphemes = tokenizer.tokenize("今日は寿司を食べた")
    wo = [m for m in morphemes if m.surface() == "を"][0]
    assert wo.part_of_speech()[0] == "助詞"
