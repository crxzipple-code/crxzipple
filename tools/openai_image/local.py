from __future__ import annotations

import base64
import mimetypes
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from crxzipple.modules.artifacts.domain.entities import ArtifactKind, ArtifactVariant
from crxzipple.modules.tool.domain import ToolExecutionContext, ToolRunResult
from crxzipple.shared.access import (
    AccessConsumerRef,
    AccessCredentialKind,
    CredentialBindingRef,
    CredentialProvider,
)
from crxzipple.shared.content_blocks import text_content_block


DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-image-2"
DEFAULT_OUTPUT_FORMAT = "png"
DEFAULT_TIMEOUT_SECONDS = 300.0
MAX_IMAGE_INPUT_BYTES = 20 * 1024 * 1024
OPENAI_ORG_VERIFICATION_URL = "https://platform.openai.com/settings/organization/general"


@dataclass(frozen=True, slots=True)
class OpenAIImageDeps:
    credential_provider: CredentialProvider | None
    artifact_service: Any | None = None
    http_client_factory: Callable[..., Any] | None = field(
        default=None,
        metadata={"dependency_id": "openai_image_http_client_factory"},
    )
    base_url: str | None = field(
        default=None,
        metadata={"dependency_id": "openai_image_base_url"},
    )
    timeout_seconds: float | None = field(
        default=None,
        metadata={"dependency_id": "openai_image_timeout_seconds"},
    )


async def _generate_handler(
    arguments: dict[str, Any],
    execution_context: ToolExecutionContext | None = None,
    *,
    deps: OpenAIImageDeps,
) -> ToolRunResult:
    prompt = _required_str(arguments, "prompt")
    payload = _base_image_payload(arguments, prompt=prompt)
    response_payload = await _post_openai_json(
        deps,
        "/images/generations",
        payload,
        tool_id="openai_image_generate",
        execution_context=execution_context,
    )
    return await _tool_result_from_openai_images(
        deps,
        response_payload,
        action="generate",
        request_payload=payload,
        execution_context=execution_context,
    )


async def _edit_handler(
    arguments: dict[str, Any],
    execution_context: ToolExecutionContext | None = None,
    *,
    deps: OpenAIImageDeps,
) -> ToolRunResult:
    prompt = _required_str(arguments, "prompt")
    payload = _base_image_payload(arguments, prompt=prompt)
    image_inputs = _collect_edit_image_inputs(
        deps,
        arguments,
        execution_context=execution_context,
    )
    if not image_inputs:
        raise RuntimeError(
            "openai_image_edit requires at least one image_artifact_id, image_artifact_ids, or image_urls value.",
        )
    payload["images"] = image_inputs
    mask_input = _collect_mask_input(
        deps,
        arguments,
        execution_context=execution_context,
    )
    if mask_input is not None:
        payload["mask"] = mask_input

    response_payload = await _post_openai_json(
        deps,
        "/images/edits",
        payload,
        tool_id="openai_image_edit",
        execution_context=execution_context,
    )
    return await _tool_result_from_openai_images(
        deps,
        response_payload,
        action="edit",
        request_payload=payload,
        execution_context=execution_context,
    )


def openai_image_generate(deps: OpenAIImageDeps | Any):
    resolved_deps = _coerce_deps(deps)

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        return await _generate_handler(
            arguments,
            execution_context,
            deps=resolved_deps,
        )

    return handler


def openai_image_edit(deps: OpenAIImageDeps | Any):
    resolved_deps = _coerce_deps(deps)

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        return await _edit_handler(
            arguments,
            execution_context,
            deps=resolved_deps,
        )

    return handler


def _coerce_deps(value: OpenAIImageDeps | Any) -> OpenAIImageDeps:
    if isinstance(value, OpenAIImageDeps):
        return value
    raise TypeError(
        "OpenAI image tools require OpenAIImageDeps.",
    )


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
    deps: OpenAIImageDeps,
    path: str,
    payload: dict[str, Any],
    *,
    tool_id: str,
    execution_context: ToolExecutionContext | None,
) -> dict[str, Any]:
    token = _resolve_api_key(
        deps,
        tool_id=tool_id,
        execution_context=execution_context,
    )
    base_url = _base_url(deps)
    timeout_seconds = _timeout_seconds(deps)
    client_factory = deps.http_client_factory or httpx.AsyncClient
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
    deps: OpenAIImageDeps,
    payload: dict[str, Any],
    *,
    action: str,
    request_payload: dict[str, Any],
    execution_context: ToolExecutionContext | None,
) -> ToolRunResult:
    images = await _extract_generated_images(
        deps,
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
    deps: OpenAIImageDeps,
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
                    deps,
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
    deps: OpenAIImageDeps,
    url: str,
    *,
    execution_context: ToolExecutionContext | None,
) -> dict[str, str]:
    client_factory = deps.http_client_factory or httpx.AsyncClient
    async with client_factory(timeout=_timeout_seconds(deps)) as client:
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
    deps: OpenAIImageDeps,
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
                deps,
                artifact_id,
                execution_context=execution_context,
            ),
        )
    for url in _string_sequence(arguments.get("image_urls")):
        inputs.append({"type": "input_image", "image_url": url})
    return inputs


def _collect_mask_input(
    deps: OpenAIImageDeps,
    arguments: dict[str, Any],
    *,
    execution_context: ToolExecutionContext | None,
) -> dict[str, Any] | None:
    mask_artifact_id = _optional_str(arguments, "mask_artifact_id")
    if mask_artifact_id is not None:
        return _artifact_image_input(
            deps,
            mask_artifact_id,
            execution_context=execution_context,
        )
    mask_url = _optional_str(arguments, "mask_url")
    if mask_url is not None:
        return {"type": "input_image", "image_url": mask_url}
    return None


def _artifact_image_input(
    deps: OpenAIImageDeps,
    artifact_id: str,
    *,
    execution_context: ToolExecutionContext | None,
) -> dict[str, Any]:
    artifact_service = deps.artifact_service
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
    deps: OpenAIImageDeps,
    *,
    tool_id: str,
    execution_context: ToolExecutionContext | None,
) -> str:
    credential_provider = deps.credential_provider
    if credential_provider is None:
        raise RuntimeError("OpenAI image tools require Access credential binding.")
    binding_id = _provider_backend_binding_id(
        execution_context,
        slot="openai_api_key",
    )
    if binding_id is None:
        raise RuntimeError(
            "OpenAI image tools require a resolved provider backend credential binding.",
        )
    try:
        return credential_provider.resolve_credential(
            CredentialBindingRef(
                binding_id=binding_id,
                source_type="binding",
                source_ref=binding_id,
                expected_kind=AccessCredentialKind.API_KEY,
                metadata={
                    "provider": "openai",
                    "slot": "openai_api_key",
                    "tool_id": tool_id,
                    "provider_backend_id": _provider_backend_id(execution_context),
                },
            ),
            consumer=AccessConsumerRef(
                consumer_id=f"tool.local:{tool_id}",
                module="tool",
                component="local_package",
                runtime_ref=tool_id,
                metadata={
                    "namespace": "openai_image",
                    "provider": "openai",
                },
            ),
        )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"OpenAI image tools require Access binding {binding_id}.",
        ) from exc


def _provider_backend_binding_id(
    execution_context: ToolExecutionContext | None,
    *,
    slot: str,
) -> str | None:
    backend = _provider_backend_payload(execution_context)
    if backend is None:
        return None
    raw_bindings = backend.get("credential_bindings")
    if isinstance(raw_bindings, Mapping):
        value = raw_bindings.get(slot)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for requirement_set in _sequence(backend.get("credential_requirements")):
        if not isinstance(requirement_set, Mapping):
            continue
        for requirement in _sequence(requirement_set.get("requirements")):
            if not isinstance(requirement, Mapping):
                continue
            slot_payload = requirement.get("slot")
            if not isinstance(slot_payload, Mapping):
                continue
            slot_name = slot_payload.get("slot")
            binding_id = slot_payload.get("binding_id")
            if (
                isinstance(slot_name, str)
                and slot_name.strip() == slot
                and isinstance(binding_id, str)
                and binding_id.strip()
            ):
                return binding_id.strip()
    return None


def _provider_backend_id(
    execution_context: ToolExecutionContext | None,
) -> str | None:
    backend = _provider_backend_payload(execution_context)
    if backend is None:
        return None
    value = backend.get("backend_id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _provider_backend_payload(
    execution_context: ToolExecutionContext | None,
) -> Mapping[str, Any] | None:
    if execution_context is None:
        return None
    value = execution_context.attrs.get("provider_backend")
    if isinstance(value, Mapping):
        return value
    return None


def _sequence(value: object) -> tuple[object, ...]:
    if value is None:
        return ()
    if isinstance(value, tuple | list):
        return tuple(value)
    return (value,)


def _base_url(deps: OpenAIImageDeps) -> str:
    value = (
        deps.base_url
        or os.environ.get("OPENAI_IMAGE_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or DEFAULT_BASE_URL
    )
    return str(value).strip().rstrip("/") or DEFAULT_BASE_URL


def _timeout_seconds(deps: OpenAIImageDeps) -> float:
    value = (
        deps.timeout_seconds
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
