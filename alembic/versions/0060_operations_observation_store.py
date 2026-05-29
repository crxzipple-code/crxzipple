"""persist operations observer state and event buckets

Revision ID: 0060_operations_observation_store
Revises: 0059_runtime_defaults_nested_schema
Create Date: 2026-05-23 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0060_operations_observation_store"
down_revision = "0059_runtime_defaults_nested_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operations_observed_events",
        sa.Column("topic", sa.String(length=240), nullable=False),
        sa.Column("cursor", sa.String(length=160), nullable=False),
        sa.Column("event_id", sa.String(length=80), nullable=False),
        sa.Column("event_name", sa.String(length=160), nullable=False),
        sa.Column("module", sa.String(length=80), nullable=False),
        sa.Column("owner", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("level", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.String(length=240), nullable=False),
        sa.Column("run_id", sa.String(length=160), nullable=True),
        sa.Column("trace_id", sa.String(length=160), nullable=True),
        sa.Column("source_event_name", sa.String(length=160), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("topic", "cursor"),
    )
    op.create_index(
        "ix_operations_observed_events_event_id",
        "operations_observed_events",
        ["event_id"],
    )
    op.create_index(
        "ix_operations_observed_events_event_name",
        "operations_observed_events",
        ["event_name"],
    )
    op.create_index(
        "ix_operations_observed_events_module",
        "operations_observed_events",
        ["module"],
    )
    op.create_index(
        "ix_operations_observed_events_owner",
        "operations_observed_events",
        ["owner"],
    )
    op.create_index(
        "ix_operations_observed_events_status",
        "operations_observed_events",
        ["status"],
    )
    op.create_index(
        "ix_operations_observed_events_entity_id",
        "operations_observed_events",
        ["entity_id"],
    )
    op.create_index(
        "ix_operations_observed_events_run_id",
        "operations_observed_events",
        ["run_id"],
    )
    op.create_index(
        "ix_operations_observed_events_trace_id",
        "operations_observed_events",
        ["trace_id"],
    )
    op.create_index(
        "ix_operations_observed_events_occurred_at",
        "operations_observed_events",
        ["occurred_at"],
    )
    op.create_index(
        "ix_operations_observed_events_recorded_at",
        "operations_observed_events",
        ["recorded_at"],
    )

    op.create_table(
        "operations_module_observations",
        sa.Column("module", sa.String(length=80), nullable=False),
        sa.Column("owner", sa.String(length=80), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("event_count", sa.Integer(), nullable=False),
        sa.Column("status_counts", sa.JSON(), nullable=False),
        sa.Column("event_name_counts", sa.JSON(), nullable=False),
        sa.Column("last_event_id", sa.String(length=80), nullable=True),
        sa.Column("last_event_name", sa.String(length=160), nullable=True),
        sa.Column("last_topic", sa.String(length=240), nullable=True),
        sa.Column("last_cursor", sa.String(length=160), nullable=True),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("module"),
    )
    op.create_index(
        "ix_operations_module_observations_updated_at",
        "operations_module_observations",
        ["updated_at"],
    )
    op.create_index(
        "ix_operations_module_observations_last_event_at",
        "operations_module_observations",
        ["last_event_at"],
    )

    op.create_table(
        "operations_observer_heartbeats",
        sa.Column("runtime_name", sa.String(length=120), nullable=False),
        sa.Column("worker_id", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_events", sa.Integer(), nullable=False),
        sa.Column("idle_cycles", sa.Integer(), nullable=False),
        sa.Column("subscription_count", sa.Integer(), nullable=False),
        sa.Column("poll_interval_seconds", sa.Float(), nullable=True),
        sa.Column("limit_per_subscription", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("runtime_name", "worker_id"),
    )
    op.create_index(
        "ix_operations_observer_heartbeats_status",
        "operations_observer_heartbeats",
        ["status"],
    )
    op.create_index(
        "ix_operations_observer_heartbeats_last_seen_at",
        "operations_observer_heartbeats",
        ["last_seen_at"],
    )

    op.create_table(
        "operations_event_time_buckets",
        sa.Column("module", sa.String(length=80), nullable=False),
        sa.Column("event_name", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("bucket_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("owner", sa.String(length=80), nullable=False),
        sa.Column("level", sa.String(length=40), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("module", "event_name", "status", "bucket_start"),
    )
    op.create_index(
        "ix_operations_event_time_buckets_owner",
        "operations_event_time_buckets",
        ["owner"],
    )
    op.create_index(
        "ix_operations_event_time_buckets_level",
        "operations_event_time_buckets",
        ["level"],
    )
    op.create_index(
        "ix_operations_event_time_buckets_updated_at",
        "operations_event_time_buckets",
        ["updated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_operations_event_time_buckets_updated_at",
        table_name="operations_event_time_buckets",
    )
    op.drop_index(
        "ix_operations_event_time_buckets_level",
        table_name="operations_event_time_buckets",
    )
    op.drop_index(
        "ix_operations_event_time_buckets_owner",
        table_name="operations_event_time_buckets",
    )
    op.drop_table("operations_event_time_buckets")

    op.drop_index(
        "ix_operations_observer_heartbeats_last_seen_at",
        table_name="operations_observer_heartbeats",
    )
    op.drop_index(
        "ix_operations_observer_heartbeats_status",
        table_name="operations_observer_heartbeats",
    )
    op.drop_table("operations_observer_heartbeats")

    op.drop_index(
        "ix_operations_module_observations_last_event_at",
        table_name="operations_module_observations",
    )
    op.drop_index(
        "ix_operations_module_observations_updated_at",
        table_name="operations_module_observations",
    )
    op.drop_table("operations_module_observations")

    op.drop_index(
        "ix_operations_observed_events_recorded_at",
        table_name="operations_observed_events",
    )
    op.drop_index(
        "ix_operations_observed_events_occurred_at",
        table_name="operations_observed_events",
    )
    op.drop_index(
        "ix_operations_observed_events_trace_id",
        table_name="operations_observed_events",
    )
    op.drop_index(
        "ix_operations_observed_events_run_id",
        table_name="operations_observed_events",
    )
    op.drop_index(
        "ix_operations_observed_events_entity_id",
        table_name="operations_observed_events",
    )
    op.drop_index(
        "ix_operations_observed_events_status",
        table_name="operations_observed_events",
    )
    op.drop_index(
        "ix_operations_observed_events_owner",
        table_name="operations_observed_events",
    )
    op.drop_index(
        "ix_operations_observed_events_module",
        table_name="operations_observed_events",
    )
    op.drop_index(
        "ix_operations_observed_events_event_name",
        table_name="operations_observed_events",
    )
    op.drop_index(
        "ix_operations_observed_events_event_id",
        table_name="operations_observed_events",
    )
    op.drop_table("operations_observed_events")
