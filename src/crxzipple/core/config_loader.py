from __future__ import annotations

import os

from crxzipple.core.config_agent_profiles import (
    load_agent_profile_settings as _load_agent_profile_settings,
)
from crxzipple.core.config_artifacts import (
    load_artifact_file_llm_max_bytes as _load_artifact_file_llm_max_bytes,
    load_artifact_image_llm_max_bytes as _load_artifact_image_llm_max_bytes,
    load_artifact_image_llm_max_dimension as _load_artifact_image_llm_max_dimension,
    load_artifact_image_preview_max_dimension as _load_artifact_image_preview_max_dimension,
    load_artifact_store_dir as _load_artifact_store_dir,
    load_artifact_text_file_llm_max_chars as _load_artifact_text_file_llm_max_chars,
)
from crxzipple.core.config_authorization import (
    authorization_runtime_policy_path as _authorization_runtime_policy_path,
    iter_authorization_policy_paths as _iter_authorization_policy_paths,
    load_authorization_enabled as _load_authorization_enabled,
)
from crxzipple.core.config_browser import (
    BrowserProxyEndpointSettings,
    load_browser_profile_settings as _load_browser_profile_settings,
    load_browser_proxy_base_urls as _load_browser_proxy_base_urls,
)
from crxzipple.core.config_browser_runtime import (
    load_browser_cdp_host as _load_browser_cdp_host,
    load_browser_cdp_port as _load_browser_cdp_port,
    load_browser_executable_path as _load_browser_executable_path,
    load_browser_headless as _load_browser_headless,
    load_browser_proxy_base_url as _load_browser_proxy_base_url,
    load_browser_proxy_egress_check_url as _load_browser_proxy_egress_check_url,
    load_browser_sandbox_docker_image as _load_browser_sandbox_docker_image,
    load_browser_sandbox_executable_path as _load_browser_sandbox_executable_path,
    load_browser_start_timeout_seconds as _load_browser_start_timeout_seconds,
)
from crxzipple.core.config_channel_profiles import (
    load_channel_profile_settings as _load_channel_profile_settings,
)
from crxzipple.core.config_env import env_flag as _env_flag
from crxzipple.core.config_events import (
    load_events_backend as _load_events_backend,
    load_events_file_sync_writes as _load_events_file_sync_writes,
    load_events_redis_block_ms as _load_events_redis_block_ms,
    load_events_redis_dedupe_ttl_seconds as _load_events_redis_dedupe_ttl_seconds,
    load_events_redis_key_prefix as _load_events_redis_key_prefix,
    load_events_redis_url as _load_events_redis_url,
)
from crxzipple.core.config_llm_profiles import (
    load_llm_profile_settings as _load_llm_profile_settings,
    load_llm_request_defaults_settings as _load_llm_request_defaults_settings,
)
from crxzipple.core.config_logging import (
    load_log_json as _load_log_json,
    load_log_level as _load_log_level,
)
from crxzipple.core.config_memory import (
    load_memory_retrieval_backend as _load_memory_retrieval_backend,
    load_memory_vector_provider as _load_memory_vector_provider,
    load_memory_vector_timeout_seconds as _load_memory_vector_timeout_seconds,
    load_memory_watch_interval_seconds as _load_memory_watch_interval_seconds,
)
from crxzipple.core.config_mobile import (
    load_mobile_device_settings as _load_mobile_device_settings,
)
from crxzipple.core.config_ocr import (
    load_ocr_backend as _load_ocr_backend,
    load_ocr_host as _load_ocr_host,
    load_ocr_port as _load_ocr_port,
    load_ocr_provider as _load_ocr_provider,
    resolve_ocr_base_url as _resolve_ocr_base_url,
    validate_ocr_backend_provider as _validate_ocr_backend_provider,
)
from crxzipple.core.config_orchestration_runtime import (
    load_orchestration_auto_compaction_enabled as _load_orchestration_auto_compaction_enabled,
    load_orchestration_auto_compaction_reserve_tokens as _load_orchestration_auto_compaction_reserve_tokens,
    load_orchestration_auto_compaction_soft_threshold_tokens as _load_orchestration_auto_compaction_soft_threshold_tokens,
    load_orchestration_detailed_engine_metrics_enabled as _load_orchestration_detailed_engine_metrics_enabled,
    load_orchestration_executor_max_concurrent_assignments as _load_orchestration_executor_max_concurrent_assignments,
    load_orchestration_run_heartbeat_seconds as _load_orchestration_run_heartbeat_seconds,
    load_orchestration_run_lease_seconds as _load_orchestration_run_lease_seconds,
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
    load_tool_local_paths as _load_tool_local_paths,
)
from crxzipple.core.config_prompt import (
    load_prompt_system_context_window_ratio as _load_prompt_system_context_window_ratio,
    load_prompt_system_max_chars as _load_prompt_system_max_chars,
    load_prompt_system_max_tokens as _load_prompt_system_max_tokens,
)
from crxzipple.core.config_runtime_guards import (
    ALLOW_FILE_EVENTS_RUNTIME_FALLBACK_ENV,
    ALLOW_SQLITE_MEMORY_INDEX_RUNTIME_ENV,
    ALLOW_SQLITE_RUNTIME_FALLBACK_ENV,
)
from crxzipple.core.config_sandbox import (
    load_sandbox_backend as _load_sandbox_backend,
    load_sandbox_base_dir as _load_sandbox_base_dir,
    load_sandbox_docker_binary as _load_sandbox_docker_binary,
    load_sandbox_docker_image as _load_sandbox_docker_image,
)
from crxzipple.core.config_settings import Settings
from crxzipple.core.config_tool_providers import (
    load_mcp_provider_settings as _load_mcp_provider_settings,
    load_openapi_provider_settings as _load_openapi_provider_settings,
)
from crxzipple.core.config_tool_runtime import (
    load_tool_details_max_chars as _load_tool_details_max_chars,
    load_tool_remote_default_max_concurrency as _load_tool_remote_default_max_concurrency,
    load_tool_run_heartbeat_seconds as _load_tool_run_heartbeat_seconds,
    load_tool_run_lease_seconds as _load_tool_run_lease_seconds,
    load_tool_run_max_attempts as _load_tool_run_max_attempts,
    load_tool_worker_concurrency_settings as _load_tool_worker_concurrency_settings,
)


def _runtime_sqlite_fallback_enabled() -> bool:
    return os.getenv(ALLOW_SQLITE_RUNTIME_FALLBACK_ENV, "").strip() == "1"


def _runtime_file_events_fallback_enabled() -> bool:
    return os.getenv(ALLOW_FILE_EVENTS_RUNTIME_FALLBACK_ENV, "").strip() == "1"


def _runtime_sqlite_memory_index_enabled() -> bool:
    return os.getenv(ALLOW_SQLITE_MEMORY_INDEX_RUNTIME_ENV, "").strip() == "1"


def load_settings() -> Settings:
    browser_profiles = _load_browser_profile_settings()
    ocr_backend = _load_ocr_backend()
    ocr_provider = _load_ocr_provider()
    ocr_host = _load_ocr_host()
    ocr_port = _load_ocr_port()
    tool_worker_concurrency = _load_tool_worker_concurrency_settings()
    _validate_ocr_backend_provider(backend=ocr_backend, provider=ocr_provider)
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
        authorization_enabled=_load_authorization_enabled(),
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
        ocr_max_concurrent_requests=max(
            int(os.getenv("APP_OCR_MAX_CONCURRENT_REQUESTS", "1")),
            1,
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
        events_file_sync_writes=_load_events_file_sync_writes(),
        events_redis_url=_load_events_redis_url(),
        events_redis_key_prefix=_load_events_redis_key_prefix(),
        events_redis_block_ms=_load_events_redis_block_ms(),
        events_redis_dedupe_ttl_seconds=_load_events_redis_dedupe_ttl_seconds(),
        channels_state_dir=os.getenv(
            "APP_CHANNELS_STATE_DIR",
            str(DEFAULT_CHANNELS_STATE_DIR),
        ),
        access_state_dir=os.getenv(
            "APP_ACCESS_STATE_DIR",
            str(DEFAULT_ACCESS_STATE_DIR),
        ),
        mobile_adb_binary=os.getenv("APP_MOBILE_ADB_BINARY", "adb").strip() or "adb",
        artifact_store_dir=_load_artifact_store_dir(),
        artifact_image_preview_max_dimension=(
            _load_artifact_image_preview_max_dimension()
        ),
        artifact_image_llm_max_dimension=_load_artifact_image_llm_max_dimension(),
        artifact_image_llm_max_bytes=_load_artifact_image_llm_max_bytes(),
        artifact_file_llm_max_bytes=_load_artifact_file_llm_max_bytes(),
        artifact_text_file_llm_max_chars=_load_artifact_text_file_llm_max_chars(),
        tool_details_max_chars=_load_tool_details_max_chars(),
        tool_remote_default_max_concurrency=_load_tool_remote_default_max_concurrency(),
        browser_executable_path=_load_browser_executable_path(),
        browser_sandbox_executable_path=_load_browser_sandbox_executable_path(),
        browser_proxy_base_url=_load_browser_proxy_base_url(),
        browser_proxy_egress_check_url=_load_browser_proxy_egress_check_url(),
        browser_cdp_host=_load_browser_cdp_host(),
        browser_cdp_port=_load_browser_cdp_port(),
        browser_headless=_load_browser_headless(),
        browser_start_timeout_seconds=_load_browser_start_timeout_seconds(),
        browser_sandbox_docker_image=_load_browser_sandbox_docker_image(),
        prompt_system_max_chars=_load_prompt_system_max_chars(),
        prompt_system_max_tokens=_load_prompt_system_max_tokens(),
        prompt_system_context_window_ratio=(
            _load_prompt_system_context_window_ratio()
        ),
        orchestration_run_lease_seconds=_load_orchestration_run_lease_seconds(),
        orchestration_run_heartbeat_seconds=(
            _load_orchestration_run_heartbeat_seconds()
        ),
        orchestration_executor_max_concurrent_assignments=(
            _load_orchestration_executor_max_concurrent_assignments()
        ),
        orchestration_detailed_engine_metrics_enabled=(
            _load_orchestration_detailed_engine_metrics_enabled()
        ),
        orchestration_auto_compaction_enabled=(
            _load_orchestration_auto_compaction_enabled()
        ),
        orchestration_auto_compaction_reserve_tokens=(
            _load_orchestration_auto_compaction_reserve_tokens()
        ),
        orchestration_auto_compaction_soft_threshold_tokens=(
            _load_orchestration_auto_compaction_soft_threshold_tokens()
        ),
        tool_run_max_attempts=_load_tool_run_max_attempts(),
        tool_run_lease_seconds=_load_tool_run_lease_seconds(),
        tool_run_heartbeat_seconds=_load_tool_run_heartbeat_seconds(),
        tool_worker_max_in_flight=tool_worker_concurrency.max_in_flight,
        tool_worker_default_run_concurrency=(
            tool_worker_concurrency.default_run_concurrency
        ),
        tool_worker_image_run_concurrency=tool_worker_concurrency.image_run_concurrency,
        tool_worker_shared_state_run_concurrency=(
            tool_worker_concurrency.shared_state_run_concurrency
        ),
        sandbox_base_dir=_load_sandbox_base_dir(),
        sandbox_backend=_load_sandbox_backend(),
        sandbox_docker_binary=_load_sandbox_docker_binary(),
        sandbox_docker_image=_load_sandbox_docker_image(),
        log_level=_load_log_level(),
        log_json=_load_log_json(),
    )
