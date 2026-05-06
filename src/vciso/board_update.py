"""Monthly board update generator.

Takes the risk register state and generates a polished PDF for the board:
  - Cover (period, generated date, headline metrics)
  - Risk posture summary (open count by severity, deltas vs previous period)
  - Top 5 priorities this month with owner + target close
  - Risks closed this period (signal of progress)
  - Compliance attestations status
  - Narrative paragraph (LLM, with stub fallback)"""

from __future__ import annotations

import hashlib
import os
import uuid
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from weasyprint import HTML

from vciso.db import BoardUpdate, Risk, session

log = structlog.get_logger()

TEMPLATES = Path(__file__).resolve().parents[2] / "templates"
_env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "xml"]))


def _summarize(risks: list[Risk]) -> dict:
    open_risks = [r for r in risks if r.status != "closed"]
    closed_this_period = [
        r for r in risks
        if r.status == "closed" and r.closed_at
        and (date.today() - r.closed_at).days <= 35
    ]
    by_severity = Counter(r.severity for r in open_risks)
    by_category = Counter(r.category for r in open_risks)

    overdue = []
    for r in open_risks:
        if r.target_close_date and r.target_close_date < date.today():
            overdue.append(r)

    top5 = sorted(
        open_risks,
        key=lambda r: (
            {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(r.severity, 0),
            -((r.target_close_date - date.today()).days if r.target_close_date else 999),
        ),
        reverse=True,
    )[:5]

    return {
        "open_count": len(open_risks),
        "by_severity": dict(by_severity),
        "by_category": dict(by_category),
        "closed_this_period": closed_this_period,
        "overdue_count": len(overdue),
        "overdue": overdue,
        "top5": top5,
    }


async def _narrative(summary: dict) -> str:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sev = summary["by_severity"]
        return (
            f"Open risks total **{summary['open_count']}** "
            f"({sev.get('high', 0)} high, {sev.get('medium', 0)} medium, "
            f"{sev.get('low', 0)} low). "
            f"{len(summary['closed_this_period'])} closed this period. "
            f"{summary['overdue_count']} are past their target close date "
            f"and need either re-baselining or escalation."
        )
    from anthropic import AsyncAnthropic

    prompt = (
        "You are writing the executive narrative paragraph for a vCISO's monthly board update. "
        "Below is the risk register summary. Write 3-5 sentences, board-appropriate (not technical), "
        "leading with the headline number, mentioning the highest-severity gaps by NAME, and "
        "noting concretely what's improving. Do not invent numbers; use only those in the summary.\n\n"
        f"Open count: {summary['open_count']}\n"
        f"By severity: {summary['by_severity']}\n"
        f"Closed this period: {len(summary['closed_this_period'])} "
        f"({[r.title for r in summary['closed_this_period']]})\n"
        f"Top 5 priorities: {[(r.id, r.title, r.severity) for r in summary['top5']]}\n"
        f"Overdue: {summary['overdue_count']} ({[(r.id, r.title) for r in summary['overdue']]})\n"
    )
    client = AsyncAnthropic()
    msg = await client.messages.create(
        model=os.environ.get("VCISO_MODEL", "claude-sonnet-4-6"),
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()


async def generate_board_update(period: str | None = None) -> dict[str, Any]:
    period = period or datetime.now(timezone.utc).strftime("%Y-%m")
    update_id = uuid.uuid4().hex[:10]

    async with session() as s:
        risks = (await s.execute(select(Risk))).scalars().all()

    summary = _summarize(list(risks))
    narrative_md = await _narrative(summary)

    template = _env.get_template("board_update.html")
    html = template.render(
        period=period,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        update_id=update_id,
        narrative_md=narrative_md,
        **summary,
    )
    pdf_bytes = HTML(string=html, base_url=str(TEMPLATES)).write_pdf()

    out_dir = Path(os.environ.get("VCISO_OUT_DIR", "board-updates"))
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / f"{period}-board-update-{update_id}.pdf"
    pdf_path.write_bytes(pdf_bytes)
    sha = hashlib.sha256(pdf_bytes).hexdigest()
    pdf_path.with_suffix(".sha256").write_text(f"{sha}  {pdf_path.name}\n")

    # Persist
    md_text = (
        f"# Monthly board update — {period}\n\n"
        f"**Open risks:** {summary['open_count']}  "
        f"**Closed this period:** {len(summary['closed_this_period'])}  "
        f"**Overdue:** {summary['overdue_count']}\n\n"
        f"{narrative_md}"
    )
    async with session() as s:
        s.add(BoardUpdate(
            id=update_id, period=period, generated_at=datetime.now(timezone.utc).replace(tzinfo=None),
            markdown=md_text, pdf_path=str(pdf_path),
        ))
    log.info("vciso.board_update.generated", id=update_id, period=period, pdf=str(pdf_path), sha=sha[:12])
    return {"id": update_id, "period": period, "pdf_path": str(pdf_path), "sha256": sha, "summary": summary}
