import os

os.environ.pop("PYTHONPATH", None)

import pytest
import sudachipy
import jamdict


@pytest.fixture(scope="session")
def tokenizer():
    return sudachipy.Dictionary().create()


@pytest.fixture(scope="session")
def dictionary():
    return jamdict.Jamdict()
