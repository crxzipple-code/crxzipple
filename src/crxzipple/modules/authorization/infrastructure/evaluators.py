from __future__ import annotations

from fnmatch import fnmatch
from typing import Any

from crxzipple.modules.authorization.application import AuthorizationEvaluator
from crxzipple.modules.authorization.domain import (
    AuthorizationDecision,
    AuthorizationDecisionCode,
    AuthorizationEffect,
    AuthorizationObligation,
    AuthorizationPolicy,
    AuthorizationRequest,
)


class AbacAuthorizationEvaluator(AuthorizationEvaluator):
    def evaluate(
        self,
        request: AuthorizationRequest,
        policies: list[AuthorizationPolicy],
    ) -> AuthorizationDecision:
        matched = [
            policy
            for policy in sorted(policies, key=lambda item: (-item.priority, item.id))
            if policy.enabled and self._matches_policy(policy, request)
        ]

        deny_matches = [policy for policy in matched if policy.effect is AuthorizationEffect.DENY]
        if deny_matches:
            return AuthorizationDecision(
                allowed=False,
                reason=f"Authorization denied by policy '{deny_matches[0].id}'.",
                code=AuthorizationDecisionCode.POLICY_DENIED,
                matched_policy_ids=tuple(policy.id for policy in matched),
            )

        allow_matches = [policy for policy in matched if policy.effect is AuthorizationEffect.ALLOW]
        if allow_matches:
            obligations: list[AuthorizationObligation] = []
            for policy in allow_matches:
                obligations.extend(policy.obligations)
            return AuthorizationDecision(
                allowed=True,
                reason=f"Authorization allowed by policy '{allow_matches[0].id}'.",
                code=AuthorizationDecisionCode.ALLOW,
                matched_policy_ids=tuple(policy.id for policy in matched),
                obligations=tuple(obligations),
            )

        return AuthorizationDecision(
            allowed=False,
            reason="Authorization denied because no matching allow policy was found.",
            code=AuthorizationDecisionCode.NO_MATCH,
        )

    def _matches_policy(
        self,
        policy: AuthorizationPolicy,
        request: AuthorizationRequest,
    ) -> bool:
        if not any(fnmatch(request.action, pattern) for pattern in policy.actions):
            return False

        if policy.subject_type is not None and not self._matches_scalar(
            request.subject.type,
            policy.subject_type,
        ):
            return False
        if policy.subject_id is not None and not self._matches_scalar(
            request.subject.id,
            policy.subject_id,
        ):
            return False
        if policy.resource_kind is not None and not self._matches_scalar(
            request.resource.kind,
            policy.resource_kind,
        ):
            return False
        if policy.resource_id is not None and not self._matches_scalar(
            request.resource.id,
            policy.resource_id,
        ):
            return False

        if not self._matches_map(request.subject.attrs, policy.subject_match):
            return False
        if not self._matches_map(request.resource.attrs, policy.resource_match):
            return False
        if not self._matches_map(request.context.attrs, policy.context_match):
            return False
        if policy.condition is not None and not self._evaluate_condition(
            policy.condition,
            request,
        ):
            return False
        return True

    def _matches_map(self, actual: dict[str, Any], expected: dict[str, Any]) -> bool:
        for key, value in expected.items():
            actual_value = self._lookup_path(actual, key)
            if not self._matches_value(actual_value, value):
                return False
        return True

    def _matches_scalar(self, actual: Any, expected: Any) -> bool:
        if actual is None:
            return expected is None
        if isinstance(actual, str) and isinstance(expected, str):
            if "*" in expected or "?" in expected:
                return fnmatch(actual, expected)
        return actual == expected

    def _matches_value(self, actual: Any, expected: Any) -> bool:
        if isinstance(expected, (list, tuple, set)):
            if isinstance(actual, (list, tuple, set)):
                return all(item in actual for item in expected)
            return actual in expected
        if isinstance(actual, (list, tuple, set)):
            return expected in actual
        return self._matches_scalar(actual, expected)

    def _lookup_path(self, payload: dict[str, Any], path: str) -> Any:
        current: Any = payload
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                return None
            current = current[part]
        return current

    def _evaluate_condition(
        self,
        expression: Any,
        request: AuthorizationRequest,
    ) -> bool:
        if not isinstance(expression, dict):
            return bool(expression)

        if "all" in expression:
            conditions = expression["all"]
            return isinstance(conditions, list) and all(
                self._evaluate_condition(item, request) for item in conditions
            )
        if "any" in expression:
            conditions = expression["any"]
            return isinstance(conditions, list) and any(
                self._evaluate_condition(item, request) for item in conditions
            )
        if "not" in expression:
            return not self._evaluate_condition(expression["not"], request)
        if "eq" in expression:
            left, right = self._resolve_pair(expression["eq"], request)
            return left == right
        if "ne" in expression:
            left, right = self._resolve_pair(expression["ne"], request)
            return left != right
        if "in" in expression:
            needle, haystack = self._resolve_pair(expression["in"], request)
            if isinstance(haystack, (list, tuple, set, str)):
                return needle in haystack
            return False
        if "contains" in expression:
            haystack, needle = self._resolve_pair(expression["contains"], request)
            if isinstance(haystack, (list, tuple, set, str)):
                return needle in haystack
            return False
        if "truthy" in expression:
            return bool(self._resolve_operand(expression["truthy"], request))
        if "exists" in expression:
            return self._resolve_operand(expression["exists"], request) is not None
        return False

    def _resolve_pair(
        self,
        raw: Any,
        request: AuthorizationRequest,
    ) -> tuple[Any, Any]:
        if not isinstance(raw, list) or len(raw) != 2:
            raise ValueError("ABAC condition operands must be a two-item list.")
        return (
            self._resolve_operand(raw[0], request),
            self._resolve_operand(raw[1], request),
        )

    def _resolve_operand(self, raw: Any, request: AuthorizationRequest) -> Any:
        if not isinstance(raw, str):
            return raw
        if raw.startswith("subject."):
            path = raw.removeprefix("subject.")
            if path == "type":
                return request.subject.type
            if path == "id":
                return request.subject.id
            return self._lookup_path(request.subject.attrs, path)
        if raw.startswith("resource."):
            path = raw.removeprefix("resource.")
            if path == "kind":
                return request.resource.kind
            if path == "id":
                return request.resource.id
            return self._lookup_path(request.resource.attrs, path)
        if raw.startswith("context."):
            path = raw.removeprefix("context.")
            return self._lookup_path(request.context.attrs, path)
        return raw
