"""
Automated unit tests for Aton's Proactive Calendar Monitor & Notification Engine.

Covers all 6 reliability requirements:
1. SQLite persistence across restarts (no duplicate notifications).
2. Separate identification of recurring event occurrences (weekly alerts) and rescheduled events.
3. Tolerant <= 15-minute monitoring window (does not require exact 15:00 clock match).
4. Persistent Do-Not-Disturb (DND) with independent sound and visual notification controls + quiet hours.
5. Hourly limit of 3 alerts with summary grouping so no important appointments are dropped.
6. Fault tolerance against network drops, expired OAuth tokens, and API errors.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from src.core.proactive_calendar import ProactiveCalendarMonitor
from src.integrations.calendar_service import get_user_timezone
from src.tools import ALL_ATON_TOOLS, dispatch_tool


def _make_mock_service_with_items(items):
    mock_service = MagicMock()
    mock_service.events.return_value.list.return_value.execute.return_value = {"items": items}
    return mock_service


def test_1_sqlite_persistence_prevents_duplicate_alerts_across_restarts(tmp_path):
    """Verify notified occurrences are stored in SQLite so restarting Aton never duplicates alerts."""
    db_file = tmp_path / "proactive_test.sqlite3"
    tz = get_user_timezone("America/Fortaleza")
    now_dt = datetime(2026, 11, 4, 13, 48, 0, tzinfo=tz)  # 12 minutes before 14:00

    event = {
        "id": "evt_persist_1",
        "summary": "Reunião com Cliente",
        "start": {"dateTime": "2026-11-04T14:00:00-03:00"},
        "end": {"dateTime": "2026-11-04T15:00:00-03:00"},
    }
    mock_svc = _make_mock_service_with_items([event])

    delivered_payloads = []
    monitor_1 = ProactiveCalendarMonitor(
        db_path=db_file,
        service_provider=lambda: (mock_svc, "servpb@gmail.com", None),
    )
    res_1 = monitor_1.check_and_deliver(
        notify_callback=delivered_payloads.append,
        now_dt=now_dt,
        now_epoch=1000.0,
    )
    assert res_1["status"] == "delivered"
    assert res_1["delivered"] == 1
    assert len(delivered_payloads) == 1
    assert "Reunião com Cliente" in delivered_payloads[0]["body"]

    # Simulate Aton restart by creating a brand-new ProactiveCalendarMonitor instance on the same SQLite DB
    monitor_after_restart = ProactiveCalendarMonitor(
        db_path=db_file,
        service_provider=lambda: (mock_svc, "servpb@gmail.com", None),
    )
    res_2 = monitor_after_restart.check_and_deliver(
        notify_callback=delivered_payloads.append,
        now_dt=now_dt + timedelta(minutes=1),
        now_epoch=1060.0,
    )
    assert res_2["status"] == "ok"
    assert res_2["delivered"] == 0
    assert len(delivered_payloads) == 1  # No duplicate alert


def test_2_recurring_occurrences_and_rescheduled_events_alert_independently(tmp_path):
    """
    Verify:
    - Each weekly occurrence of a recurring event alerts in its respective week.
    - If an event is rescheduled to a new start time, it alerts again for the new time.
    """
    db_file = tmp_path / "recurring_test.sqlite3"
    tz = get_user_timezone("America/Fortaleza")

    # Week 1 occurrence
    week1_now = datetime(2026, 11, 4, 9, 46, 0, tzinfo=tz)
    ev_week1 = {
        "id": "master_weekly_20261104T130000Z",
        "recurringEventId": "master_weekly",
        "summary": "Alinhamento Semanal",
        "start": {"dateTime": "2026-11-04T10:00:00-03:00"},
        "end": {"dateTime": "2026-11-04T11:00:00-03:00"},
    }
    # Week 2 occurrence (7 days later)
    week2_now = datetime(2026, 11, 11, 9, 47, 0, tzinfo=tz)
    ev_week2 = {
        "id": "master_weekly_20261111T130000Z",
        "recurringEventId": "master_weekly",
        "summary": "Alinhamento Semanal",
        "start": {"dateTime": "2026-11-11T10:00:00-03:00"},
        "end": {"dateTime": "2026-11-11T11:00:00-03:00"},
    }

    current_items = [ev_week1]
    monitor = ProactiveCalendarMonitor(
        db_path=db_file,
        service_provider=lambda: (_make_mock_service_with_items(current_items), "servpb@gmail.com", None),
    )

    r1 = monitor.check_and_deliver(now_dt=week1_now, now_epoch=2000.0)
    assert r1["delivered"] == 1

    # Next week's occurrence must alert normally
    current_items = [ev_week2]
    r2 = monitor.check_and_deliver(now_dt=week2_now, now_epoch=600000.0)
    assert r2["delivered"] == 1

    # If Week 2 event is rescheduled from 10:00 to 16:00, it must alert at 15:46
    ev_week2_moved = dict(ev_week2)
    ev_week2_moved["start"] = {"dateTime": "2026-11-11T16:00:00-03:00"}
    ev_week2_moved["end"] = {"dateTime": "2026-11-11T17:00:00-03:00"}
    current_items = [ev_week2_moved]
    r3 = monitor.check_and_deliver(
        now_dt=datetime(2026, 11, 11, 15, 46, 0, tzinfo=tz),
        now_epoch=620000.0,
    )
    assert r3["delivered"] == 1


def test_3_tolerant_window_triggers_anytime_within_15_minutes(tmp_path):
    """Verify alert triggers when <= 15 minutes remain without needing exact 15:00 match."""
    db_file = tmp_path / "window_test.sqlite3"
    tz = get_user_timezone("America/Fortaleza")

    ev = {
        "id": "evt_tol_1",
        "summary": "Dentista",
        "start": {"dateTime": "2026-11-04T15:00:00-03:00"},
        "end": {"dateTime": "2026-11-04T16:00:00-03:00"},
    }
    monitor = ProactiveCalendarMonitor(
        db_path=db_file,
        service_provider=lambda: (_make_mock_service_with_items([ev]), "servpb@gmail.com", None),
    )

    # 20 minutes before (14:40) -> outside 15-min window, does NOT trigger yet
    res_early = monitor.check_and_deliver(
        now_dt=datetime(2026, 11, 4, 14, 40, 0, tzinfo=tz),
        now_epoch=3000.0,
    )
    assert res_early["delivered"] == 0

    # 11 minutes and 23 seconds before (14:48:37) -> inside <= 15-min window, triggers!
    res_within = monitor.check_and_deliver(
        now_dt=datetime(2026, 11, 4, 14, 48, 37, tzinfo=tz),
        now_epoch=3517.0,
    )
    assert res_within["delivered"] == 1


def test_4_persistent_dnd_separate_sound_and_visual_controls(tmp_path):
    """Verify DND settings persist in SQLite and independently control sound vs. visual notifications."""
    db_file = tmp_path / "dnd_test.sqlite3"
    tz = get_user_timezone("America/Fortaleza")

    ev1 = {
        "id": "evt_dnd_1",
        "summary": "Call Financeiro",
        "start": {"dateTime": "2026-11-04T11:00:00-03:00"},
        "end": {"dateTime": "2026-11-04T12:00:00-03:00"},
    }
    monitor = ProactiveCalendarMonitor(
        db_path=db_file,
        service_provider=lambda: (_make_mock_service_with_items([ev1]), "servpb@gmail.com", None),
    )
    # Mute sound only, keep visual notifications enabled
    monitor.update_settings(dnd_mute_sound=True, dnd_block_visual=False)

    # Recreate monitor to verify persistence across restarts
    monitor_restarted = ProactiveCalendarMonitor(
        db_path=db_file,
        service_provider=lambda: (_make_mock_service_with_items([ev1]), "servpb@gmail.com", None),
    )
    cfg = monitor_restarted.get_settings()
    assert cfg.dnd_mute_sound is True
    assert cfg.dnd_block_visual is False

    payloads = []
    res = monitor_restarted.check_and_deliver(
        notify_callback=payloads.append,
        now_dt=datetime(2026, 11, 4, 10, 50, 0, tzinfo=tz),
        now_epoch=4000.0,
    )
    assert res["delivered"] == 1
    assert res["sound_played"] is False
    assert res["visual_shown"] is True
    assert payloads[0]["allow_sound"] is False
    assert payloads[0]["allow_visual"] is True


def test_5_hourly_budget_groups_multiple_or_excess_events_into_summary(tmp_path):
    """Verify multiple upcoming events are grouped into a single summary notification so none are lost."""
    db_file = tmp_path / "budget_test.sqlite3"
    tz = get_user_timezone("America/Fortaleza")

    events = [
        {
            "id": f"evt_b_{i}",
            "summary": f"Compromisso Importante {i}",
            "start": {"dateTime": f"2026-11-04T16:0{i}:00-03:00"},
            "end": {"dateTime": f"2026-11-04T16:3{i}:00-03:00"},
        }
        for i in range(1, 5)
    ]
    monitor = ProactiveCalendarMonitor(
        db_path=db_file,
        service_provider=lambda: (_make_mock_service_with_items(events), "servpb@gmail.com", None),
    )
    payloads = []
    res = monitor.check_and_deliver(
        notify_callback=payloads.append,
        now_dt=datetime(2026, 11, 4, 15, 50, 0, tzinfo=tz),
        now_epoch=5000.0,
    )
    assert res["status"] == "delivered"
    assert res["delivered"] == 1  # Grouped into 1 consolidated notification
    assert res["events_notified"] == 4  # All 4 events accounted for and persisted
    assert "4 compromissos" in payloads[0]["title"]

    explanation = monitor.get_last_alert_explanation()
    assert explanation["status"] == "success"
    assert explanation["grouped_count"] == 4


def test_6_fault_tolerance_handles_network_and_auth_errors_cleanly(tmp_path):
    """Verify network drops, expired OAuth, or API exceptions never raise or break the loop."""
    db_file = tmp_path / "fault_test.sqlite3"

    def broken_provider():
        svc = MagicMock()
        svc.events.return_value.list.return_value.execute.side_effect = RuntimeError("Network unreachable")
        return svc, "servpb@gmail.com", None

    monitor = ProactiveCalendarMonitor(db_path=db_file, service_provider=broken_provider)
    res = monitor.check_and_deliver()
    assert res["status"] == "error_handled"
    assert res["delivered"] == 0
    assert "Network unreachable" in res["error"]

    # Also verify tools are registered in ALL_ATON_TOOLS
    tool_names = {d["name"] for d in ALL_ATON_TOOLS}
    assert "explicar_ultimo_aviso" in tool_names
    assert "configurar_avisos_proativos" in tool_names

