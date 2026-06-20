import urllib.request

import trafilatura


def decode_html(raw_bytes: bytes) -> str:
    for encoding in ("utf-8", "shift_jis", "euc-jp", "iso-2022-jp"):
        try:
            return raw_bytes.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw_bytes.decode("utf-8", errors="replace")


def extract_text(html: str) -> str:
    result = trafilatura.extract(html)
    return result or ""


def fetch_and_extract(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw_bytes = resp.read()
    html = decode_html(raw_bytes)
    return extract_text(html)
