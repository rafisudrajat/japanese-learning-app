"""Shared HTTP-test harness for the integration suite.

These fixtures replace the old module-level globals in ``test_api.py`` that
``test_import.py`` used to import directly. Anything under ``tests/integration/``
gets ``client`` (a ``TestClient`` wired to a throwaway SQLite file), ``api_db``
(a per-test clean of that file, returning its path), and ``make_due_card``.
"""

import sqlite3
import tempfile
from pathlib import Path
from typing import Callable

import fsrs
import pytest
from starlette.testclient import TestClient

from server.db import connect, save_card, upsert_vocab
from server.main import app, get_db

_TABLES = ("review_logs", "cards", "vocab", "texts")


@pytest.fixture(scope="session")
def api_db_path() -> Path:
    return Path(tempfile.mkdtemp()) / "test_api.db"


@pytest.fixture(scope="session")
def client(api_db_path: Path) -> TestClient:
    def _override_db() -> sqlite3.Connection:
        return connect(api_db_path)

    app.dependency_overrides[get_db] = _override_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def api_db(api_db_path: Path) -> Path:
    """Empty every table before a test, then hand back the db path to inspect."""
    conn = connect(api_db_path)
    for table in _TABLES:
        conn.execute(f"DELETE FROM {table}")
    conn.commit()
    conn.close()
    return api_db_path


@pytest.fixture()
def make_due_card(api_db_path: Path) -> Callable[..., int]:
    def _make(lemma: str = "猫") -> int:
        conn = connect(api_db_path)
        vocab_id = upsert_vocab(conn, lemma, "ねこ", "cat", "名詞", now="2025-01-01T00:00:00")
        card_db_id = save_card(conn, vocab_id, fsrs.Card())
        conn.close()
        return card_db_id

    return _make
