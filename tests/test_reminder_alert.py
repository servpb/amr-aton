from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from src.core.reminders import ReminderStore


@pytest.mark.parametrize('action,state',[('complete','completed'),('snooze','pending')])
def test_actions_durable_single_use(tmp_path,action,state):
    now=[1000];s=ReminderStore(tmp_path/'r.db',clock=lambda:now[0])
    item=s.create('Lembrete',seconds=1);now[0]+=2;s.claim_due();s.finish(item['id'])
    assert s.respond_to_alert(item['id'],action)
    assert not s.respond_to_alert(item['id'],action)
    assert ReminderStore(s.path,clock=lambda:now[0]).get(item['id'])['state']==state
    if action=='snooze': assert s.get(item['id'])['due_at']==1602


def test_fast_click_before_delivery_finish_is_not_overwritten(tmp_path):
    s=ReminderStore(tmp_path/'r.db',clock=lambda:1000)
    item=s.create('Teste',seconds=1)
    s.clock=lambda:1002;s.claim_due()
    assert s.respond_to_alert(item['id'],'snooze')
    s.finish(item['id'])
    assert s.get(item['id'])['state']=='pending'


@pytest.mark.parametrize('busy,muted,dnd,quiet,visual,expected',[
    (False,False,False,False,False,True),
    (True,False,False,False,False,True),
    (False,True,False,False,False,False),
    (False,False,True,False,False,False),
    (False,False,False,True,False,False),
    (False,False,False,False,True,None)])
def test_audio_and_dnd_policy(monkeypatch,busy,muted,dnd,quiet,visual,expected):
    from src.core import reminders,proactive_calendar
    from src.integrations import reminder_alert
    from src.core.assistant import AMRAssistant,AssistantState
    a=AMRAssistant.__new__(AMRAssistant);a.tray=Mock();a.player=Mock();a._is_muted=muted
    a.state=AssistantState.CONVERSING if busy else AssistantState.SLEEPING
    a._live_client=None
    a.player.is_playing=False
    cfg=SimpleNamespace(dnd_block_visual=visual,dnd_mute_sound=dnd,quiet_start_hour=23,quiet_end_hour=7)
    monitor=SimpleNamespace(get_settings=lambda:cfg,is_in_quiet_hours=lambda *args:quiet)
    monkeypatch.setattr(proactive_calendar,'get_proactive_calendar_monitor',lambda:monitor)
    monkeypatch.setattr(reminders,'get_reminder_store',lambda:SimpleNamespace(path='test.db'))
    popup=Mock();monkeypatch.setattr(reminder_alert,'show_reminder_alert',popup)
    if expected is None:
        with pytest.raises(RuntimeError): a._notify_reminder({'id':'x','title':'Teste'})
        popup.assert_not_called()
    else:
        a._notify_reminder({'id':'x','title':'Teste'})
        assert popup.call_args.kwargs['allow_sound'] is expected
