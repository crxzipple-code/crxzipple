from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from crxzipple.core.db import Base


class TemporaryAuthorizationGrantModel(Base):
    __tablename__ = "authorization_temporary_grants"

    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    scope: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    run_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    session_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    agent_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    approval_request_id: Mapped[str | None] = mapped_column(
        String(160),
        nullable=True,
        index=True,
    )
    effect_ids_payload: Mapped[list[str]] = mapped_column(
        JSON(),
        nullable=False,
        default=list,
    )
    tool_ids_payload: Mapped[list[str]] = mapped_column(
        JSON(),
        nullable=False,
        default=list,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
