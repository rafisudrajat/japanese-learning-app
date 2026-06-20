import os
import sqlite3

os.environ.pop("PYTHONPATH", None)

from pathlib import Path

import pytest
import sudachipy
import jamdict

from server.db import connect


@pytest.fixture(scope="session")
def tokenizer():
    return sudachipy.Dictionary().create()


@pytest.fixture(scope="session")
def dictionary():
    return jamdict.Jamdict()


@pytest.fixture()
def db(tmp_path: Path) -> sqlite3.Connection:
    conn = connect(tmp_path / "test.db")
    yield conn
    conn.close()
