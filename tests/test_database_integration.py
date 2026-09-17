"""Optional PostgreSQL integration test.

Set PROMPTCHIVED_TEST_DATABASE_URL to a dedicated database whose name contains
"test". The guard prevents this test from ever targeting the application DB.
"""
import json
import os

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from promptchived.models import Conversation, Message, Source
from promptchived.services.import_jobs import _import_path
from promptchived.services.search import search


TEST_URL = os.getenv("PROMPTCHIVED_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_URL, reason="database integration is not configured")


def test_reimport_is_idempotent(tmp_path):
    assert "test" in (make_url(TEST_URL).database or "").lower()
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", TEST_URL)
    command.upgrade(config, "head")
    path = tmp_path / "conversations-000.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "stable-conversation",
                    "title": "Idempotent",
                    "current_node": "node-1",
                    "mapping": {
                        "node-1": {
                            "id": "node-1",
                            "parent": None,
                            "message": {
                                "id": "stable-message",
                                "author": {"role": "user"},
                                "create_time": 1_700_000_000,
                                "content": {"content_type": "text", "parts": ["hello"]},
                                "metadata": {},
                            },
                        }
                    },
                }
            ]
        ),
        encoding="utf-8",
    )
    engine = create_engine(TEST_URL)
    connection = engine.connect()
    transaction = connection.begin()
    try:
        with Session(bind=connection) as session:
            source = Source(name="fixture", provider="chatgpt", root_path=str(tmp_path))
            session.add(source)
            session.flush()
            first = _import_path(session, source, path)
            second = _import_path(session, source, path)
            assert first[:2] == (1, 1)
            assert second == (0, 0, True)
            assert session.scalar(select(func.count()).select_from(Conversation)) == 1
            assert session.scalar(select(func.count()).select_from(Message)) == 1
            result = search(session, "hello", mode="fulltext")
            assert len(result["items"]) == 1
    finally:
        transaction.rollback()
        connection.close()
        engine.dispose()
