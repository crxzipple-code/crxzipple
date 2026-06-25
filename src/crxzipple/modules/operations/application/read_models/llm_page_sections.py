from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.llm_error_sections import (
    error_summary_section,
)
from crxzipple.modules.operations.application.read_models.llm_invocation_details import (
    invocation_details,
)
from crxzipple.modules.operations.application.read_models.llm_invocation_filters import (
    has_invocation_filters,
    invocations_empty_state,
)
from crxzipple.modules.operations.application.read_models.llm_invocation_tables import (
    failed_invocations_section,
    recent_invocations_section,
    streaming_requests_section,
)
from crxzipple.modules.operations.application.read_models.llm_lifecycle_events import (
    llm_lifecycle_events_section,
)
from crxzipple.modules.operations.application.read_models.llm_limiter_queue_sections import (
    limiter_queue_section,
)
from crxzipple.modules.operations.application.read_models.llm_page_facts import (
    LlmPageFacts,
)
from crxzipple.modules.operations.application.read_models.llm_provider_warmup import (
    latest_warmup_events_by_profile,
)
from crxzipple.modules.operations.application.read_models.llm_provider_sections import (
    model_availability_section,
    provider_access_health_section,
    provider_auth_blocked_section,
)
from crxzipple.modules.operations.application.read_models.llm_rate_limiter_sections import (
    execution_blocking_risk_section,
    rate_limiter_section,
)
from crxzipple.modules.operations.application.read_models.llm_resolver_problem_sections import (
    fallback_problems_section,
)
from crxzipple.modules.operations.application.read_models.llm_resolver_sections import (
    model_resolver_section,
)
from crxzipple.modules.operations.application.read_models.llm_stream_sections import (
    stream_health_section,
)
from crxzipple.modules.operations.application.read_models.llm_usage_sections import (
    context_pressure_section,
    invocation_rate_section,
    latency_section,
    token_usage_section,
)


def llm_page_sections(
    *,
    facts: LlmPageFacts,
    access_service: Any | None,
) -> dict[str, Any]:
    warmup_events_by_profile = latest_warmup_events_by_profile(facts.observed_events)
    failed_empty_state = (
        invocations_empty_state(facts.query)
        if has_invocation_filters(facts.query)
        else "No failed LLM invocations."
    )
    return {
        "provider_access_health": provider_access_health_section(
            facts.profiles,
            invocations=facts.invocations,
            access_service=access_service,
            warmup_events_by_profile=warmup_events_by_profile,
        ),
        "provider_auth_blocked": provider_auth_blocked_section(
            facts.profiles,
            invocations=facts.invocations,
            access_service=access_service,
            warmup_events_by_profile=warmup_events_by_profile,
        ),
        "model_resolver": model_resolver_section(facts.resolver_events),
        "rate_limiter": rate_limiter_section(
            facts.profiles,
            runtime_snapshot=facts.runtime_snapshot,
        ),
        "limiter_queue": limiter_queue_section(
            facts.profiles,
            runtime_snapshot=facts.runtime_snapshot,
        ),
        "streaming_requests": streaming_requests_section(
            facts.streaming_invocations,
            profiles_by_id=facts.profiles_by_id,
            events_by_invocation=facts.events_by_invocation,
            run_contexts=facts.run_contexts,
            now=facts.now,
        ),
        "recent_invocations": recent_invocations_section(
            facts.visible_invocations,
            profiles_by_id=facts.profiles_by_id,
            observed_events=facts.observed_events,
            events_by_invocation=facts.events_by_invocation,
            run_contexts=facts.run_contexts,
            total_count=len(facts.filtered_invocations),
            empty_state=invocations_empty_state(facts.query),
        ),
        "failed_invocations": failed_invocations_section(
            facts.filtered_failed_invocations[:50],
            profiles_by_id=facts.profiles_by_id,
            observed_events=facts.observed_events,
            events_by_invocation=facts.events_by_invocation,
            run_contexts=facts.run_contexts,
            total_count=len(facts.filtered_failed_invocations),
            empty_state=failed_empty_state,
        ),
        "latency": latency_section(
            facts.invocations,
            profiles_by_id=facts.profiles_by_id,
        ),
        "token_usage": token_usage_section(facts.invocations),
        "invocation_rate": invocation_rate_section(facts.invocations),
        "stream_health": stream_health_section(
            facts.profiles,
            streaming_invocations=facts.streaming_invocations,
            observed_events=facts.observed_events,
            now=facts.now,
        ),
        "execution_blocking_risk": execution_blocking_risk_section(
            facts.profiles,
            active_invocations=facts.active_invocations,
            runtime_snapshot=facts.runtime_snapshot,
            now=facts.now,
        ),
        "fallback_problems": fallback_problems_section(facts.resolver_events),
        "context_pressure": context_pressure_section(
            facts.invocations,
            profiles_by_id=facts.profiles_by_id,
        ),
        "model_availability": model_availability_section(
            facts.profiles,
            access_service=access_service,
        ),
        "error_summary": error_summary_section(facts.failed_invocations),
        "llm_lifecycle_events": llm_lifecycle_events_section(facts.observed_events),
        "invocation_details": invocation_details(
            facts.detail_invocations,
            profiles_by_id=facts.profiles_by_id,
            events_by_invocation=facts.events_by_invocation,
            run_contexts=facts.run_contexts,
            resolver_events_by_run_id=facts.resolver_events_by_run_id,
            observed_events=facts.observed_events,
            response_events_by_invocation=facts.response_events_by_invocation,
            response_event_retention_policy=facts.response_event_retention_policy,
        ),
    }
