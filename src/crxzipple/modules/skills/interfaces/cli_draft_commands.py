from __future__ import annotations

import typer

from crxzipple.modules.skills.interfaces.cli_draft_authoring_commands import (
    register_draft_authoring_commands,
)
from crxzipple.modules.skills.interfaces.cli_draft_lifecycle_commands import (
    register_draft_lifecycle_commands,
)
from crxzipple.modules.skills.interfaces.cli_draft_query_commands import (
    register_draft_query_commands,
)


def build_draft_cli() -> typer.Typer:
    draft_app = typer.Typer(
        help="Manage governed skill authoring drafts.",
        no_args_is_help=True,
    )
    register_draft_query_commands(draft_app)
    register_draft_authoring_commands(draft_app)
    register_draft_lifecycle_commands(draft_app)
    return draft_app
