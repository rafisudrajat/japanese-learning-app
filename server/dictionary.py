from jamdict import Jamdict


def lookup_meanings(lemma: str, dictionary: Jamdict) -> list[str]:
    if not lemma or not lemma.strip():
        return []
    try:
        result = dictionary.lookup(lemma)
    except ValueError:
        # jamdict treats '%' and '?' as wildcards and rejects queries that are
        # only wildcards. Such lemmas (punctuation/symbols) have no entry anyway.
        return []
    return [str(g) for entry in result.entries for sense in entry.senses for g in sense.gloss]
