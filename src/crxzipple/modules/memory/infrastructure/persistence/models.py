from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from crxzipple.core.db import Base


class MemorySpaceModel(Base):
    __tablename__ = "memory_spaces"

    scope_ref: Mapped[str] = mapped_column(String(255), primary_key=True)
    owner_kind: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    owner_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    engine_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    storage_root: Mapped[str] = mapped_column(String(1000), nullable=False)
    retrieval_backend: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    metadata_payload: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )


class MemoryPolicyModel(Base):
    __tablename__ = "memory_policies"

    policy_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    target_kind: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    target_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    recall_enabled: Mapped[bool] = mapped_column(nullable=False)
    remember_enabled: Mapped[bool] = mapped_column(nullable=False)
    max_recall_items: Mapped[int] = mapped_column(nullable=False)
    retention: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    metadata_payload: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
