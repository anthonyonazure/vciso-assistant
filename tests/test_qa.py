"""Tests for vCISO Q&A — retrieval + stub answering."""

import pytest

from vciso.qa import answer_question, kb_retrieve, relevant_risks

KB = [
    {
        "id": "KB-MFA",
        "topics": ["mfa", "authentication"],
        "statement": "MFA enforced via Entra.",
    },
    {
        "id": "KB-CRYPTO",
        "topics": ["encryption_at_rest"],
        "statement": "AES-256 with KV.",
    },
]


def test_kb_retrieve_basic():
    hits = kb_retrieve("Do we use MFA?", KB)
    assert hits[0]["id"] == "KB-MFA"


@pytest.mark.asyncio
async def test_relevant_risks_returns_open_only(seeded_db):
    risks = await relevant_risks("storage public access")
    assert any(r["id"] == "R-001" for r in risks)
    # R-010 is closed; should NOT be returned even if it matches keywords
    assert all(r["id"] != "R-010" for r in risks)


@pytest.mark.asyncio
async def test_answer_includes_citations(seeded_db):
    # Match on a topic keyword so the lexical retriever scores it
    ans = await answer_question("explain our encryption_at_rest controls", kb=KB)
    assert "KB-CRYPTO" in ans["kb_citations"]


@pytest.mark.asyncio
async def test_answer_no_kb_no_risk_flags_followup(seeded_db):
    ans = await answer_question("what's our position on quantum cryptography?", kb=[])
    assert ans["needs_followup"] is True
    assert ans["confidence"] <= 0.4
