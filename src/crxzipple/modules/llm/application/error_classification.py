from __future__ import annotations


def llm_error_family(error_code: str) -> str:
    text = error_code.lower()
    if any(token in text for token in ("rate", "quota", "429")):
        return "rate_limit"
    if any(token in text for token in ("auth", "access", "credential", "401", "403")):
        return "auth"
    if "timeout" in text:
        return "timeout"
    if any(token in text for token in ("context", "token", "length")):
        return "context_length"
    if any(token in text for token in ("unavailable", "connection", "provider", "503")):
        return "provider_down"
    if any(token in text for token in ("bad_request", "validation", "400")):
        return "bad_request"
    return "adapter_error"


def llm_error_retryable(error_code: str) -> bool:
    return llm_error_family(error_code) in {
        "rate_limit",
        "timeout",
        "provider_down",
    } or any(token in error_code.lower() for token in ("retry", "temporarily"))
