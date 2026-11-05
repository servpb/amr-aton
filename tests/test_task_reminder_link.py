import io
import json
from datetime import datetime,timedelta,timezone
from unittest.mock import Mock
from src.tools import google_tasks as tasks
from src.core import reminders


def setup(monkeypatch):
    monkeypatch.setattr(tasks,'_get_credentials',lambda:Mock(valid=True,token='test'))
    send=Mock(return_value=io.BytesIO(json.dumps({'id':'task1'}).encode()))
    monkeypatch.setattr(tasks.urllib.request,'urlopen',send)
    return send


def future():return (datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()


def test_task_and_alarm_created(monkeypatch,tmp_path):
    setup(monkeypatch)
    store=reminders.ReminderStore(tmp_path/'r.db')
    monkeypatch.setattr(reminders,'get_reminder_store',lambda:store)
    result=tasks.create_task('Pagar conta',reminder_at=future())
    assert result['reminder_scheduled'] is True
    assert store.get(result['reminder_id'])['title']=='Pagar conta'


def test_title_time_requires_clarification_before_write(monkeypatch):
    send=setup(monkeypatch)
    assert tasks.create_task('Agua as 19:30')['status']=='needs_clarification'
    send.assert_not_called()


def test_bad_reminder_never_creates_google_task(monkeypatch):
    send=setup(monkeypatch)
    assert tasks.create_task('Agua',reminder_at='2026-11-06T15:00:00')['task_created'] is False
    send.assert_not_called()


def test_date_only_never_claims_alarm(monkeypatch):
    setup(monkeypatch)
    result=tasks.create_task('Agua')
    assert result['reminder_scheduled'] is False


def test_partial_failure_never_claims_alarm(monkeypatch):
    setup(monkeypatch)
    store=Mock();store.create.side_effect=RuntimeError()
    monkeypatch.setattr(reminders,'get_reminder_store',lambda:store)
    result=tasks.create_task('Agua',reminder_at=future())
    assert result['status']=='partial_success'
    assert result['task_created'] and not result['reminder_scheduled']
