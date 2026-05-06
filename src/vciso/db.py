"""SQLAlchemy async data layer for the risk register."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import AsyncIterator

from sqlalchemy import Date, DateTime, JSON, String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

DATABASE_URL = os.environ.get("VCISO_DATABASE_URL", "sqlite+aiosqlite:///./vciso.db")

_engine = create_async_engine(DATABASE_URL, echo=False, future=True)
_session = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


class Risk(Base):
    __tablename__ = "risks"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String)
    category: Mapped[str] = mapped_column(String, index=True)
    severity: Mapped[str] = mapped_column(String, index=True)  # low / medium / high / critical
    status: Mapped[str] = mapped_column(String, index=True)    # open / in_progress / monitoring / closed
    likelihood: Mapped[str] = mapped_column(String)
    impact: Mapped[str] = mapped_column(String)
    owner: Mapped[str] = mapped_column(String)
    discovered_at: Mapped[date] = mapped_column(Date)
    discovered_by: Mapped[str] = mapped_column(String)
    target_close_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    closed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str] = mapped_column(String)
    history: Mapped[list] = mapped_column(JSON, default=list)


class BoardUpdate(Base):
    __tablename__ = "board_updates"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    period: Mapped[str] = mapped_column(String, index=True)  # e.g. "2026-04"
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    markdown: Mapped[str] = mapped_column(String)
    pdf_path: Mapped[str | None] = mapped_column(String, nullable=True)


async def init_db() -> None:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def session() -> AsyncIterator[AsyncSession]:
    async with _session() as s:
        yield s
        await s.commit()
