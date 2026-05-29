"""remove deprecated codex auth json access asset

Revision ID: 0048_remove_codex_auth_json_access_asset
Revises: 0047_access_oauth_accounts
Create Date: 2026-05-12 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0048_remove_codex_auth_json_access_asset"
down_revision = "0047_access_oauth_accounts"
branch_labels = None
depends_on = None


_DEPRECATED_RESOURCE_ID = "codex-auth-json"
_DEPRECATED_ACCESS_ACTIONS = (
    "import_codex_cli_oauth_account",
    "start_codex_cli_login",
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    _delete_by_resource_id(
        bind,
        inspector,
        "settings_effective_snapshots",
        "resource_id",
    )
    _delete_by_resource_id(bind, inspector, "settings_overrides", "resource_id")
    _delete_by_resource_id(
        bind,
        inspector,
        "settings_validation_results",
        "resource_id",
    )
    _delete_by_resource_id(
        bind,
        inspector,
        "settings_action_audits",
        "resource_id",
    )
    _delete_by_resource_id(
        bind,
        inspector,
        "settings_resource_versions",
        "resource_id",
    )
    _delete_by_resource_id(bind, inspector, "settings_resources", "resource_id")

    if inspector.has_table("access_action_audits"):
        bind.execute(
            sa.text(
                """
                DELETE FROM access_action_audits
                WHERE target_id = :resource_id
                   OR action_type IN :deprecated_actions
                """,
            ).bindparams(
                sa.bindparam("deprecated_actions", expanding=True),
            ),
            {
                "resource_id": _DEPRECATED_RESOURCE_ID,
                "deprecated_actions": _DEPRECATED_ACCESS_ACTIONS,
            },
        )

    _delete_by_target_id(
        bind,
        inspector,
        "access_readiness_snapshots",
        "target_id",
    )
    _delete_access_consumer_bindings(bind, inspector)
    _delete_access_secret_bindings(bind, inspector)
    _delete_access_connection_profiles(bind, inspector)
    _delete_access_credential_bindings(bind, inspector)
    _delete_access_assets(bind, inspector)


def downgrade() -> None:
    # Deprecated Codex CLI/auth.json assets are intentionally not restored.
    return None


def _delete_by_resource_id(
    bind: sa.engine.Connection,
    inspector: sa.Inspector,
    table_name: str,
    column_name: str,
) -> None:
    if not inspector.has_table(table_name):
        return
    columns = {column["name"] for column in inspector.get_columns(table_name)}
    if column_name not in columns:
        return
    bind.execute(
        sa.text(
            f"DELETE FROM {table_name} WHERE {column_name} = :resource_id",
        ),
        {"resource_id": _DEPRECATED_RESOURCE_ID},
    )


def _delete_by_target_id(
    bind: sa.engine.Connection,
    inspector: sa.Inspector,
    table_name: str,
    column_name: str,
) -> None:
    if not inspector.has_table(table_name):
        return
    columns = {column["name"] for column in inspector.get_columns(table_name)}
    if column_name not in columns:
        return
    bind.execute(
        sa.text(f"DELETE FROM {table_name} WHERE {column_name} = :target_id"),
        {"target_id": _DEPRECATED_RESOURCE_ID},
    )


def _delete_access_consumer_bindings(
    bind: sa.engine.Connection,
    inspector: sa.Inspector,
) -> None:
    if not inspector.has_table("access_consumer_bindings"):
        return
    bind.execute(
        sa.text(
            """
            DELETE FROM access_consumer_bindings
            WHERE asset_id = :resource_id
               OR credential_binding_id = :resource_id
            """,
        ),
        {"resource_id": _DEPRECATED_RESOURCE_ID},
    )


def _delete_access_secret_bindings(
    bind: sa.engine.Connection,
    inspector: sa.Inspector,
) -> None:
    if not inspector.has_table("access_secret_bindings"):
        return
    bind.execute(
        sa.text(
            """
            DELETE FROM access_secret_bindings
            WHERE credential_binding_id = :resource_id
               OR source_kind = 'codex_auth_json'
            """,
        ),
        {"resource_id": _DEPRECATED_RESOURCE_ID},
    )


def _delete_access_connection_profiles(
    bind: sa.engine.Connection,
    inspector: sa.Inspector,
) -> None:
    if not inspector.has_table("access_connection_profiles"):
        return
    bind.execute(
        sa.text(
            """
            DELETE FROM access_connection_profiles
            WHERE asset_id = :resource_id
               OR credential_binding_id = :resource_id
            """,
        ),
        {"resource_id": _DEPRECATED_RESOURCE_ID},
    )


def _delete_access_credential_bindings(
    bind: sa.engine.Connection,
    inspector: sa.Inspector,
) -> None:
    if not inspector.has_table("access_credential_bindings"):
        return
    bind.execute(
        sa.text(
            """
            DELETE FROM access_credential_bindings
            WHERE binding_id = :resource_id
               OR asset_id = :resource_id
               OR binding_kind = 'codex_auth_json'
               OR source_kind = 'codex_auth_json'
            """,
        ),
        {"resource_id": _DEPRECATED_RESOURCE_ID},
    )


def _delete_access_assets(
    bind: sa.engine.Connection,
    inspector: sa.Inspector,
) -> None:
    if not inspector.has_table("access_assets"):
        return
    bind.execute(
        sa.text(
            """
            DELETE FROM access_assets
            WHERE asset_id = :resource_id
               OR asset_kind = 'codex_auth_json'
               OR governance_scope = 'codex_auth_json'
            """,
        ),
        {"resource_id": _DEPRECATED_RESOURCE_ID},
    )
