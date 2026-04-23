"""Testes de deduplicação por fingerprint."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.processor.dedup import dedup_batch, find_existing, save_promotion
from src.processor.extractor import _fingerprint
from src.types import PromotionData


def _make_promo(**kwargs) -> PromotionData:
    defaults = dict(
        fingerprint="abc123",
        source_program="smiles",
        source_type="direct_scraper",
        source_url="https://www.smiles.com.br/promo",
        promo_type="transfer_bonus",
        origin_program="livelo",
        destination_program="smiles",
        bonus_percent=100.0,
        starts_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        ends_at=datetime(2026, 5, 31, tzinfo=timezone.utc),
        confidence=0.8,
    )
    defaults.update(kwargs)
    return PromotionData(**defaults)


def test_fingerprint_is_consistent():
    fp1 = _fingerprint(["livelo", "smiles", "100", "transfer_bonus", "2026-05-01"])
    fp2 = _fingerprint(["livelo", "smiles", "100", "transfer_bonus", "2026-05-01"])
    assert fp1 == fp2


def test_fingerprint_is_order_sensitive():
    fp1 = _fingerprint(["smiles", "livelo", "100", "transfer_bonus", "2026-05-01"])
    fp2 = _fingerprint(["livelo", "smiles", "100", "transfer_bonus", "2026-05-01"])
    assert fp1 != fp2


def test_fingerprint_length():
    fp = _fingerprint(["a", "b", "c"])
    assert len(fp) == 64


def test_save_promotion_new(mock_session):
    promo = _make_promo()
    mock_session.query.return_value.filter_by.return_value.first.return_value = None

    with patch("src.processor.dedup.find_existing", return_value=None):
        with patch("src.processor.dedup.Promotion") as MockPromotion:
            mock_db = MagicMock()
            MockPromotion.return_value = mock_db
            result, is_new = save_promotion(mock_session, promo)
            assert is_new is True
            mock_session.add.assert_called_once()


def test_save_promotion_existing(mock_session):
    promo = _make_promo()
    existing_mock = MagicMock()

    with patch("src.processor.dedup.find_existing", return_value=existing_mock):
        result, is_new = save_promotion(mock_session, promo)
        assert is_new is False
        assert result is existing_mock
        mock_session.add.assert_not_called()


def test_two_monitors_same_promo_yields_one_db_entry(mock_session):
    """2 monitores capturando a mesma promo = 1 linha no DB."""
    fp = _fingerprint(["livelo", "smiles", "100", "transfer_bonus", "2026-05-01"])
    promo1 = _make_promo(fingerprint=fp)
    promo2 = _make_promo(fingerprint=fp)

    mock_db = MagicMock()
    mock_db.fingerprint = fp

    # Primeira chamada: promo ainda não existe → salva. Segunda: já existe → dedup.
    with patch("src.processor.dedup.find_existing", side_effect=[None, mock_db]):
        with patch("src.processor.dedup.Promotion", return_value=mock_db):
            results = dedup_batch(mock_session, [promo1, promo2])

    assert len(results) == 2
    _, is_new1 = results[0]
    _, is_new2 = results[1]
    assert is_new1 is True
    assert is_new2 is False
    assert mock_session.add.call_count == 1
