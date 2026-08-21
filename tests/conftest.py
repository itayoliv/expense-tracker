"""Shared fixtures: isolated SQLite DB per test."""

from __future__ import annotations

import pytest

import db
from app import app


@pytest.fixture(autouse=True)
def _no_real_openai(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def _blocked(*_args, **_kwargs):
        raise AssertionError("ask_openai must be mocked in tests")

    monkeypatch.setattr("gpt_sort.ask_openai", _blocked)


@pytest.fixture()
def client(tmp_path):
    db.configure_engine(tmp_path / "expenses.db")
    db.init_db()
    with db.get_session() as session:
        db.seed_defaults(session)
        session.commit()
    app.config["TESTING"] = True
    app._db_ready = True
    with app.test_client() as test_client:
        yield test_client
    app._db_ready = False
