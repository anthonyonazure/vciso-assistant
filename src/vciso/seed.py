"""Seed the risk register from risk_register/seed.yaml."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import structlog
import yaml

from vciso.db import Risk, init_db, session

log = structlog.get_logger()
SEED_PATH = Path(__file__).resolve().parents[2] / "risk_register" / "seed.yaml"


async def seed() -> None:
    await init_db()
    data = yaml.safe_load(SEED_PATH.read_text())["risks"]
    async with session() as s:
        for r in data:
            s.add(
                Risk(
                    id=r["id"],
                    title=r["title"],
                    category=r["category"],
                    severity=r["severity"],
                    status=r["status"],
                    likelihood=r.get("likelihood", "medium"),
                    impact=r.get("impact", "medium"),
                    owner=r.get("owner", "(unassigned)"),
                    discovered_at=_to_date(r["discovered_at"]),
                    discovered_by=r.get("discovered_by", "(unknown)"),
                    target_close_date=_to_date(r["target_close_date"]) if r.get("target_close_date") else None,
                    closed_at=_to_date(r["closed_at"]) if r.get("closed_at") else None,
                    notes=r.get("notes", "").strip(),
                    history=[],
                )
            )
    log.info("vciso.seed.complete", risks=len(data))


def _to_date(v) -> date:
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v))
