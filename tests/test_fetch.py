from pathlib import Path

from server.importer.extract import decode_html, extract_text

FIXTURES = Path(__file__).parent / "fixtures"


def test_shift_jis_decodes() -> None:
    raw = (FIXTURES / "article_sjis.bin").read_bytes()
    text = decode_html(raw)
    assert "日本語" in text
    assert "テスト" in text


def test_extraction_strips_boilerplate() -> None:
    html = (FIXTURES / "article_with_nav.html").read_text()
    text = extract_text(html)
    assert "東京" in text
    assert "About Us" not in text
