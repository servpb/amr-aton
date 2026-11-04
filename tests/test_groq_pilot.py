import json
from urllib.error import HTTPError, URLError
import pytest
from src.integrations import groq_client as module


def client(**kw):
    return module.GroqPilotClient("test-secret", enabled=True, free_plan_verified=True, **kw)


def reply(content, **extra):
    return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(content), **extra}}]}


@pytest.mark.parametrize("enabled,verified,key,status", [
    (False,True,"key","disabled"),(True,False,"key","free_plan_not_verified"),
    (True,True,"","missing_key")])
def test_guards_never_send(monkeypatch, enabled, verified, key, status):
    monkeypatch.setattr(module,"_post",lambda *a: pytest.fail("network called"))
    c=module.GroqPilotClient(key,enabled=enabled,free_plan_verified=verified)
    assert c.run_case("volume")["status"] == status


def test_unknown_case_never_sends(monkeypatch):
    monkeypatch.setattr(module,"_post",lambda *a: pytest.fail("network called"))
    assert client().run_case("private email")["status"] == "unknown_synthetic_case"


def test_payload_and_success(monkeypatch):
    calls=[]
    def send(key,payload,timeout):
        calls.append(payload)
        return reply({"action":"set_volume","level":30})
    monkeypatch.setattr(module,"_post",send)
    c=client()
    assert c.run_case("volume")["matches_expected"] is True
    assert calls[0]["model"] == module.MODEL
    assert "tools" not in calls[0]
    assert c.run_case("volume")["status"] == "cooldown"
    assert len(calls)==1


@pytest.mark.parametrize("proposal", [{"action":"delete"},{"action":"set_volume","level":True},
    {"action":"set_volume","level":101},{"action":"clarify","extra":"value"},[]])
def test_invalid_proposals(monkeypatch,proposal):
    monkeypatch.setattr(module,"_post",lambda *a: reply(proposal))
    assert client().run_case("volume")["status"] == "invalid_proposal"


def test_no_tool_execution(monkeypatch):
    monkeypatch.setattr(module,"_post",lambda *a: reply({},tool_calls=[{"name":"delete"}]))
    assert client().run_case("volume")["status"] == "unexpected_tool_call"


@pytest.mark.parametrize("error,status", [(TimeoutError("secret"),"timeout"),
    (URLError("secret"),"network_error"),(HTTPError("url",401,"secret",{},None),"authentication_failed"),
    (ValueError("secret"),"invalid_response")])
def test_errors_sanitized(monkeypatch,error,status):
    def send(*a): raise error
    monkeypatch.setattr(module,"_post",send)
    result=client().run_case("volume")
    assert result == {"status":status}


def test_rate_limit_no_retry(monkeypatch):
    calls=[]
    def send(*a):
        calls.append(1)
        raise HTTPError("url",429,"secret",{"Retry-After":"120"},None)
    monkeypatch.setattr(module,"_post",send)
    c=client()
    assert c.run_case("volume")["retry_after_seconds"] == 120
    assert c.run_case("volume")["status"] == "cooldown"
    assert len(calls)==1


def test_settings_no_key_repr():
    from src.config import Settings
    s=Settings(_env_file=None,GROQ_API_KEY="test-secret")
    assert "test-secret" not in repr(s)
    assert s.groq_free_plan_verified is False
