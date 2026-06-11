"""allow multiple context render snapshots per run

Revision ID: 0070_context_render_snapshot_run_history
Revises: 0069_llm_invocation_request_metadata
Create Date: 2026-06-07 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0070_context_render_snapshot_run_history"
down_revision = "0069_llm_invocation_request_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        _recreate_sqlite_context_render_snapshots(unique_run=False)
        return
    constraint_name = _run_unique_constraint_name()
    if constraint_name is None:
        return
    op.drop_constraint(
        constraint_name,
        "context_render_snapshots",
        type_="unique",
    )


def downgrade() -> None:
    _dedupe_to_latest_snapshot_per_run()
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        _recreate_sqlite_context_render_snapshots(unique_run=True)
        return
    op.create_unique_constraint(
        "context_render_snapshots_run_id_key",
        "context_render_snapshots",
        ["run_id"],
    )


def _dedupe_to_latest_snapshot_per_run() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.execute(
            sa.text(
                """
                DELETE FROM context_render_snapshots older
                USING context_render_snapshots newer
                WHERE older.run_id = newer.run_id
                  AND (
                    older.created_at < newer.created_at
                    OR (
                      older.created_at = newer.created_at
                      AND older.snapshot_id < newer.snapshot_id
                    )
                  )
                """,
            ),
        )
        return
    rows = bind.execute(
        sa.text(
            """
            SELECT snapshot_id, run_id, created_at
            FROM context_render_snapshots
            ORDER BY run_id ASC, created_at DESC, snapshot_id DESC
            """,
        ),
    ).all()
    keep_by_run: dict[str, str] = {}
    delete_ids: list[str] = []
    for row in rows:
        run_id = str(row.run_id)
        if run_id in keep_by_run:
            delete_ids.append(str(row.snapshot_id))
            continue
        keep_by_run[run_id] = str(row.snapshot_id)
    for snapshot_id in delete_ids:
        bind.execute(
            sa.text(
                "DELETE FROM context_render_snapshots WHERE snapshot_id = :snapshot_id",
            ),
            {"snapshot_id": snapshot_id},
        )


def _run_unique_constraint_name() -> str | None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for constraint in inspector.get_unique_constraints("context_render_snapshots"):
        columns = tuple(constraint.get("column_names") or ())
        if columns != ("run_id",):
            continue
        name = constraint.get("name")
        return str(name) if name else None
    return None


def _recreate_sqlite_context_render_snapshots(*, unique_run: bool) -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT snapshot_id, workspace_id, session_key, run_id, tree_revision,
                   prompt_body, provider_attachments, estimate, included_node_ids,
                   mirrored_node_ids, metadata, created_at
            FROM context_render_snapshots
            ORDER BY created_at ASC, snapshot_id ASC
            """,
        ),
    ).all()
    op.drop_index(
        "ix_context_render_snapshots_workspace_id",
        table_name="context_render_snapshots",
    )
    op.drop_index(
        "ix_context_render_snapshots_session_key",
        table_name="context_render_snapshots",
    )
    op.drop_index(
        "ix_context_render_snapshots_run_id",
        table_name="context_render_snapshots",
    )
    op.drop_index(
        "ix_context_render_snapshots_created_at",
        table_name="context_render_snapshots",
    )
    op.drop_table("context_render_snapshots")
    constraints: list[sa.Constraint] = [sa.PrimaryKeyConstraint("snapshot_id")]
    if unique_run:
        constraints.append(sa.UniqueConstraint("run_id"))
    op.create_table(
        "context_render_snapshots",
        sa.Column("snapshot_id", sa.String(length=80), nullable=False),
        sa.Column("workspace_id", sa.String(length=80), nullable=False),
        sa.Column("session_key", sa.String(length=240), nullable=False),
        sa.Column("run_id", sa.String(length=160), nullable=False),
        sa.Column("tree_revision", sa.Integer(), nullable=False),
        sa.Column("prompt_body", sa.Text(), nullable=False),
        sa.Column("provider_attachments", sa.JSON(), nullable=False),
        sa.Column("estimate", sa.JSON(), nullable=False),
        sa.Column("included_node_ids", sa.JSON(), nullable=False),
        sa.Column("mirrored_node_ids", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        *constraints,
    )
    for column in (
        "workspace_id",
        "session_key",
        "run_id",
        "created_at",
    ):
        op.create_index(
            f"ix_context_render_snapshots_{column}",
            "context_render_snapshots",
            [column],
        )
    for row in rows:
        bind.execute(
            sa.text(
                """
                INSERT INTO context_render_snapshots (
                    snapshot_id, workspace_id, session_key, run_id, tree_revision,
                    prompt_body, provider_attachments, estimate, included_node_ids,
                    mirrored_node_ids, metadata, created_at
                )
                VALUES (
                    :snapshot_id, :workspace_id, :session_key, :run_id,
                    :tree_revision, :prompt_body, :provider_attachments,
                    :estimate, :included_node_ids, :mirrored_node_ids,
                    :metadata, :created_at
                )
                """,
            ),
            dict(row._mapping),
        )
