"""Persistence for investigations and scenario runs (SQLite by default, PostgreSQL via DATABASE_URL)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from app.config import get_settings
from app.models.schemas import Investigation


class Base(DeclarativeBase):
    pass


class InvestigationRow(Base):
    __tablename__ = "investigations"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    ticker: Mapped[Optional[str]] = mapped_column(String(10), index=True)
    state: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[str] = mapped_column(Text)


class AppStateRow(Base):
    __tablename__ = "app_state"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class WatchlistRow(Base):
    __tablename__ = "watchlist"
    ticker: Mapped[str] = mapped_column(String(10), primary_key=True)
    data_mode: Mapped[str] = mapped_column(String(16))
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    accessions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON list from the last check
    last_report: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON


class DecisionRow(Base):
    __tablename__ = "decisions"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    ticker: Mapped[str] = mapped_column(String(10), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[str] = mapped_column(Text)


class BoardRow(Base):
    __tablename__ = "boards"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[str] = mapped_column(Text)


class ScenarioRunRow(Base):
    __tablename__ = "scenario_runs"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[str] = mapped_column(Text)


_url = get_settings().database_url
if _url.startswith("postgresql://"):
    _url = _url.replace("postgresql://", "postgresql+psycopg://", 1)
engine = create_engine(_url, connect_args={"check_same_thread": False} if _url.startswith("sqlite") else {})
Base.metadata.create_all(engine)


def utc(dt: Optional[datetime]) -> Optional[datetime]:
    """SQLite stores datetimes without a timezone; everything Parallax writes is UTC, so say so."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def save_investigation(inv: Investigation) -> None:
    with Session(engine) as s:
        row = s.get(InvestigationRow, inv.id)
        payload = inv.model_dump_json()
        if row is None:
            s.add(InvestigationRow(id=inv.id, ticker=inv.ticker, state=inv.state.value, created_at=inv.created_at,
                                   updated_at=inv.updated_at, payload=payload))
        else:
            row.ticker, row.state, row.updated_at, row.payload = inv.ticker, inv.state.value, inv.updated_at, payload
        s.commit()


def load_investigation(inv_id: str) -> Optional[Investigation]:
    with Session(engine) as s:
        row = s.get(InvestigationRow, inv_id)
        return Investigation.model_validate_json(row.payload) if row else None


def list_investigations(limit: int = 20) -> list[dict]:
    with Session(engine) as s:
        rows = s.scalars(select(InvestigationRow).order_by(InvestigationRow.created_at.desc()).limit(limit)).all()
        out = []
        for r in rows:
            inv = Investigation.model_validate_json(r.payload)
            out.append({"id": r.id, "ticker": r.ticker, "state": r.state, "created_at": utc(r.created_at),
                        "question": inv.question, "data_mode": inv.data_mode})
        return out


def save_scenario_run(run_id: str, payload: str) -> None:
    with Session(engine) as s:
        s.add(ScenarioRunRow(id=run_id, created_at=datetime.now(timezone.utc), payload=payload))
        s.commit()


def get_state(key: str) -> Optional[str]:
    with Session(engine) as s:
        row = s.get(AppStateRow, key)
        return row.value if row else None


def set_state(key: str, value: str) -> None:
    with Session(engine) as s:
        row = s.get(AppStateRow, key)
        if row is None:
            s.add(AppStateRow(key=key, value=value))
        else:
            row.value = value
        s.commit()


def watchlist_rows() -> list[WatchlistRow]:
    with Session(engine) as s:
        rows = s.scalars(select(WatchlistRow).order_by(WatchlistRow.added_at)).all()
        s.expunge_all()
        return list(rows)


def add_watch(ticker: str, data_mode: str) -> None:
    with Session(engine) as s:
        row = s.get(WatchlistRow, ticker)
        if row is None:
            s.add(WatchlistRow(ticker=ticker, data_mode=data_mode, added_at=datetime.now(timezone.utc)))
        else:
            row.data_mode = data_mode
        s.commit()


def remove_watch(ticker: str) -> bool:
    with Session(engine) as s:
        row = s.get(WatchlistRow, ticker)
        if row is None:
            return False
        s.delete(row)
        s.commit()
        return True


def save_watch_result(ticker: str, checked_at: datetime, accessions: str, report: str) -> None:
    with Session(engine) as s:
        row = s.get(WatchlistRow, ticker)
        if row is None:
            return
        row.last_checked_at, row.accessions, row.last_report = checked_at, accessions, report
        s.commit()


def save_doc(kind: str, doc_id: str, payload: str, ticker: Optional[str] = None) -> None:
    """Upsert a decision ("decision") or board ("board") document."""
    model = DecisionRow if kind == "decision" else BoardRow
    with Session(engine) as s:
        row = s.get(model, doc_id)
        if row is None:
            kwargs = {"id": doc_id, "created_at": datetime.now(timezone.utc), "payload": payload}
            if model is DecisionRow:
                kwargs["ticker"] = ticker or ""
            s.add(model(**kwargs))
        else:
            row.payload = payload
        s.commit()


def load_doc(kind: str, doc_id: str) -> Optional[str]:
    model = DecisionRow if kind == "decision" else BoardRow
    with Session(engine) as s:
        row = s.get(model, doc_id)
        return row.payload if row else None


def list_decisions(ticker: Optional[str] = None) -> list[str]:
    with Session(engine) as s:
        q = select(DecisionRow).order_by(DecisionRow.created_at.desc())
        if ticker:
            q = q.where(DecisionRow.ticker == ticker)
        return [r.payload for r in s.scalars(q).all()]
