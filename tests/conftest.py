"""Fixtures compartilhadas entre todos os testes."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def rss_xml() -> str:
    return (FIXTURES_DIR / "rss_melhores_destinos.xml").read_text(encoding="utf-8")


@pytest.fixture()
def mock_session():
    """Mock de sessão SQLAlchemy para testes unitários."""
    session = MagicMock()
    session.query.return_value.filter_by.return_value.first.return_value = None
    session.add = MagicMock()
    session.flush = MagicMock()
    session.commit = MagicMock()
    return session


@pytest.fixture()
def future_date():
    return datetime(2026, 5, 31, tzinfo=UTC)


@pytest.fixture()
def past_date():
    return datetime(2025, 1, 1, tzinfo=UTC)
