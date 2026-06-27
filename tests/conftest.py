import pytest

from jester import db


@pytest.fixture
def conn():
    """A fresh in-memory database with the schema applied, per test."""
    c = db.connect(":memory:")
    db.init_db(c)
    yield c
    c.close()
