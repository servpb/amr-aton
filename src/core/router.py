"""Offline routing policy. No network calls, payloads, or tool execution."""
from dataclasses import dataclass
from enum import Enum


class DataClass(str, Enum):
    PUBLIC = "public"
    SYNTHETIC = "synthetic"
    PERSONAL = "personal"
    CONFIDENTIAL = "confidential"
    UNKNOWN = "unknown"


class TaskKind(str, Enum):
    COMMAND = "command"
    PLANNING = "planning"
    VOICE = "voice"


@dataclass(frozen=True)
class RouteRequest:
    kind: TaskKind
    data_class: DataClass = DataClass.UNKNOWN
    cancelled: bool = False
    action_already_sent: bool = False


@dataclass(frozen=True)
class RouteDecision:
    allowed: bool
    provider: str | None
    model: str | None
    reason: str


@dataclass(frozen=True)
class FreeEndpoint:
    provider: str
    model: str
    free_tier_verified: bool = False


class ModelRouter:
    """Deny by default; future connectors must enforce this decision again.

    Metadata must come from trusted local policy, never a model/user claim.
    Free-tier verification is an operator attestation, not billing detection.
    """

    def __init__(self, *, enabled: bool = False,
                 endpoints: tuple[FreeEndpoint, ...] = ()):
        self.enabled = enabled
        self.endpoints = tuple(endpoints)

    def route(self, request: RouteRequest, *,
              unavailable: frozenset[str] = frozenset()) -> RouteDecision:
        def deny(reason: str) -> RouteDecision:
            return RouteDecision(False, None, None, reason)

        if request.cancelled:
            return deny("cancelled")
        if request.action_already_sent:
            return deny("action_requires_reconciliation")
        if not isinstance(request.kind, TaskKind):
            return deny("unsupported_task")
        if not isinstance(request.data_class, DataClass) or request.data_class not in (
                DataClass.PUBLIC, DataClass.SYNTHETIC):
            return deny("data_policy_blocked")
        if request.kind == TaskKind.VOICE:
            return deny("existing_voice_path_only")
        if not self.enabled:
            return deny("gateway_disabled")
        # No cross-role fallback until capabilities are evaluated.
        provider = "groq" if request.kind == TaskKind.COMMAND else "openrouter"
        candidates = [e for e in self.endpoints if e.provider == provider]
        for endpoint in candidates:
            if provider in unavailable:
                continue
            if not endpoint.free_tier_verified or not endpoint.model.strip():
                continue
            if provider == "openrouter" and not endpoint.model.endswith(":free"):
                continue
            return RouteDecision(True, provider, endpoint.model, "free_candidate_selected")
        return deny("no_eligible_free_endpoint")
