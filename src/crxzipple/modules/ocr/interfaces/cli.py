from __future__ import annotations

import typer

from crxzipple.interfaces.cli.context import AppKey, ensure_container
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.artifacts.domain.entities import ArtifactVariant
from crxzipple.modules.ocr.domain import (
    OcrCapacityExceededError,
    OcrExecutionError,
    OcrValidationError,
)
from crxzipple.modules.ocr.infrastructure import create_ocr_host_app


def build_cli() -> typer.Typer:
    app = typer.Typer(help="Analyze images through the OCR service.", no_args_is_help=True)
    host_app = typer.Typer(help="Run the OCR host process.", no_args_is_help=True)

    @app.command("health")
    def health(ctx: typer.Context) -> None:
        container = ensure_container(ctx)
        try:
            echo_data(container.require(AppKey.OCR_SERVICE).health())
        except OcrCapacityExceededError as exc:
            raise typer.BadParameter(str(exc)) from exc
        except (OcrValidationError, OcrExecutionError) as exc:
            raise typer.BadParameter(str(exc)) from exc

    @app.command("analyze-artifact")
    def analyze_artifact(
        ctx: typer.Context,
        artifact_id: str = typer.Argument(..., help="Artifact id to analyze."),
        variant: str = typer.Option(
            ArtifactVariant.ORIGINAL.value,
            "--variant",
            help="Artifact variant: original, preview, or llm.",
        ),
        language: str | None = typer.Option(
            None,
            "--language",
            help="OCR language code passed to the OCR backend.",
        ),
        detect_orientation: bool = typer.Option(
            True,
            "--detect-orientation/--no-detect-orientation",
            help="Enable orientation classification when supported.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        try:
            resolved_variant = ArtifactVariant(variant.strip().lower())
        except ValueError as exc:
            raise typer.BadParameter(
                "variant must be one of: original, preview, llm.",
            ) from exc
        try:
            result = container.require(AppKey.OCR_SERVICE).analyze_artifact(
                artifact_id=artifact_id,
                variant=resolved_variant,
                language=language,
                detect_orientation=detect_orientation,
            )
        except (OcrValidationError, OcrExecutionError) as exc:
            raise typer.BadParameter(str(exc)) from exc
        echo_data(container.require(AppKey.OCR_RESULT_SERIALIZER).serialize(result))

    @host_app.command("run")
    def run_host(
        ctx: typer.Context,
        host: str | None = typer.Option(None, "--host", help="Bind host for the OCR HTTP server."),
        port: int | None = typer.Option(None, "--port", min=1, help="Bind port for the OCR HTTP server."),
        language: str | None = typer.Option(None, "--language", help="Default PaddleOCR language."),
        use_gpu: bool | None = typer.Option(None, "--use-gpu/--no-use-gpu", help="Enable GPU acceleration when supported."),
        max_concurrent_requests: int | None = typer.Option(
            None,
            "--max-concurrent-requests",
            min=1,
            help="Maximum concurrent OCR host requests.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        settings = container.require(AppKey.CORE_SETTINGS)
        app = create_ocr_host_app(
            default_language=language or settings.ocr_language,
            use_gpu=settings.ocr_use_gpu if use_gpu is None else use_gpu,
            max_concurrent_requests=(
                max_concurrent_requests or settings.ocr_max_concurrent_requests
            ),
        )
        import uvicorn

        uvicorn.run(
            app,
            host=host or settings.ocr_host,
            port=port or settings.ocr_port,
        )

    app.add_typer(host_app, name="host")
    return app
