"""Tests for board update generation."""

import pytest

from vciso.board_update import generate_board_update


@pytest.mark.asyncio
async def test_board_update_creates_pdf_and_persists(seeded_db, tmp_path, monkeypatch):
    monkeypatch.setenv("VCISO_OUT_DIR", str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    result = await generate_board_update(period="2026-05")

    assert result["period"] == "2026-05"
    pdf_path = tmp_path / f"2026-05-board-update-{result['id']}.pdf"
    assert pdf_path.exists() and pdf_path.read_bytes()[:4] == b"%PDF"

    # Sidecar SHA-256 written
    sha = tmp_path / f"2026-05-board-update-{result['id']}.sha256"
    assert sha.exists()
    assert result["sha256"] in sha.read_text()


@pytest.mark.asyncio
async def test_summary_buckets_match_seed(seeded_db, tmp_path, monkeypatch):
    monkeypatch.setenv("VCISO_OUT_DIR", str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = await generate_board_update(period="2026-05")
    summary = result["summary"]

    # Seed has 9 open + 1 closed
    assert summary["open_count"] == 9

    # Top 5 prioritizes by severity
    top_severities = [r.severity for r in summary["top5"]]
    assert top_severities[0] in ("high", "critical")
