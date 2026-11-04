"""Persistence, recovery, cancellation and concurrent-claim regression tests."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import pytest
from src.core.reminders import ReminderStore

@pytest.fixture
def setup_store(tmp_path):
    clock = [1700000000.0]
    store = ReminderStore(tmp_path / "reminders.db", clock=lambda: clock[0])
    return store, clock

def test_survives_restart_and_delivers_overdue_once(setup_store):
    store, clock = setup_store
    item = store.create("Pausa", seconds=60)
    clock[0] += 120
    restored = ReminderStore(store.path, clock=lambda: clock[0])
    delivered = []
    assert restored.deliver_one(lambda row: delivered.append(row['id']))
    assert not restored.deliver_one(lambda row: delivered.append(row['id']))
    assert delivered == [item['id']]
    assert restored.get(item['id'])['state'] == 'notified'

def test_cancel_prevents_delivery(setup_store):
    store, clock = setup_store
    item = store.create("Cancelar", seconds=1)
    assert store.cancel(item['id'])
    assert not store.cancel(item['id'])
    clock[0] += 10
    assert not store.deliver_one(lambda row: pytest.fail("Cancelled reminder delivered"))

def test_failed_notification_is_retried_after_backoff(setup_store):
    store, clock = setup_store
    item = store.create("Aviso", seconds=1)
    clock[0] += 2
    def broken(row):
        raise RuntimeError("Notification unavailable")
    assert store.deliver_one(broken)
    assert store.get(item['id'])['state'] == 'pending'
    assert not store.deliver_one(broken)
    clock[0] += 31
    delivered = []
    assert store.deliver_one(delivered.append)
    assert delivered[0]['id'] == item['id']

def test_concurrent_workers_cannot_claim_same_reminder(setup_store):
    store, clock = setup_store
    item = store.create("Único", seconds=1)
    clock[0] += 2
    stores = [ReminderStore(store.path, clock=lambda: clock[0]) for _ in range(2)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(lambda s: s.claim_due(), stores))
    assert sum(row is not None for row in rows) == 1
    assert not store.cancel(item['id'])  # Delivery in progress cannot be cancelled falsely.

def test_crashed_delivery_lease_is_recovered(setup_store):
    store, clock = setup_store
    item = store.create("Recuperar", seconds=1)
    clock[0] += 2
    assert store.claim_due()['id'] == item['id']
    assert store.claim_due() is None
    clock[0] += 61
    assert store.claim_due()['id'] == item['id']

@pytest.mark.parametrize('seconds', [0, -1, True, float('nan'), float('inf'), '60'])
def test_rejects_invalid_duration(setup_store, seconds):
    store, _ = setup_store
    with pytest.raises(ValueError):
        store.create('Aviso', seconds=seconds)

def test_absolute_time_requires_timezone_and_preserves_instant(setup_store):
    store, _ = setup_store
    with pytest.raises(ValueError):
        store.create('Aviso', at='1970-01-01T04:00:00')
    item = store.create('Aviso', at='2024-01-01T01:00:00-03:00')
    assert item['due_at'] == datetime(2024, 1, 1, 4, tzinfo=timezone.utc).timestamp()
    assert not store.list(include_history=False)[0]['notified_at']

def test_tool_does_not_confirm_failed_save_and_uses_real_ids(setup_store, monkeypatch):
    from src.tools import reminders as tools
    store, _ = setup_store
    monkeypatch.setattr(tools, 'get_reminder_store', lambda: store)
    assert tools.dispatch_reminder_tool('create_timer', {'seconds': -1, 'title': 'X'})['status'] == 'error'
    created = tools.dispatch_reminder_tool('create_timer', {'seconds': 60, 'title': 'X'})
    assert created['status'] == 'success'
    listing = tools.dispatch_reminder_tool('list_reminders', {})
    assert listing['reminders'][0]['id'] == created['reminder']['id']
    assert 'current_local_time' in listing
    assert tools.dispatch_reminder_tool('cancel_reminder', {'reminder_id': 'invented'})['status'] == 'not_cancelled'

def test_notification_submits_to_tray_without_gemini():
    from types import SimpleNamespace
    from unittest.mock import Mock
    from src.core.assistant import AMRAssistant, AssistantState
    assistant = AMRAssistant.__new__(AMRAssistant)
    assistant.tray = SimpleNamespace(notify_reminder=Mock())
    assistant.player = SimpleNamespace(play_wake_chime=Mock())
    assistant.state = AssistantState.SLEEPING
    assistant._notify_reminder({'title': 'Pausa', 'due_at': 1700000000})
    assistant.tray.notify_reminder.assert_called_once()
    assistant.player.play_wake_chime.assert_called_once()
    assert assistant._reminder_audio_until > 0

def test_tools_are_in_live_registry():
    from src.tools import ALL_ATON_TOOLS
    names = [item['name'] for item in ALL_ATON_TOOLS]
    for name in ['create_timer', 'create_reminder', 'list_reminders', 'cancel_reminder']:
        assert names.count(name) == 1


@pytest.mark.asyncio
async def test_worker_runs_while_sleeping_and_stops(monkeypatch):
    import asyncio
    from unittest.mock import Mock
    from src.core import reminders
    from src.core.assistant import AMRAssistant, AssistantState
    assistant = AMRAssistant.__new__(AMRAssistant)
    assistant._running = True
    assistant.state = AssistantState.SLEEPING
    delivered = []
    assistant._notify_reminder = delivered.append
    def deliver(notify):
        notify({'title': 'Pausa', 'due_at': 1700000000})
        assistant._running = False
        return True
    fake = Mock()
    fake.deliver_one.side_effect = deliver
    monkeypatch.setattr(reminders, 'get_reminder_store', lambda: fake)
    await asyncio.wait_for(assistant._run_reminders(), timeout=3)
    assert len(delivered) == 1
    assert assistant.state == AssistantState.SLEEPING


def test_no_tray_retains_pending_reminder(setup_store):
    from src.core.assistant import AMRAssistant, AssistantState
    store, clock = setup_store
    assistant = AMRAssistant.__new__(AMRAssistant)
    assistant.tray = None
    assistant.state = AssistantState.SLEEPING
    item = store.create('Pausa', seconds=1)
    clock[0] += 2
    store.deliver_one(assistant._notify_reminder)
    assert store.get(item['id'])['state'] == 'pending'
