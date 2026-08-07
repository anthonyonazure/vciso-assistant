"""Policy Q&A — answer ad-hoc questions from KB + risk register.

Two retrieval surfaces:
  1. Knowledge base (policy statements with citation ids)
  2. Risk register (open risks tagged with categories)

The composer cites both. If neither has direct support, the answer is
'I don't see this in our policies or risk register; please add it.'"""

from __future__ import annotations

import json
import os
from pathlib import Path

import yaml
from sqlalchemy import select

from vciso.db import Risk, session
from vciso.llm import first_text


def load_kb(path: str | None = None) -> list[dict]:
    p = Path(
        path or os.environ.get("VCISO_KNOWLEDGE_BASE", "knowledge_base/cyber_co.yaml")
    )
    return yaml.safe_load(p.read_text())["knowledge"]


async def relevant_risks(question: str, *, top_k: int = 3) -> list[dict]:
    q_lower = question.lower()
    async with session() as s:
        all_risks = (await s.execute(select(Risk))).scalars().all()
    scored = []
    for r in all_risks:
        if r.status == "closed":
            continue
        score = 0
        text = f"{r.title} {r.category} {r.notes}".lower()
        for word in q_lower.split():
            if len(word) > 3 and word in text:
                score += 1
        if score:
            scored.append((score, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [_risk_to_dict(r) for _, r in scored[:top_k]]


def _risk_to_dict(r: Risk) -> dict:
    return {
        "id": r.id,
        "title": r.title,
        "severity": r.severity,
        "status": r.status,
        "owner": r.owner,
        "target_close_date": r.target_close_date.isoformat()
        if r.target_close_date
        else None,
    }


def kb_retrieve(question: str, kb: list[dict], top_k: int = 3) -> list[dict]:
    """Reuse the same lexical+topic logic as SQR."""
    try:
        # SQR is an optional sibling project; the import has to sit inside the
        # try or the ImportError escapes before the fallback below can run.
        from sqr.retrieval import retrieve  # type: ignore[import-not-found]

        return retrieve(question, kb, top_k=top_k)
    except ImportError:
        # If SQR isn't installed, do a lightweight inline version
        q_words = {w.lower() for w in question.split() if len(w) > 3}
        scored = []
        for entry in kb:
            text = entry["statement"].lower() + " " + " ".join(entry.get("topics", []))
            score = sum(1 for w in q_words if w in text)
            for topic in entry.get("topics", []):
                if topic.replace("_", " ") in question.lower():
                    score += 3
            if score:
                scored.append((score, entry))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:top_k]]


_PROMPT = """You are the company's vCISO answering an ad-hoc question from an engineer or executive over Slack.

Question:
{question}

Knowledge-base entries the retriever surfaced (use ONLY these):
{kb_block}

Currently open risks that may be relevant:
{risks_block}

Rules:
1. Cite KB entry ids you use (KB-XXX) and risk ids you reference (R-XXX).
2. Be specific. Engineers have read 100 vague policy docs; they want the
   answer + the policy reference + the exception path if any.
3. If the question can't be answered from the inputs, say so explicitly:
   "I don't see this in our policies or risk register — please open a
   policy ticket." Never invent.
4. Keep it under 6 sentences. Slack-readable.

Output JSON:
{{
  "answer": "...",
  "kb_citations": ["KB-IAM-MFA"],
  "risk_citations": ["R-003"],
  "confidence": 0.85,
  "needs_followup": false
}}"""


def _stub_answer(question: str, kb_hits: list[dict], risks: list[dict]) -> dict:
    if not kb_hits and not risks:
        return {
            "answer": (
                "I don't see this in our policies or risk register. Please open "
                "a policy ticket so we can address it formally."
            ),
            "kb_citations": [],
            "risk_citations": [],
            "confidence": 0.2,
            "needs_followup": True,
        }
    parts = []
    if kb_hits:
        parts.append(kb_hits[0]["statement"].strip().split("\n")[0])
    if risks:
        parts.append(
            f"Open risk to flag: {risks[0]['title']} ({risks[0]['severity']}, owner: {risks[0]['owner']})."
        )
    return {
        "answer": " ".join(parts),
        "kb_citations": [h["id"] for h in kb_hits[:2]],
        "risk_citations": [r["id"] for r in risks[:2]],
        "confidence": 0.6 if kb_hits else 0.45,
        "needs_followup": not kb_hits,
    }


async def answer_question(question: str, *, kb: list[dict] | None = None) -> dict:
    kb = kb if kb is not None else load_kb()
    kb_hits = kb_retrieve(question, kb)
    risks = await relevant_risks(question)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        return _stub_answer(question, kb_hits, risks)

    from anthropic import AsyncAnthropic

    kb_block = (
        "\n\n".join(f"[{e['id']}] {e['statement'].strip()}" for e in kb_hits)
        or "(none)"
    )
    risks_block = (
        "\n".join(
            f"- [{r['id']}] {r['title']} ({r['severity']}, {r['status']}, owner: {r['owner']})"
            for r in risks
        )
        or "(none)"
    )
    client = AsyncAnthropic()
    msg = await client.messages.create(
        model=os.environ.get("VCISO_MODEL", "claude-sonnet-4-6"),
        max_tokens=600,
        messages=[
            {
                "role": "user",
                "content": _PROMPT.format(
                    question=question,
                    kb_block=kb_block,
                    risks_block=risks_block,
                ),
            }
        ],
    )
    text = first_text(msg).strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        text = text.removeprefix("json")
        text = text.rsplit("```", 1)[0].strip()
    return json.loads(text)
