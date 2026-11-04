"""Routing boundary tests; no credentials, audio, tools, or network."""
import pytest
from src.core.router import (DataClass, FreeEndpoint, ModelRouter, RouteRequest, TaskKind)


def configured():
    return ModelRouter(enabled=True, endpoints=(
        FreeEndpoint("groq", "candidate", True),
        FreeEndpoint("openrouter", "nvidia/candidate:free", True),
        FreeEndpoint("google_paid", "paid", True),
    ))


def test_default_is_disabled():
    assert ModelRouter().route(RouteRequest(TaskKind.COMMAND, DataClass.PUBLIC)).reason == "gateway_disabled"


@pytest.mark.parametrize("data", [DataClass.PERSONAL, DataClass.CONFIDENTIAL, DataClass.UNKNOWN, "public", None])
def test_untrusted_or_private_data_blocked(data):
    assert not configured().route(RouteRequest(TaskKind.COMMAND, data)).allowed


@pytest.mark.parametrize("kind,provider", [(TaskKind.COMMAND,"groq"), (TaskKind.PLANNING,"openrouter")])
def test_role_selection(kind, provider):
    assert configured().route(RouteRequest(kind, DataClass.SYNTHETIC)).provider == provider


def test_voice_remains_separate():
    assert configured().route(RouteRequest(TaskKind.VOICE, DataClass.PUBLIC)).reason == "existing_voice_path_only"


@pytest.mark.parametrize("flag,reason", [("cancelled","cancelled"), ("action_already_sent","action_requires_reconciliation")])
def test_no_cancelled_or_uncertain_action_replay(flag, reason):
    request = RouteRequest(TaskKind.COMMAND, DataClass.PUBLIC, **{flag: True})
    assert configured().route(request).reason == reason


def test_unavailable_does_not_fall_back_to_paid_or_other_role():
    result = configured().route(RouteRequest(TaskKind.COMMAND, DataClass.PUBLIC), unavailable=frozenset({"groq"}))
    assert not result.allowed and result.provider is None


@pytest.mark.parametrize("endpoint", [FreeEndpoint("openrouter","paid",True), FreeEndpoint("openrouter","x:free",False)])
def test_suffix_and_verification_required(endpoint):
    router = ModelRouter(enabled=True,endpoints=(endpoint,))
    assert not router.route(RouteRequest(TaskKind.PLANNING,DataClass.PUBLIC)).allowed


def test_unknown_task_blocked():
    assert not configured().route(RouteRequest("other",DataClass.PUBLIC)).allowed


def test_settings_gateway_default_off():
    from src.config import Settings
    assert Settings(_env_file=None).multi_llm_enabled is False
