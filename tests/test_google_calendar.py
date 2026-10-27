"""Unit tests for Google Calendar tools and OAuth2 integration (Phase 4)."""

from datetime import datetime, timedelta
import io
import json
from unittest.mock import MagicMock, patch
import urllib.error

import pytest

from src.tools import ALL_ATON_TOOLS, dispatch_tool
from src.tools.google_calendar import (
    GOOGLE_CALENDAR_FUNCTION_DECLARATIONS,
    create_calendar_event,
    dispatch_calendar_tool,
    get_calendar_events,
    parse_datetime_flexible,
)


def test_parse_datetime_flexible():
    """Test flexible parsing of natural and ISO dates."""
    now = datetime.now().astimezone()

    # 1. Fallback / None
    dt_none = parse_datetime_flexible(None)
    assert dt_none.date() == now.date()

    # 2. ISO format
    iso_str = "2026-11-15T14:30:00"
    dt_iso = parse_datetime_flexible(iso_str)
    assert dt_iso.year == 2026
    assert dt_iso.month == 11
    assert dt_iso.day == 15
    assert dt_iso.hour == 14
    assert dt_iso.minute == 30

    # 3. Natural 'hoje às 15:00'
    dt_hoje = parse_datetime_flexible("hoje às 15:00")
    assert dt_hoje.date() == now.date()
    assert dt_hoje.hour == 15
    assert dt_hoje.minute == 0

    # 4. Natural 'amanhã às 10h'
    dt_amanha = parse_datetime_flexible("amanhã às 10h")
    assert dt_amanha.date() == (now.date() + timedelta(days=1))
    assert dt_amanha.hour == 10
    assert dt_amanha.minute == 0

    # 5. Relative end time fallback (base_start + 1h)
    base = datetime(2026, 10, 28, 14, 0)
    end_dt = parse_datetime_flexible(None, is_end_time=True, base_start=base)
    assert end_dt == datetime(2026, 10, 28, 15, 0)


def test_get_calendar_events_unauthenticated():
    """Verify behavior when no Google OAuth credentials are present."""
    with patch("src.tools.google_calendar._get_credentials", return_value=None):
        res = get_calendar_events()
        assert res["status"] == "not_authenticated"
        assert "Google Agenda ainda não está autenticado" in res["message"]
        assert res["events"] == []


def test_get_calendar_events_success():
    """Verify listing upcoming events from Google Calendar API."""
    mock_creds = MagicMock()
    mock_creds.valid = True
    mock_creds.token = "mock_valid_token"

    sample_api_response = {
        "items": [
            {
                "id": "evt_123",
                "summary": "Reunião de Planejamento",
                "start": {"dateTime": "2026-10-28T14:00:00Z"},
                "end": {"dateTime": "2026-10-28T15:00:00Z"},
                "location": "Google Meet",
            },
            {
                "id": "evt_456",
                "summary": "Consulta Médica",
                "start": {"dateTime": "2026-10-28T16:30:00Z"},
                "end": {"dateTime": "2026-10-28T17:30:00Z"},
                "location": "Consultório",
            },
        ]
    }

    mock_resp = io.BytesIO(json.dumps(sample_api_response).encode("utf-8"))

    with patch("src.tools.google_calendar._get_credentials", return_value=mock_creds), \
         patch("urllib.request.urlopen", return_value=mock_resp):
        res = get_calendar_events(time_min="hoje", max_results=5)
        assert res["status"] == "success"
        assert res["count"] == 2
        assert len(res["events"]) == 2
        assert res["events"][0]["summary"] == "Reunião de Planejamento"
        assert "Você tem 2 compromissos" in res["message"]


def test_get_calendar_events_empty():
    """Verify response when calendar has no upcoming events."""
    mock_creds = MagicMock()
    mock_creds.valid = True
    mock_creds.token = "mock_valid_token"

    sample_api_response = {"items": []}
    mock_resp = io.BytesIO(json.dumps(sample_api_response).encode("utf-8"))

    with patch("src.tools.google_calendar._get_credentials", return_value=mock_creds), \
         patch("urllib.request.urlopen", return_value=mock_resp):
        res = get_calendar_events()
        assert res["status"] == "success"
        assert res["count"] == 0
        assert "não tem nenhum compromisso" in res["message"]


def test_create_calendar_event_unauthenticated():
    """Verify create_calendar_event when unauthenticated."""
    with patch("src.tools.google_calendar._get_credentials", return_value=None):
        res = create_calendar_event("Reunião", "hoje às 14:00")
        assert res["status"] == "not_authenticated"
        assert "Google Agenda ainda não está autenticado" in res["message"]


def test_create_calendar_event_success():
    """Verify successful creation of a new calendar event."""
    mock_creds = MagicMock()
    mock_creds.valid = True
    mock_creds.token = "mock_valid_token"

    sample_response = {
        "id": "new_evt_789",
        "htmlLink": "https://www.google.com/calendar/event?eid=new_evt_789",
        "summary": "Dentista",
    }
    mock_resp = io.BytesIO(json.dumps(sample_response).encode("utf-8"))

    with patch("src.tools.google_calendar._get_credentials", return_value=mock_creds), \
         patch("urllib.request.urlopen", return_value=mock_resp):
        res = create_calendar_event(
            summary="Dentista",
            start_time="amanhã às 15:00",
            location="Clínica Sorriso",
        )
        assert res["status"] == "success"
        assert res["event_id"] == "new_evt_789"
        assert "Compromisso 'Dentista' agendado com sucesso" in res["message"]


def test_dispatch_calendar_tools():
    """Test unified dispatcher for Google Calendar tools."""
    with patch("src.tools.google_calendar.get_calendar_events", return_value={"status": "ok"}) as mock_get:
        res = dispatch_tool("get_calendar_events", {"time_min": "hoje"})
        assert res["status"] == "ok"
        mock_get.assert_called_once()

    with patch("src.tools.google_calendar.create_calendar_event", return_value={"status": "ok"}) as mock_create:
        res = dispatch_tool("create_calendar_event", {"summary": "Almoço", "start_time": "hoje às 12:00"})
        assert res["status"] == "ok"
        mock_create.assert_called_once()

    res_unknown = dispatch_calendar_tool("unknown_calendar_action", {})
    assert res_unknown["status"] == "error"


def test_all_aton_tools_count_with_calendar():
    """Verify ALL_ATON_TOOLS includes at least 19 tools."""
    assert len(ALL_ATON_TOOLS) >= 19
    names = [t["name"] for t in ALL_ATON_TOOLS]
    assert "get_calendar_events" in names
    assert "create_calendar_event" in names
