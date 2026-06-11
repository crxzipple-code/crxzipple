from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from crxzipple.core.db import Base


class LlmProfileModel(Base):
    __tablename__ = "llm_profiles"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    api_family: Mapped[str] = mapped_column(String(100), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    context_window_tokens: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    model_family: Mapped[str] = mapped_column(String(100), nullable=False)
    capabilities: Mapped[list[str]] = mapped_column(JSON(), nullable=False, default=list)
    default_params: Mapped[dict[str, object]] = mapped_column(
        JSON(),
        nullable=False,
        default=dict,
    )
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    credential_binding_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    timeout_seconds: Mapped[int] = mapped_column(Integer(), nullable=False, default=60)
    max_concurrency: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    concurrency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_kind: Mapped[str] = mapped_column(String(100), nullable=False)
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)


class LlmInvocationModel(Base):
    __tablename__ = "llm_invocations"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    llm_id: Mapped[str] = mapped_column(
        ForeignKey("llm_profiles.id"),
        nullable=False,
        index=True,
    )
    messages: Mapped[list[dict[str, object]]] = mapped_column(
        JSON(),
        nullable=False,
        default=list,
    )
    tool_schemas: Mapped[list[dict[str, object]]] = mapped_column(
        JSON(),
        nullable=False,
        default=list,
    )
    response_format: Mapped[dict[str, object] | None] = mapped_column(JSON(), nullable=True)
    request_overrides: Mapped[dict[str, object]] = mapped_column(
        JSON(),
        nullable=False,
        default=dict,
    )
    request_metadata: Mapped[dict[str, object]] = mapped_column(
        JSON(),
        nullable=False,
        default=dict,
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    result_payload: Mapped[dict[str, object] | None] = mapped_column(JSON(), nullable=True)
    error_payload: Mapped[dict[str, object] | None] = mapped_column(JSON(), nullable=True)
    provider_request_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
