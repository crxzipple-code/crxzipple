from __future__ import annotations

import typer

from crxzipple.modules.skills.interfaces.cli_draft_commands import build_draft_cli
from crxzipple.modules.skills.interfaces.cli_skill_mutation_commands import (
    register_skill_mutation_commands,
)
from crxzipple.modules.skills.interfaces.cli_skill_query_commands import (
    register_skill_query_commands,
)
from crxzipple.modules.skills.interfaces.cli_source_commands import build_source_cli


def build_cli() -> typer.Typer:
    app = typer.Typer(help="Manage filesystem-backed skills.", no_args_is_help=True)
    register_skill_query_commands(app)
    app.add_typer(build_source_cli(), name="source")
    app.add_typer(build_draft_cli(), name="draft")
    register_skill_mutation_commands(app)
    return app
