from __future__ import annotations

import base64
import mimetypes
import os
from pathlib import Path
from typing import Any

import httpx

from crxzipple.modules.access.application import CredentialResolver
from crxzipple.modules.artifacts.domain.entities import ArtifactKind, ArtifactVariant
from crxzipple.modules.tool.domain import ToolExecutionContext, ToolRunResult
from crxzipple.shared.content_blocks import text_content_block


DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-image-2"
DEFAULT_OUTPUT_FORMAT = "png"
DEFAULT_TIMEOUT_SECONDS = 300.0
OPENAI_API_KEY_BINDING = "env:OPENAI_API_KEY"
MAX_IMAGE_INPUT_BYTES = 20 * 1024 * 1024
OPENAI_ORG_VERIFICATION_URL = "https://platform.openai.com/settings/organization/general"


async def _generate_handler(
    arguments: dict[str, Any],
    execution_context: ToolExecutionContext | None = None,
    *,
    container: Any,
) -> ToolRunResult:
    prompt = _required_str(arguments, "prompt")
    payload = _base_image_payload(arguments, prompt=prompt)
    response_payload = await _post_openai_json(
        container,
        "/images/generations",
        payload,
        execution_context=execution_context,
    )
    return await _tool_result_from_openai_images(
        container,
        response_payload,
        action="generate",
        request_payload=payload,
        execution_context=execution_context,
    )


async def _edit_handler(
    arguments: dict[str, Any],
    execution_context: ToolExecutionContext | None = None,
    *,
    container: Any,
) -> ToolRunResult:
    prompt = _required_str(arguments, "prompt")
    payload = _base_image_payload(arguments, prompt=prompt)
    image_inputs = _collect_edit_image_inputs(
        container,
        arguments,
        execution_context=execution_context,
    )
    if not image_inputs:
        raise RuntimeError(
            "openai_image_edit requires at least one image_artifact_id, image_artifact_ids, or image_urls value.",
        )
    payload["images"] = image_inputs
    mask_input = _collect_mask_input(
        container,
        arguments,
        execution_context=execution_context,
    )
    if mask_input is not None:
        payload["mask"] = mask_input

    response_payload = await _post_openai_json(
        container,
        "/images/edits",
        payload,
        execution_context=execution_context,
    )
    return await _tool_result_from_openai_images(
        container,
        response_payload,
        action="edit",
        request_payload=payload,
        execution_context=execution_context,
    )


def openai_image_generate(container: Any):
    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        return await _generate_handler(
            arguments,
            execution_context,
            container=container,
        )

    return handler


def openai_image_edit(container: Any):
    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        return await _edit_handler(
            arguments,
            execution_context,
            container=container,
        )

    return handler


def _base_image_payload(arguments: dict[str, Any], *, prompt: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": _optional_str(arguments, "model") or _default_model(),
        "prompt": prompt,
    }
    for key in ("size", "quality", "background", "output_format", "moderation"):
        value = _optional_str(arguments, key)
        if value is not None:
            payload[key] = value
    output_compression = _optional_int(arguments, "output_compression")
    if output_compression is not None:
        payload["output_compression"] = output_compression
    count = _optional_int(arguments, "n")
    if count is not None:
        payload["n"] = count
    return payload


async def _post_openai_json(
    container: Any,
    path: str,
    payload: dict[str, Any],
    *,
    execution_context: ToolExecutionContext | None,
) -> dict[str, Any]:
    token = _resolve_api_key(container, execution_context=execution_context)
    base_url = _base_url(container)
    timeout_seconds = _timeout_seconds(container)
    client_factory = getattr(container, "openai_image_http_client_factory", None)
    if client_factory is None:
        client_factory = httpx.AsyncClient
    async with client_factory(timeout=timeout_seconds) as client:
        try:
            response = await client.post(
                f"{base_url}{path}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        except httpx.TimeoutException as exc:
            raise RuntimeError(
                f"OpenAI image API {path} timed out after {timeout_seconds:g}s. "
                "Image generation can take longer for high quality or large outputs; "
                "retry later or increase OPENAI_IMAGE_TIMEOUT_SECONDS.",
            ) from exc
    return _json_response_payload(response, description=f"OpenAI image API {path}")


async def _tool_result_from_openai_images(
    container: Any,
    payload: dict[str, Any],
    *,
    action: str,
    request_payload: dict[str, Any],
    execution_context: ToolExecutionContext | None,
) -> ToolRunResult:
    images = await _extract_generated_images(
        container,
        payload,
        output_format=str(
            request_payload.get("output_format") or DEFAULT_OUTPUT_FORMAT,
        ),
        execution_context=execution_context,
    )
    if not images:
        raise RuntimeError("OpenAI image API completed without an image payload.")

    model = str(request_payload.get("model") or DEFAULT_MODEL)
    prompt = str(request_payload.get("prompt") or "")
    image_blocks = []
    for index, image in enumerate(images, start=1):
        image_blocks.append(
            {
                "type": "image",
                "data": image["data"],
                "mime_type": image["mime_type"],
                "name": _image_name(model=model, action=action, index=index, mime_type=image["mime_type"]),
            },
        )

    action_label = "Generated" if action == "generate" else "Edited"
    count = len(image_blocks)
    content = [
        text_content_block(
            f"{action_label} {count} image{'s' if count != 1 else ''} with {model}.",
        ),
        *image_blocks,
    ]
    return ToolRunResult.structured(
        content=content,
        details=_safe_details(
            {
                "provider": "openai",
                "action": action,
                "model": model,
                "image_count": count,
                "size": request_payload.get("size"),
                "quality": request_payload.get("quality"),
                "background": request_payload.get("background"),
                "output_format": request_payload.get("output_format"),
                "output_compression": request_payload.get("output_compression"),
                "prompt_excerpt": _excerpt(prompt),
                "revised_prompts": [
                    item.get("revised_prompt")
                    for item in _response_data(payload)
                    if isinstance(item, dict) and isinstance(item.get("revised_prompt"), str)
                ],
            },
        ),
        metadata={
            "provider": "openai",
            "model": model,
            "action": action,
            "image_count": count,
        },
    )


async def _extract_generated_images(
    container: Any,
    payload: dict[str, Any],
    *,
    output_format: str,
    execution_context: ToolExecutionContext | None,
) -> list[dict[str, str]]:
    images: list[dict[str, str]] = []
    for item in _response_data(payload):
        if not isinstance(item, dict):
            continue
        b64_json = item.get("b64_json") or item.get("b64")
        if isinstance(b64_json, str) and b64_json.strip():
            data, mime_type = _normalize_base64_image(
                b64_json,
                fallback_mime_type=_mime_type_for_output_format(output_format),
            )
            images.append({"data": data, "mime_type": mime_type})
            continue
        url = item.get("url")
        if isinstance(url, str) and url.strip():
            images.append(
                await _download_image_url(
                    container,
                    url.strip(),
                    execution_context=execution_context,
                ),
            )
    return images


def _response_data(payload: dict[str, Any]) -> list[Any]:
    data = payload.get("data")
    if isinstance(data, list):
        return data
    output = payload.get("output")
    if isinstance(output, list):
        return output
    return []


async def _download_image_url(
    container: Any,
    url: str,
    *,
    execution_context: ToolExecutionContext | None,
) -> dict[str, str]:
    client_factory = getattr(container, "openai_image_http_client_factory", None)
    if client_factory is None:
        client_factory = httpx.AsyncClient
    async with client_factory(timeout=_timeout_seconds(container)) as client:
        try:
            response = await client.get(url)
        except httpx.TimeoutException as exc:
            raise RuntimeError(
                "OpenAI image URL download timed out. "
                "Retry later or increase OPENAI_IMAGE_TIMEOUT_SECONDS.",
            ) from exc
    if response.status_code >= 400:
        raise RuntimeError(f"OpenAI image URL download failed with HTTP {response.status_code}.")
    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
    mime_type = content_type if content_type.startswith("image/") else "image/png"
    data = base64.b64encode(response.content).decode("ascii")
    return {"data": data, "mime_type": mime_type}


def _collect_edit_image_inputs(
    container: Any,
    arguments: dict[str, Any],
    *,
    execution_context: ToolExecutionContext | None,
) -> list[dict[str, Any]]:
    inputs: list[dict[str, Any]] = []
    artifact_ids = _string_sequence(arguments.get("image_artifact_ids"))
    single_artifact_id = _optional_str(arguments, "image_artifact_id")
    if single_artifact_id is not None:
        artifact_ids = (single_artifact_id, *artifact_ids)
    for artifact_id in dict.fromkeys(artifact_ids):
        inputs.append(
            _artifact_image_input(
                container,
                artifact_id,
                execution_context=execution_context,
            ),
        )
    for url in _string_sequence(arguments.get("image_urls")):
        inputs.append({"type": "input_image", "image_url": url})
    return inputs


def _collect_mask_input(
    container: Any,
    arguments: dict[str, Any],
    *,
    execution_context: ToolExecutionContext | None,
) -> dict[str, Any] | None:
    mask_artifact_id = _optional_str(arguments, "mask_artifact_id")
    if mask_artifact_id is not None:
        return _artifact_image_input(
            container,
            mask_artifact_id,
            execution_context=execution_context,
        )
    mask_url = _optional_str(arguments, "mask_url")
    if mask_url is not None:
        return {"type": "input_image", "image_url": mask_url}
    return None


def _artifact_image_input(
    container: Any,
    artifact_id: str,
    *,
    execution_context: ToolExecutionContext | None,
) -> dict[str, Any]:
    artifact_service = getattr(container, "artifact_service", None)
    if artifact_service is None:
        raise RuntimeError("openai_image_edit requires the artifact service to read image artifacts.")
    try:
        resolved = artifact_service.resolve_variant(
            artifact_id,
            variant=ArtifactVariant.ORIGINAL,
        )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Image artifact '{artifact_id}' could not be resolved.") from exc
    if resolved.artifact.kind is not ArtifactKind.IMAGE:
        raise RuntimeError(f"Artifact '{artifact_id}' is not an image artifact.")
    image_bytes = resolved.path.read_bytes()
    if len(image_bytes) > MAX_IMAGE_INPUT_BYTES:
        resolved = artifact_service.resolve_variant(
            artifact_id,
            variant=ArtifactVariant.LLM,
        )
        image_bytes = resolved.path.read_bytes()
    if len(image_bytes) > MAX_IMAGE_INPUT_BYTES:
        raise RuntimeError(
            f"Image artifact '{artifact_id}' exceeds the OpenAI image input limit.",
        )
    mime_type = resolved.artifact.mime_type or _guess_mime_type(resolved.path)
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return {
        "type": "input_image",
        "image_url": f"data:{mime_type};base64,{encoded}",
    }


def _resolve_api_key(
    container: Any,
    *,
    execution_context: ToolExecutionContext | None,
) -> str:
    resolver = getattr(container, "credential_resolver", None)
    if resolver is None:
        access_service = getattr(container, "access_service", None)
        resolver = getattr(access_service, "credential_resolver", None)
    if resolver is None:
        resolver = CredentialResolver()
    workspace_dir = execution_context.get_str("workspace_dir") if execution_context else None
    try:
        return resolver.resolve(
            OPENAI_API_KEY_BINDING,
            workspace_dir=workspace_dir,
            allow_literal=False,
        )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("OpenAI image tools require OPENAI_API_KEY.") from exc


def _base_url(container: Any) -> str:
    value = (
        getattr(container, "openai_image_base_url", None)
        or os.environ.get("OPENAI_IMAGE_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or DEFAULT_BASE_URL
    )
    return str(value).strip().rstrip("/") or DEFAULT_BASE_URL


def _timeout_seconds(container: Any) -> float:
    value = (
        getattr(container, "openai_image_timeout_seconds", None)
        or os.environ.get("OPENAI_IMAGE_TIMEOUT_SECONDS")
        or DEFAULT_TIMEOUT_SECONDS
    )
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_SECONDS
    return max(timeout, 1.0)


def _json_response_payload(response: httpx.Response, *, description: str) -> dict[str, Any]:
    if response.status_code >= 400:
        body = response.text
        try:
            error_payload = response.json()
        except ValueError:
            error_payload = None
        if isinstance(error_payload, dict):
            error = error_payload.get("error")
            if isinstance(error, dict) and isinstance(error.get("message"), str):
                body = error["message"]
        raise RuntimeError(_format_openai_error(description, response.status_code, body))
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"{description} returned invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{description} returned a non-object JSON payload.")
    return payload


def _default_model() -> str:
    return os.environ.get("OPENAI_IMAGE_MODEL", "").strip() or DEFAULT_MODEL


def _format_openai_error(description: str, status_code: int, body: str) -> str:
    message = f"{description} failed with HTTP {status_code}: {body}"
    if status_code == 403 and _looks_like_org_verification_error(body):
        return (
            f"{message}\n"
            f"OpenAI organization verification is required for this image model. "
            f"Verify the API organization at {OPENAI_ORG_VERIFICATION_URL}; if verification "
            f"was just completed, wait up to 15 minutes for access to propagate. "
            f"As a temporary workaround, pass a different `model` argument or set "
            f"`OPENAI_IMAGE_MODEL` to a model your organization can access."
        )
    return message


def _looks_like_org_verification_error(message: str) -> bool:
    normalized = message.lower()
    return "organization" in normalized and "verified" in normalized


def _normalize_base64_image(
    data: str,
    *,
    fallback_mime_type: str,
) -> tuple[str, str]:
    normalized = data.strip()
    mime_type = fallback_mime_type
    if normalized.startswith("data:") and ";base64," in normalized:
        metadata, normalized = normalized.split(";base64,", 1)
        candidate_mime = metadata.removeprefix("data:").strip()
        if candidate_mime.startswith("image/"):
            mime_type = candidate_mime
    return normalized, mime_type


def _mime_type_for_output_format(output_format: str) -> str:
    normalized = output_format.strip().lower()
    if normalized in {"jpg", "jpeg"}:
        return "image/jpeg"
    if normalized == "webp":
        return "image/webp"
    return "image/png"


def _guess_mime_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "image/png"


def _image_name(*, model: str, action: str, index: int, mime_type: str) -> str:
    suffix = mimetypes.guess_extension(mime_type) or ".png"
    if suffix == ".jpe":
        suffix = ".jpg"
    safe_model = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in model)
    return f"openai-{safe_model}-{action}-{index}{suffix}"


def _required_str(arguments: dict[str, Any], key: str) -> str:
    value = _optional_str(arguments, key)
    if value is None:
        raise RuntimeError(f"OpenAI image tool requires a non-empty '{key}' argument.")
    return value


def _optional_str(arguments: dict[str, Any], key: str) -> str | None:
    value = arguments.get(key)
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _optional_int(arguments: dict[str, Any], key: str) -> int | None:
    value = arguments.get(key)
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"OpenAI image argument '{key}' must be an integer.") from exc
    if parsed <= 0:
        raise RuntimeError(f"OpenAI image argument '{key}' must be greater than zero.")
    return parsed


def _string_sequence(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        normalized = value.strip()
        return (normalized,) if normalized else ()
    if isinstance(value, (list, tuple)):
        return tuple(
            normalized
            for item in value
            if (normalized := str(item).strip())
        )
    return ()


def _safe_details(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item not in (None, [], {})}


def _excerpt(value: str, *, max_chars: int = 500) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= max_chars:
        return normalized
    return f"{normalized[: max_chars - 1]}..."
