from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from crxzipple.core.config_agent_profiles import (
    AgentProfileSettings,
)
from crxzipple.core.config_artifacts import (
    DEFAULT_ARTIFACT_FILE_LLM_MAX_BYTES,
    DEFAULT_ARTIFACT_IMAGE_LLM_MAX_BYTES,
    DEFAULT_ARTIFACT_IMAGE_LLM_MAX_DIMENSION,
    DEFAULT_ARTIFACT_IMAGE_PREVIEW_MAX_DIMENSION,
    DEFAULT_ARTIFACT_STORE_DIR,
    DEFAULT_ARTIFACT_TEXT_FILE_LLM_MAX_CHARS,
)
from crxzipple.core.config_authorization import (
    DEFAULT_AUTHORIZATION_RUNTIME_POLICY_PATH,
)
from crxzipple.core.config_browser import (
    DEFAULT_BROWSER_DEFAULT_PROFILE_NAME,
    BrowserProfileSettings,
    BrowserProxyEndpointSettings,
    ensure_default_user_browser_profile_settings as _ensure_default_user_browser_profile_settings,
)
from crxzipple.core.config_browser_runtime import (
    DEFAULT_BROWSER_CDP_HOST,
    DEFAULT_BROWSER_CDP_PORT,
    DEFAULT_BROWSER_HEADLESS,
    DEFAULT_BROWSER_SANDBOX_DOCKER_IMAGE,
    DEFAULT_BROWSER_START_TIMEOUT_SECONDS,
)
from crxzipple.core.config_events import (
    DEFAULT_EVENTS_REDIS_BLOCK_MS,
    DEFAULT_EVENTS_REDIS_DEDUPE_TTL_SECONDS,
    DEFAULT_EVENTS_REDIS_KEY_PREFIX,
    DEFAULT_EVENTS_REDIS_URL,
)
from crxzipple.core.config_llm_profiles import (
    LlmProfileSettings,
    LlmRequestDefaultsSettings,
)
from crxzipple.core.config_mobile import MobileDeviceSettings
from crxzipple.core.config_ocr import (
    DEFAULT_OCR_BACKEND,
    DEFAULT_OCR_HOST,
    DEFAULT_OCR_PORT,
    DEFAULT_OCR_PROVIDER,
)
from crxzipple.core.config_orchestration_runtime import (
    DEFAULT_ORCHESTRATION_AUTO_COMPACTION_ENABLED,
    DEFAULT_ORCHESTRATION_AUTO_COMPACTION_RESERVE_TOKENS,
    DEFAULT_ORCHESTRATION_AUTO_COMPACTION_SOFT_THRESHOLD_TOKENS,
    DEFAULT_ORCHESTRATION_DETAILED_ENGINE_METRICS_ENABLED,
    DEFAULT_ORCHESTRATION_EXECUTOR_MAX_CONCURRENT_ASSIGNMENTS,
    DEFAULT_ORCHESTRATION_RUN_HEARTBEAT_SECONDS,
    DEFAULT_ORCHESTRATION_RUN_LEASE_SECONDS,
)
from crxzipple.core.config_paths import (
    DEFAULT_ACCESS_STATE_DIR,
    DEFAULT_BROWSER_STATE_DIR,
    DEFAULT_CHANNELS_STATE_DIR,
    DEFAULT_DAEMON_STATE_DIR,
    DEFAULT_EVENTS_STATE_DIR,
    DEFAULT_MEMORY_STATE_DIR,
    DEFAULT_MOBILE_STATE_DIR,
    DEFAULT_OPERATIONS_STATE_DIR,
)
from crxzipple.core.config_prompt import (
    DEFAULT_PROMPT_SYSTEM_CONTEXT_WINDOW_RATIO,
    DEFAULT_PROMPT_SYSTEM_MAX_CHARS,
    DEFAULT_PROMPT_SYSTEM_MAX_TOKENS,
)
from crxzipple.core.config_sandbox import (
    DEFAULT_SANDBOX_BACKEND,
    DEFAULT_SANDBOX_BASE_DIR,
    DEFAULT_SANDBOX_DOCKER_BINARY,
    DEFAULT_SANDBOX_DOCKER_IMAGE,
)
from crxzipple.core.config_logging import (
    DEFAULT_LOG_JSON,
    DEFAULT_LOG_LEVEL,
)
from crxzipple.core.config_tool_providers import (
    McpProviderSettings,
    OpenApiProviderSettings,
)
from crxzipple.core.config_tool_runtime import (
    DEFAULT_TOOL_DETAILS_MAX_CHARS,
    DEFAULT_TOOL_REMOTE_DEFAULT_MAX_CONCURRENCY,
    DEFAULT_TOOL_RUN_HEARTBEAT_SECONDS,
    DEFAULT_TOOL_RUN_LEASE_SECONDS,
    DEFAULT_TOOL_RUN_MAX_ATTEMPTS,
    DEFAULT_TOOL_WORKER_MAX_IN_FLIGHT,
    DEFAULT_TOOL_WORKER_SHARED_STATE_RUN_CONCURRENCY,
)

if TYPE_CHECKING:
    from crxzipple.modules.channels.domain.value_objects import ChannelProfile


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str = "crxzipple"
    environment: str = "local"
    database_url: str = "sqlite:///./crxzipple.db"
    sandbox_base_dir: str = DEFAULT_SANDBOX_BASE_DIR
    sandbox_backend: str = DEFAULT_SANDBOX_BACKEND
    sandbox_docker_binary: str = DEFAULT_SANDBOX_DOCKER_BINARY
    sandbox_docker_image: str = DEFAULT_SANDBOX_DOCKER_IMAGE
    log_level: str = DEFAULT_LOG_LEVEL
    log_json: bool = DEFAULT_LOG_JSON
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
    ocr_max_concurrent_requests: int = 1
    daemon_state_dir: str = str(DEFAULT_DAEMON_STATE_DIR)
    events_state_dir: str = str(DEFAULT_EVENTS_STATE_DIR)
    operations_state_dir: str = str(DEFAULT_OPERATIONS_STATE_DIR)
    events_backend: Literal["file", "redis"] = "redis"
    events_file_sync_writes: bool = False
    events_redis_url: str | None = DEFAULT_EVENTS_REDIS_URL
    events_redis_key_prefix: str = DEFAULT_EVENTS_REDIS_KEY_PREFIX
    events_redis_block_ms: int = DEFAULT_EVENTS_REDIS_BLOCK_MS
    events_redis_dedupe_ttl_seconds: int = DEFAULT_EVENTS_REDIS_DEDUPE_TTL_SECONDS
    channels_state_dir: str = str(DEFAULT_CHANNELS_STATE_DIR)
    access_state_dir: str = str(DEFAULT_ACCESS_STATE_DIR)
    mobile_adb_binary: str = "adb"
    artifact_store_dir: str = str(DEFAULT_ARTIFACT_STORE_DIR)
    artifact_image_preview_max_dimension: int = (
        DEFAULT_ARTIFACT_IMAGE_PREVIEW_MAX_DIMENSION
    )
    artifact_image_llm_max_dimension: int = DEFAULT_ARTIFACT_IMAGE_LLM_MAX_DIMENSION
    artifact_image_llm_max_bytes: int = DEFAULT_ARTIFACT_IMAGE_LLM_MAX_BYTES
    artifact_file_llm_max_bytes: int = DEFAULT_ARTIFACT_FILE_LLM_MAX_BYTES
    artifact_text_file_llm_max_chars: int = DEFAULT_ARTIFACT_TEXT_FILE_LLM_MAX_CHARS
    tool_details_max_chars: int = DEFAULT_TOOL_DETAILS_MAX_CHARS
    tool_remote_default_max_concurrency: int = DEFAULT_TOOL_REMOTE_DEFAULT_MAX_CONCURRENCY
    browser_executable_path: str | None = None
    browser_sandbox_executable_path: str | None = None
    browser_proxy_base_url: str | None = None
    browser_proxy_egress_check_url: str | None = None
    browser_cdp_host: str = DEFAULT_BROWSER_CDP_HOST
    browser_cdp_port: int = DEFAULT_BROWSER_CDP_PORT
    browser_headless: bool = DEFAULT_BROWSER_HEADLESS
    browser_start_timeout_seconds: int = DEFAULT_BROWSER_START_TIMEOUT_SECONDS
    browser_sandbox_docker_image: str = DEFAULT_BROWSER_SANDBOX_DOCKER_IMAGE
    prompt_system_max_chars: int = DEFAULT_PROMPT_SYSTEM_MAX_CHARS
    prompt_system_max_tokens: int = DEFAULT_PROMPT_SYSTEM_MAX_TOKENS
    prompt_system_context_window_ratio: float = DEFAULT_PROMPT_SYSTEM_CONTEXT_WINDOW_RATIO
    orchestration_run_lease_seconds: int = DEFAULT_ORCHESTRATION_RUN_LEASE_SECONDS
    orchestration_run_heartbeat_seconds: float = (
        DEFAULT_ORCHESTRATION_RUN_HEARTBEAT_SECONDS
    )
    orchestration_executor_max_concurrent_assignments: int = (
        DEFAULT_ORCHESTRATION_EXECUTOR_MAX_CONCURRENT_ASSIGNMENTS
    )
    orchestration_detailed_engine_metrics_enabled: bool = (
        DEFAULT_ORCHESTRATION_DETAILED_ENGINE_METRICS_ENABLED
    )
    orchestration_auto_compaction_enabled: bool = (
        DEFAULT_ORCHESTRATION_AUTO_COMPACTION_ENABLED
    )
    orchestration_auto_compaction_reserve_tokens: int = (
        DEFAULT_ORCHESTRATION_AUTO_COMPACTION_RESERVE_TOKENS
    )
    orchestration_auto_compaction_soft_threshold_tokens: int = (
        DEFAULT_ORCHESTRATION_AUTO_COMPACTION_SOFT_THRESHOLD_TOKENS
    )
    tool_run_max_attempts: int = DEFAULT_TOOL_RUN_MAX_ATTEMPTS
    tool_run_lease_seconds: int = DEFAULT_TOOL_RUN_LEASE_SECONDS
    tool_run_heartbeat_seconds: float = DEFAULT_TOOL_RUN_HEARTBEAT_SECONDS
    tool_worker_max_in_flight: int = DEFAULT_TOOL_WORKER_MAX_IN_FLIGHT
    tool_worker_default_run_concurrency: int = DEFAULT_TOOL_WORKER_MAX_IN_FLIGHT
    tool_worker_image_run_concurrency: int = DEFAULT_TOOL_WORKER_MAX_IN_FLIGHT
    tool_worker_shared_state_run_concurrency: int = (
        DEFAULT_TOOL_WORKER_SHARED_STATE_RUN_CONCURRENCY
    )

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
