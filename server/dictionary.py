from jamdict import Jamdict


def lookup_meanings(lemma: str, dictionary: Jamdict) -> list[str]:
    result = dictionary.lookup(lemma)
    return [str(g) for entry in result.entries for sense in entry.senses for g in sense.gloss]
