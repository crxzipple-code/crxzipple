from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import tempfile
from typing import TYPE_CHECKING, Literal

from crxzipple.core.config_agent_profiles import (
    AgentProfileDefaultsSettings,
    AgentProfileSettings,
    load_agent_profile_settings as _load_agent_profile_settings,
)
from crxzipple.core.config_browser import (
    DEFAULT_BROWSER_DEFAULT_PROFILE_NAME,
    BrowserProfileSettings,
    BrowserProxyEndpointSettings,
    ensure_default_user_browser_profile_settings as _ensure_default_user_browser_profile_settings,
    load_browser_profile_settings as _load_browser_profile_settings,
    load_browser_proxy_base_urls as _load_browser_proxy_base_urls,
)
from crxzipple.core.config_channel_profiles import (
    load_channel_profile_settings as _load_channel_profile_settings,
)
from crxzipple.core.config_env import env_flag as _env_flag
from crxzipple.core.config_llm_profiles import (
    LlmProfileSettings,
    LlmRequestDefaultsSettings,
    load_llm_profile_settings as _load_llm_profile_settings,
    load_llm_request_defaults_settings as _load_llm_request_defaults_settings,
)
from crxzipple.core.config_mobile import (
    MobileDeviceSettings,
    load_mobile_device_settings as _load_mobile_device_settings,
)
from crxzipple.core.config_runtime_guards import (
    ALLOW_FILE_EVENTS_RUNTIME_FALLBACK_ENV,
    ALLOW_SQLITE_MEMORY_INDEX_RUNTIME_ENV,
    ALLOW_SQLITE_RUNTIME_FALLBACK_ENV,
    RuntimeDatabaseGuardError,
    RuntimeEventsBackendGuardError,
    RuntimeMemoryIndexGuardError,
    is_sqlite_database_url,
    require_production_memory_index_acknowledgement,
    require_runtime_database,
    require_shared_events_backend,
)
from crxzipple.core.config_tool_providers import (
    McpProviderSettings,
    OpenApiCredentialBinding,
    OpenApiProviderSettings,
    load_mcp_provider_settings as _load_mcp_provider_settings,
    load_openapi_provider_settings as _load_openapi_provider_settings,
)

if TYPE_CHECKING:
    from crxzipple.modules.channels.domain.value_objects import ChannelProfile

__all__ = [
    "AgentProfileDefaultsSettings",
    "AgentProfileSettings",
    "BrowserProfileSettings",
    "BrowserProxyEndpointSettings",
    "LlmProfileSettings",
    "LlmRequestDefaultsSettings",
    "McpProviderSettings",
    "MobileDeviceSettings",
    "OpenApiCredentialBinding",
    "OpenApiProviderSettings",
    "RuntimeDatabaseGuardError",
    "RuntimeEventsBackendGuardError",
    "RuntimeMemoryIndexGuardError",
    "Settings",
    "is_sqlite_database_url",
    "load_settings",
    "require_production_memory_index_acknowledgement",
    "require_runtime_database",
    "require_shared_events_backend",
]


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_AUTHORIZATION_POLICY_DIR = PROJECT_ROOT / "config" / "authorization_policies"
DEFAULT_AUTHORIZATION_RUNTIME_POLICY_PATH = (
    PROJECT_ROOT / ".crxzipple" / "authorization_runtime.yaml"
)
DEFAULT_WORKSPACE_TOOL_DIR = PROJECT_ROOT / ".crxzipple" / "tools"
DEFAULT_BUNDLED_TOOL_DIR = PROJECT_ROOT / "tools"
DEFAULT_BROWSER_STATE_DIR = PROJECT_ROOT / ".crxzipple" / "browser"
DEFAULT_MOBILE_STATE_DIR = PROJECT_ROOT / ".crxzipple" / "mobile"
DEFAULT_DAEMON_STATE_DIR = PROJECT_ROOT / ".crxzipple" / "daemon"
DEFAULT_EVENTS_STATE_DIR = PROJECT_ROOT / ".crxzipple" / "events"
DEFAULT_OPERATIONS_STATE_DIR = PROJECT_ROOT / ".crxzipple" / "operations"
DEFAULT_CHANNELS_STATE_DIR = PROJECT_ROOT / ".crxzipple" / "channels"
DEFAULT_ACCESS_STATE_DIR = PROJECT_ROOT / ".crxzipple" / "access"
DEFAULT_MEMORY_STATE_DIR = PROJECT_ROOT / ".crxzipple" / "memory"
DEFAULT_ARTIFACT_STORE_DIR = PROJECT_ROOT / ".crxzipple" / "artifacts"
DEFAULT_OCR_BACKEND = "local"
DEFAULT_OCR_PROVIDER = "host"
DEFAULT_OCR_HOST = "127.0.0.1"
DEFAULT_OCR_PORT = 18900
_ALLOWED_EVENTS_BACKENDS = {"file", "redis"}
DEFAULT_EVENTS_BACKEND = "redis"
DEFAULT_EVENTS_REDIS_URL = "redis://127.0.0.1:6379/0"


def _load_events_backend() -> Literal["file", "redis"]:
    raw = os.getenv("APP_EVENTS_BACKEND", DEFAULT_EVENTS_BACKEND).strip().lower()
    if not raw:
        return DEFAULT_EVENTS_BACKEND
    if raw == "redis":
        return "redis"
    if raw == "file":
        return "file"
    raise ValueError("APP_EVENTS_BACKEND must be one of: file, redis.")


def _load_ocr_backend() -> str:
    raw = os.getenv("APP_OCR_BACKEND", DEFAULT_OCR_BACKEND).strip().lower()
    if not raw:
        return DEFAULT_OCR_BACKEND
    if raw in {"local", "remote"}:
        return raw
    raise ValueError("APP_OCR_BACKEND must be one of: local, remote.")


def _load_ocr_provider() -> str:
    raw = os.getenv("APP_OCR_PROVIDER", DEFAULT_OCR_PROVIDER).strip().lower()
    if not raw:
        return DEFAULT_OCR_PROVIDER
    if raw in {"host", "ppstructurev3"}:
        return raw
    raise ValueError("APP_OCR_PROVIDER must be one of: host, ppstructurev3.")


def _resolve_ocr_base_url(*, backend: str, host: str, port: int) -> str:
    explicit = os.getenv("APP_OCR_BASE_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")
    if backend == "remote":
        raise ValueError(
            "APP_OCR_BASE_URL must be set when APP_OCR_BACKEND=remote.",
        )
    return f"http://{host}:{port}"


def _runtime_sqlite_fallback_enabled() -> bool:
    return os.getenv(ALLOW_SQLITE_RUNTIME_FALLBACK_ENV, "").strip() == "1"


def _runtime_file_events_fallback_enabled() -> bool:
    return os.getenv(ALLOW_FILE_EVENTS_RUNTIME_FALLBACK_ENV, "").strip() == "1"


def _runtime_sqlite_memory_index_enabled() -> bool:
    return os.getenv(ALLOW_SQLITE_MEMORY_INDEX_RUNTIME_ENV, "").strip() == "1"


def _load_memory_retrieval_backend() -> str:
    raw = os.getenv("APP_MEMORY_RETRIEVAL_BACKEND", "keyword").strip().lower()
    if not raw:
        return "keyword"
    if raw in {"keyword", "hybrid", "vector"}:
        return raw
    raise ValueError(
        "APP_MEMORY_RETRIEVAL_BACKEND must be one of: keyword, hybrid, vector.",
    )


def _load_memory_vector_provider() -> str:
    raw = os.getenv("APP_MEMORY_VECTOR_PROVIDER", "local").strip().lower()
    if not raw:
        return "local"
    if raw in {"local", "openai_compatible"}:
        return raw
    raise ValueError(
        "APP_MEMORY_VECTOR_PROVIDER must be one of: local, openai_compatible.",
    )


def _load_memory_vector_timeout_seconds() -> int:
    return max(int(os.getenv("APP_MEMORY_VECTOR_TIMEOUT_SECONDS", "30")), 1)


def _load_memory_watch_interval_seconds() -> float:
    return max(float(os.getenv("APP_MEMORY_WATCH_INTERVAL_SECONDS", "300")), 0.0)


def _load_tool_local_paths() -> tuple[str, ...]:
    configured_paths = [
        DEFAULT_WORKSPACE_TOOL_DIR,
        DEFAULT_BUNDLED_TOOL_DIR,
    ]

    unique_paths: list[str] = []
    seen: set[Path] = set()
    for path in configured_paths:
        resolved = path.expanduser().resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_paths.append(str(resolved))
    return tuple(unique_paths)


def _iter_authorization_policy_paths() -> tuple[Path, ...]:
    raw = os.getenv("APP_AUTHORIZATION_POLICY_PATHS", "").strip()
    if raw:
        configured_paths = [
            Path(part.strip()).expanduser()
            for part in raw.split(os.pathsep)
            if part.strip()
        ]
    elif DEFAULT_AUTHORIZATION_POLICY_DIR.exists():
        configured_paths = [DEFAULT_AUTHORIZATION_POLICY_DIR]
    else:
        configured_paths = []

    resolved_files: list[Path] = []
    for path in configured_paths:
        if path.is_dir():
            resolved_files.extend(
                candidate
                for pattern in ("*.yaml", "*.yml", "*.json")
                for candidate in sorted(path.glob(pattern))
                if candidate.is_file()
            )
            continue
        if path.is_file():
            resolved_files.append(path)

    unique_files: list[Path] = []
    seen: set[Path] = set()
    for path in resolved_files:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_files.append(resolved)
    runtime_path = _authorization_runtime_policy_path().resolve()
    if runtime_path not in seen:
        unique_files.append(runtime_path)
    return tuple(unique_files)


def _authorization_runtime_policy_path() -> Path:
    raw = os.getenv("APP_AUTHORIZATION_RUNTIME_POLICY_PATH", "").strip()
    if raw:
        return Path(raw).expanduser()
    return DEFAULT_AUTHORIZATION_RUNTIME_POLICY_PATH


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str
    environment: str
    database_url: str
    sandbox_base_dir: str
    sandbox_backend: str
    sandbox_docker_binary: str
    sandbox_docker_image: str
    log_level: str
    log_json: bool
    allow_sqlite_runtime_fallback: bool = False
    allow_file_events_runtime_fallback: bool = False
    allow_sqlite_memory_index_runtime: bool = False
    tool_local_paths: tuple[str, ...] = ()
    tool_openapi_providers: tuple[OpenApiProviderSettings, ...] = ()
    tool_mcp_providers: tuple[McpProviderSettings, ...] = ()
    llm_profiles: tuple[LlmProfileSettings, ...] = ()
    llm_request_defaults: LlmRequestDefaultsSettings = field(
        default_factory=LlmRequestDefaultsSettings,
    )
    channel_profiles: tuple[ChannelProfile, ...] = ()
    agent_profiles: tuple[AgentProfileSettings, ...] = ()
    authorization_enabled: bool = True
    authorization_policy_paths: tuple[str, ...] = ()
    authorization_runtime_policy_path: str = str(DEFAULT_AUTHORIZATION_RUNTIME_POLICY_PATH)
    memory_retrieval_backend: str = "keyword"
    memory_storage_root: str = str(DEFAULT_MEMORY_STATE_DIR)
    memory_vector_provider: str = "local"
    memory_vector_model: str | None = None
    memory_vector_base_url: str | None = None
    memory_vector_credential_binding_id: str | None = None
    memory_vector_timeout_seconds: int = 30
    memory_watch_interval_seconds: float = 300.0
    browser_enabled: bool = True
    browser_profiles: tuple[BrowserProfileSettings, ...] = field(
        default_factory=lambda: (
            BrowserProfileSettings(name=DEFAULT_BROWSER_DEFAULT_PROFILE_NAME),
        ),
    )
    browser_proxy_base_urls: tuple[BrowserProxyEndpointSettings, ...] = ()
    browser_state_dir: str = str(DEFAULT_BROWSER_STATE_DIR)
    mobile_enabled: bool = True
    mobile_devices: tuple[MobileDeviceSettings, ...] = ()
    mobile_state_dir: str = str(DEFAULT_MOBILE_STATE_DIR)
    ocr_enabled: bool = True
    ocr_backend: str = DEFAULT_OCR_BACKEND
    ocr_provider: str = DEFAULT_OCR_PROVIDER
    ocr_host: str = DEFAULT_OCR_HOST
    ocr_port: int = DEFAULT_OCR_PORT
    ocr_base_url: str = f"http://{DEFAULT_OCR_HOST}:{DEFAULT_OCR_PORT}"
    ocr_language: str = "ch"
    ocr_use_gpu: bool = False
    ocr_request_timeout_seconds: float = 60.0
    daemon_state_dir: str = str(DEFAULT_DAEMON_STATE_DIR)
    events_state_dir: str = str(DEFAULT_EVENTS_STATE_DIR)
    operations_state_dir: str = str(DEFAULT_OPERATIONS_STATE_DIR)
    events_backend: Literal["file", "redis"] = "redis"
    events_file_sync_writes: bool = False
    events_redis_url: str | None = DEFAULT_EVENTS_REDIS_URL
    events_redis_key_prefix: str = "crx:events"
    events_redis_block_ms: int = 1000
    events_redis_dedupe_ttl_seconds: int = 3600
    channels_state_dir: str = str(DEFAULT_CHANNELS_STATE_DIR)
    access_state_dir: str = str(DEFAULT_ACCESS_STATE_DIR)
    mobile_adb_binary: str = "adb"
    artifact_store_dir: str = str(DEFAULT_ARTIFACT_STORE_DIR)
    artifact_image_preview_max_dimension: int = 1024
    artifact_image_llm_max_dimension: int = 1568
    artifact_image_llm_max_bytes: int = 1_500_000
    artifact_file_llm_max_bytes: int = 4_000_000
    artifact_text_file_llm_max_chars: int = 20_000
    tool_details_max_chars: int = 131_072
    tool_remote_default_max_concurrency: int = 16
    browser_executable_path: str | None = None
    browser_sandbox_executable_path: str | None = None
    browser_proxy_base_url: str | None = None
    browser_proxy_egress_check_url: str | None = None
    browser_cdp_host: str = "127.0.0.1"
    browser_cdp_port: int = 18800
    browser_headless: bool = False
    browser_start_timeout_seconds: int = 10
    browser_sandbox_docker_image: str = "python:3.11-slim"
    prompt_system_max_chars: int = 120_000
    prompt_system_max_tokens: int = 30_000
    prompt_system_context_window_ratio: float = 0.15
    orchestration_run_lease_seconds: int = 30
    orchestration_run_heartbeat_seconds: float = 5.0
    orchestration_executor_max_concurrent_assignments: int = 4
    orchestration_detailed_engine_metrics_enabled: bool = False
    orchestration_auto_compaction_enabled: bool = True
    orchestration_auto_compaction_reserve_tokens: int = 20_000
    orchestration_auto_compaction_soft_threshold_tokens: int = 4_000
    tool_run_max_attempts: int = 3
    tool_run_lease_seconds: int = 30
    tool_run_heartbeat_seconds: float = 5.0
    tool_worker_max_in_flight: int = 4
    tool_worker_default_run_concurrency: int = 4
    tool_worker_image_run_concurrency: int = 4
    tool_worker_shared_state_run_concurrency: int = 1

    def __post_init__(self) -> None:
        profiles = _ensure_default_user_browser_profile_settings(
            self.browser_profiles,
        )
        object.__setattr__(
            self,
            "browser_profiles",
            profiles,
        )

    @property
    def browser_profile_specs(self) -> tuple[BrowserProfileSettings, ...]:
        return self.browser_profiles


def load_settings() -> Settings:
    browser_profiles = _load_browser_profile_settings()
    ocr_backend = _load_ocr_backend()
    ocr_provider = _load_ocr_provider()
    ocr_host = os.getenv("APP_OCR_HOST", DEFAULT_OCR_HOST).strip() or DEFAULT_OCR_HOST
    ocr_port = max(int(os.getenv("APP_OCR_PORT", str(DEFAULT_OCR_PORT))), 1)
    tool_worker_max_in_flight = max(
        int(os.getenv("APP_TOOL_WORKER_MAX_IN_FLIGHT", "4")),
        1,
    )
    tool_worker_default_run_concurrency = max(
        int(
            os.getenv(
                "APP_TOOL_WORKER_DEFAULT_RUN_CONCURRENCY",
                str(tool_worker_max_in_flight),
            ),
        ),
        1,
    )
    tool_worker_image_run_concurrency = max(
        int(
            os.getenv(
                "APP_TOOL_WORKER_IMAGE_RUN_CONCURRENCY",
                str(tool_worker_max_in_flight),
            ),
        ),
        1,
    )
    tool_worker_shared_state_run_concurrency = max(
        int(os.getenv("APP_TOOL_WORKER_SHARED_STATE_RUN_CONCURRENCY", "1")),
        1,
    )
    if ocr_backend == "local" and ocr_provider != "host":
        raise ValueError(
            "APP_OCR_PROVIDER must be 'host' when APP_OCR_BACKEND=local.",
        )
    return Settings(
        app_name=os.getenv("APP_NAME", "crxzipple"),
        environment=os.getenv("APP_ENV", "local"),
        database_url=os.getenv("APP_DATABASE_URL", "sqlite:///./crxzipple.db"),
        allow_sqlite_runtime_fallback=_runtime_sqlite_fallback_enabled(),
        allow_file_events_runtime_fallback=_runtime_file_events_fallback_enabled(),
        allow_sqlite_memory_index_runtime=_runtime_sqlite_memory_index_enabled(),
        tool_local_paths=_load_tool_local_paths(),
        tool_openapi_providers=_load_openapi_provider_settings(),
        tool_mcp_providers=_load_mcp_provider_settings(),
        llm_profiles=_load_llm_profile_settings(),
        llm_request_defaults=_load_llm_request_defaults_settings(),
        channel_profiles=_load_channel_profile_settings(),
        agent_profiles=_load_agent_profile_settings(),
        authorization_enabled=_env_flag("APP_AUTHORIZATION_ENABLED", default=True),
        authorization_policy_paths=tuple(
            str(path) for path in _iter_authorization_policy_paths()
        ),
        authorization_runtime_policy_path=str(_authorization_runtime_policy_path()),
        memory_retrieval_backend=_load_memory_retrieval_backend(),
        memory_storage_root=os.getenv(
            "APP_MEMORY_STORAGE_ROOT",
            str(DEFAULT_MEMORY_STATE_DIR),
        ),
        memory_vector_provider=_load_memory_vector_provider(),
        memory_vector_model=(
            os.getenv("APP_MEMORY_VECTOR_MODEL", "").strip() or None
        ),
        memory_vector_base_url=(
            os.getenv("APP_MEMORY_VECTOR_BASE_URL", "").strip() or None
        ),
        memory_vector_credential_binding_id=(
            os.getenv("APP_MEMORY_VECTOR_CREDENTIAL_BINDING_ID", "").strip() or None
        ),
        memory_vector_timeout_seconds=_load_memory_vector_timeout_seconds(),
        memory_watch_interval_seconds=_load_memory_watch_interval_seconds(),
        browser_enabled=_env_flag("APP_BROWSER_ENABLED", default=True),
        browser_profiles=browser_profiles,
        browser_proxy_base_urls=tuple(
            BrowserProxyEndpointSettings(profile=profile, base_url=base_url)
            for profile, base_url in _load_browser_proxy_base_urls()
        ),
        browser_state_dir=os.getenv(
            "APP_BROWSER_STATE_DIR",
            str(DEFAULT_BROWSER_STATE_DIR),
        ),
        mobile_enabled=_env_flag("APP_MOBILE_ENABLED", default=True),
        mobile_devices=_load_mobile_device_settings(),
        mobile_state_dir=os.getenv(
            "APP_MOBILE_STATE_DIR",
            str(DEFAULT_MOBILE_STATE_DIR),
        ),
        ocr_enabled=_env_flag("APP_OCR_ENABLED", default=True),
        ocr_backend=ocr_backend,
        ocr_provider=ocr_provider,
        ocr_host=ocr_host,
        ocr_port=ocr_port,
        ocr_base_url=_resolve_ocr_base_url(
            backend=ocr_backend,
            host=ocr_host,
            port=ocr_port,
        ),
        ocr_language=os.getenv("APP_OCR_LANGUAGE", "ch").strip() or "ch",
        ocr_use_gpu=_env_flag("APP_OCR_USE_GPU", default=False),
        ocr_request_timeout_seconds=max(
            float(os.getenv("APP_OCR_REQUEST_TIMEOUT_SECONDS", "60")),
            0.1,
        ),
        daemon_state_dir=os.getenv(
            "APP_DAEMON_STATE_DIR",
            str(DEFAULT_DAEMON_STATE_DIR),
        ),
        events_state_dir=os.getenv(
            "APP_EVENTS_STATE_DIR",
            str(DEFAULT_EVENTS_STATE_DIR),
        ),
        operations_state_dir=os.getenv(
            "APP_OPERATIONS_STATE_DIR",
            str(DEFAULT_OPERATIONS_STATE_DIR),
        ),
        events_backend=_load_events_backend(),
        events_file_sync_writes=_env_flag(
            "APP_EVENTS_FILE_SYNC_WRITES",
            default=False,
        ),
        events_redis_url=(
            os.getenv(
                "APP_EVENTS_REDIS_URL",
                DEFAULT_EVENTS_REDIS_URL,
            ).strip()
            or DEFAULT_EVENTS_REDIS_URL
        ),
        events_redis_key_prefix=(
            os.getenv("APP_EVENTS_REDIS_KEY_PREFIX", "crx:events").strip()
            or "crx:events"
        ),
        events_redis_block_ms=max(
            int(os.getenv("APP_EVENTS_REDIS_BLOCK_MS", "1000")),
            1,
        ),
        events_redis_dedupe_ttl_seconds=max(
            int(os.getenv("APP_EVENTS_REDIS_DEDUPE_TTL_SECONDS", "3600")),
            1,
        ),
        channels_state_dir=os.getenv(
            "APP_CHANNELS_STATE_DIR",
            str(DEFAULT_CHANNELS_STATE_DIR),
        ),
        access_state_dir=os.getenv(
            "APP_ACCESS_STATE_DIR",
            str(DEFAULT_ACCESS_STATE_DIR),
        ),
        mobile_adb_binary=os.getenv("APP_MOBILE_ADB_BINARY", "adb").strip() or "adb",
        artifact_store_dir=os.getenv(
            "APP_ARTIFACT_STORE_DIR",
            str(DEFAULT_ARTIFACT_STORE_DIR),
        ),
        artifact_image_preview_max_dimension=max(
            int(os.getenv("APP_ARTIFACT_IMAGE_PREVIEW_MAX_DIMENSION", "1024")),
            1,
        ),
        artifact_image_llm_max_dimension=max(
            int(os.getenv("APP_ARTIFACT_IMAGE_LLM_MAX_DIMENSION", "1568")),
            1,
        ),
        artifact_image_llm_max_bytes=max(
            int(os.getenv("APP_ARTIFACT_IMAGE_LLM_MAX_BYTES", "1500000")),
            1,
        ),
        artifact_file_llm_max_bytes=max(
            int(os.getenv("APP_ARTIFACT_FILE_LLM_MAX_BYTES", "4000000")),
            1,
        ),
        artifact_text_file_llm_max_chars=max(
            int(os.getenv("APP_ARTIFACT_TEXT_FILE_LLM_MAX_CHARS", "20000")),
            1,
        ),
        tool_details_max_chars=max(
            int(os.getenv("APP_TOOL_DETAILS_MAX_CHARS", "131072")),
            1,
        ),
        tool_remote_default_max_concurrency=max(
            int(os.getenv("APP_TOOL_REMOTE_DEFAULT_MAX_CONCURRENCY", "16")),
            1,
        ),
        browser_executable_path=(
            os.getenv("APP_BROWSER_EXECUTABLE_PATH", "").strip() or None
        ),
        browser_sandbox_executable_path=(
            os.getenv("APP_BROWSER_SANDBOX_EXECUTABLE_PATH", "").strip() or None
        ),
        browser_proxy_base_url=(
            os.getenv("APP_BROWSER_PROXY_BASE_URL", "").strip() or None
        ),
        browser_proxy_egress_check_url=(
            os.getenv("APP_BROWSER_PROXY_EGRESS_CHECK_URL", "").strip() or None
        ),
        browser_cdp_host=os.getenv("APP_BROWSER_CDP_HOST", "127.0.0.1").strip()
        or "127.0.0.1",
        browser_cdp_port=max(int(os.getenv("APP_BROWSER_CDP_PORT", "18800")), 1),
        browser_headless=_env_flag("APP_BROWSER_HEADLESS", default=False),
        browser_start_timeout_seconds=max(
            int(os.getenv("APP_BROWSER_START_TIMEOUT_SECONDS", "10")),
            1,
        ),
        browser_sandbox_docker_image=os.getenv(
            "APP_BROWSER_SANDBOX_DOCKER_IMAGE",
            os.getenv(
                "APP_SANDBOX_DOCKER_IMAGE",
                "python:3.11-slim",
            ),
        ).strip()
        or os.getenv(
            "APP_SANDBOX_DOCKER_IMAGE",
            "python:3.11-slim",
        ).strip()
        or "python:3.11-slim",
        prompt_system_max_chars=max(
            int(os.getenv("APP_PROMPT_SYSTEM_MAX_CHARS", "120000")),
            1,
        ),
        prompt_system_max_tokens=max(
            int(os.getenv("APP_PROMPT_SYSTEM_MAX_TOKENS", "30000")),
            1,
        ),
        prompt_system_context_window_ratio=max(
            float(os.getenv("APP_PROMPT_SYSTEM_CONTEXT_WINDOW_RATIO", "0.15")),
            0.01,
        ),
        orchestration_run_lease_seconds=max(
            int(os.getenv("APP_ORCHESTRATION_RUN_LEASE_SECONDS", "30")),
            1,
        ),
        orchestration_run_heartbeat_seconds=max(
            float(os.getenv("APP_ORCHESTRATION_RUN_HEARTBEAT_SECONDS", "5")),
            0.1,
        ),
        orchestration_executor_max_concurrent_assignments=max(
            int(
                os.getenv(
                    "APP_ORCHESTRATION_EXECUTOR_MAX_CONCURRENT_ASSIGNMENTS",
                    "4",
                ),
            ),
            1,
        ),
        orchestration_detailed_engine_metrics_enabled=_env_flag(
            "APP_ORCHESTRATION_DETAILED_ENGINE_METRICS_ENABLED",
            default=False,
        ),
        orchestration_auto_compaction_enabled=_env_flag(
            "APP_ORCHESTRATION_AUTO_COMPACTION_ENABLED",
            default=True,
        ),
        orchestration_auto_compaction_reserve_tokens=max(
            int(
                os.getenv(
                    "APP_ORCHESTRATION_AUTO_COMPACTION_RESERVE_TOKENS",
                    "20000",
                ),
            ),
            0,
        ),
        orchestration_auto_compaction_soft_threshold_tokens=max(
            int(
                os.getenv(
                    "APP_ORCHESTRATION_AUTO_COMPACTION_SOFT_THRESHOLD_TOKENS",
                    "4000",
                ),
            ),
            0,
        ),
        tool_run_max_attempts=max(int(os.getenv("APP_TOOL_RUN_MAX_ATTEMPTS", "3")), 1),
        tool_run_lease_seconds=max(int(os.getenv("APP_TOOL_RUN_LEASE_SECONDS", "30")), 1),
        tool_run_heartbeat_seconds=max(
            float(os.getenv("APP_TOOL_RUN_HEARTBEAT_SECONDS", "5")),
            0.1,
        ),
        tool_worker_max_in_flight=tool_worker_max_in_flight,
        tool_worker_default_run_concurrency=tool_worker_default_run_concurrency,
        tool_worker_image_run_concurrency=tool_worker_image_run_concurrency,
        tool_worker_shared_state_run_concurrency=tool_worker_shared_state_run_concurrency,
        sandbox_base_dir=os.getenv(
            "APP_SANDBOX_BASE_DIR",
            os.path.join(tempfile.gettempdir(), "crxzipple-sandboxes"),
        ),
        sandbox_backend=os.getenv("APP_SANDBOX_BACKEND", "subprocess").strip().lower(),
        sandbox_docker_binary=os.getenv("APP_SANDBOX_DOCKER_BINARY", "docker"),
        sandbox_docker_image=os.getenv(
            "APP_SANDBOX_DOCKER_IMAGE",
            "python:3.11-slim",
        ),
        log_level=os.getenv("APP_LOG_LEVEL", "INFO").upper(),
        log_json=_env_flag("APP_LOG_JSON", default=False),
    )
