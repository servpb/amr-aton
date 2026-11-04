"""
Unit tests for Multi-Module Verified Scenes & Custom Voice Routines (`src/tools/scenes.py`).

Validates all 6 reliability and verification requirements (Frente 1) plus all 6
custom routine security, confirmation, and persistence requirements (Etapa 3)
without real hardware:
1. Fault-isolated step execution (a failure in Fire TV or Gmail never aborts other steps).
2. Three-level verification (`confirmed`, `sent_unverified`, `failed`).
3. Security guards: per-step timeout, anti-duplication cooldown, credential sanitization,
   strict action catalog whitelist, and authorized application identifiers.
4. State snapshot & restoration (restores previous volume & DND flags without altering quiet hours).
5. Per-step structured report distinguishing confirmed, sent_unverified, and failed.
6. Proposal-bound two-phase confirmation (60s TTL, single-use, session-bound, superseded proposals),
   sensitive action execution gate (`fechar_app_pc` with unsaved document warning), native scene
   protection, and SQLite persistence + timer recovery across Aton restarts.
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest

from src.core.proactive_calendar import (
    ProactiveCalendarMonitor,
    set_proactive_calendar_monitor,
)
from src.core.reminders import ReminderStore
from src.tools.scenes import (
    SceneConfirmationManager,
    _sanitize_text,
    confirmar_rotina_personalizada,
    executar_cena,
    get_custom_scene_from_db,
    get_saved_scene_snapshot,
    get_scene_confirmation_manager,
    listar_cenas,
    propor_cena_personalizada,
    remover_cena_personalizada,
    reset_scene_guards,
    restaurar_cena,
)


@pytest.fixture(autouse=True)
def isolated_env(tmp_path: Path):
    """Provide an isolated SQLite DB and fresh ProactiveCalendarMonitor per test."""
    reset_scene_guards()
    db_file = tmp_path / "test_scenes.sqlite3"
    monitor = ProactiveCalendarMonitor(db_path=db_file)
    set_proactive_calendar_monitor(monitor)
    yield db_file
    reset_scene_guards()


def test_1_independent_step_execution_fire_tv_failure_does_not_block_scene(isolated_env: Path):
    """
    Requirement 1: When Fire TV fails (offline/error), Modo Cinema still completes
    proactive DND sound muting and Windows volume reduction.
    """
    with (
        patch("src.tools.system_audio.set_system_volume") as mock_vol,
        patch("src.tools.fire_tv.launch_fire_tv_app") as mock_tv,
    ):
        mock_vol.side_effect = [
            {"status": "success", "volume_percent": 65, "is_muted": False, "message": "65%"},
            {"status": "success", "volume_percent": 20, "is_muted": False, "message": "20%"},
        ]
        mock_tv.return_value = {
            "status": "error",
            "confirmed": False,
            "action_sent": False,
            "message": "Fire TV Stick offline na rede local.",
        }

        res = executar_cena("modo_cinema", db_path=isolated_env)

    assert res["status"] == "partial"
    assert res["counts"] == {"total": 3, "confirmed": 2, "sent_unverified": 0, "failed": 1}

    step_map = {s["step_id"]: s for s in res["steps"]}
    assert step_map["proactive_dnd_sound"]["verification_level"] == "confirmed"
    assert step_map["windows_volume_cinema"]["verification_level"] == "confirmed"
    assert step_map["fire_tv_app"]["verification_level"] == "failed"
    assert "Confirmado:" in res["message"]
    assert "Não concluído:" in res["message"]


def test_2_three_level_verification_confirmed_vs_sent_unverified_vs_failed(isolated_env: Path):
    """
    Requirement 2: Distinguish between command sent without foreground confirmation
    (`sent_unverified`) vs. confirmed foreground (`confirmed`) vs. device failure (`failed`).
    """
    with (
        patch("src.tools.system_audio.set_system_volume") as mock_vol,
        patch("src.tools.fire_tv.launch_fire_tv_app") as mock_tv,
    ):
        mock_vol.side_effect = [
            {"status": "success", "volume_percent": 50, "is_muted": False},
            {"status": "success", "volume_percent": 20, "is_muted": False},
        ]
        mock_tv.return_value = {
            "status": "inconclusive",
            "confirmed": False,
            "action_sent": True,
            "foreground_package": "com.amazon.tv.launcher",
            "message": "Comando enviado, mas pacote em primeiro plano não confirmado.",
        }

        res_unverified = executar_cena("modo_cinema", db_path=isolated_env)

    step_tv = {s["step_id"]: s for s in res_unverified["steps"]}["fire_tv_app"]
    assert step_tv["verification_level"] == "sent_unverified"
    assert res_unverified["counts"]["confirmed"] == 2
    assert res_unverified["counts"]["sent_unverified"] == 1
    assert res_unverified["counts"]["failed"] == 0
    assert "Comando enviado sem confirmação final:" in res_unverified["message"]

    reset_scene_guards()
    with (
        patch("src.tools.system_audio.set_system_volume") as mock_vol,
        patch("src.tools.fire_tv.launch_fire_tv_app") as mock_tv,
    ):
        mock_vol.return_value = {"status": "success", "volume_percent": 20, "is_muted": False}
        mock_tv.return_value = {
            "status": "success",
            "confirmed": True,
            "action_sent": True,
            "foreground_package": "com.amazon.firetv.youtube",
            "message": "YouTube confirmado em primeiro plano.",
        }

        res_confirmed = executar_cena("modo_cinema", db_path=isolated_env)

    step_tv_ok = {s["step_id"]: s for s in res_confirmed["steps"]}["fire_tv_app"]
    assert step_tv_ok["verification_level"] == "confirmed"
    assert res_confirmed["status"] == "success"
    assert res_confirmed["counts"] == {"total": 3, "confirmed": 3, "sent_unverified": 0, "failed": 0}


def test_3_security_step_timeout_deduplication_and_log_sanitization(isolated_env: Path):
    """
    Requirement 3:
    - Slow/hung step times out cleanly without blocking remaining steps.
    - Duplicate calls within cooldown are blocked.
    - Credentials/API keys in error messages are redacted.
    """
    def slow_fire_tv(_app_name: str):
        time.sleep(0.4)
        return {"status": "success", "confirmed": True}

    with (
        patch("src.tools.system_audio.set_system_volume") as mock_vol,
        patch("src.tools.fire_tv.launch_fire_tv_app", side_effect=slow_fire_tv),
    ):
        mock_vol.return_value = {"status": "success", "volume_percent": 20, "is_muted": False}
        res = executar_cena(
            "modo_cinema",
            db_path=isolated_env,
            step_timeout_seconds=0.1,
        )

    step_map = {s["step_id"]: s for s in res["steps"]}
    assert step_map["proactive_dnd_sound"]["verification_level"] == "confirmed"
    assert step_map["windows_volume_cinema"]["verification_level"] == "confirmed"
    assert step_map["fire_tv_app"]["verification_level"] == "failed"
    assert "tempo limite excedido" in step_map["fire_tv_app"]["message"]

    dup = executar_cena("modo_cinema", db_path=isolated_env)
    assert dup["status"] == "duplicate_blocked"

    dirty = (
        "Erro HTTP 401 com Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.secret "
        "e chave AIzaSyD-1234567890abcdefghijklmnop e token=meu_segredo_super_longo_123"
    )
    clean = _sanitize_text(dirty)
    assert "eyJhbGci" not in clean
    assert "AIzaSyD" not in clean
    assert "meu_segredo_super_longo_123" not in clean
    assert "[CREDENTIAL_REDACTED]" in clean


def test_4_state_snapshot_and_restore_preserves_previous_volume_and_quiet_hours(isolated_env: Path):
    """
    Requirement 4:
    - Modo Cinema snapshots original volume (72%) and DND (False) without changing
      permanent quiet hours (23:00-07:00).
    - `restaurar_cena` restores volume to 72% and DND sound to False and clears snapshot.
    """
    from src.core.proactive_calendar import get_proactive_calendar_monitor

    monitor = get_proactive_calendar_monitor()
    initial_settings = monitor.get_settings()
    assert initial_settings.dnd_mute_sound is False
    assert initial_settings.quiet_start_hour == 23
    assert initial_settings.quiet_end_hour == 7

    with (
        patch("src.tools.system_audio.set_system_volume") as mock_vol,
        patch("src.tools.fire_tv.launch_fire_tv_app") as mock_tv,
    ):
        mock_vol.side_effect = [
            {"status": "success", "volume_percent": 72, "is_muted": False},
            {"status": "success", "volume_percent": 20, "is_muted": False},
        ]
        mock_tv.return_value = {
            "status": "success",
            "confirmed": True,
            "action_sent": True,
            "foreground_package": "com.amazon.firetv.youtube",
        }

        cinema_res = executar_cena("modo_cinema", db_path=isolated_env)

    assert cinema_res["status"] == "success"
    assert monitor.get_settings().dnd_mute_sound is True
    assert monitor.get_settings().quiet_start_hour == 23
    assert monitor.get_settings().quiet_end_hour == 7

    snap = get_saved_scene_snapshot(db_path=isolated_env)
    assert snap is not None
    assert snap["previous_volume_percent"] == 72
    assert snap["previous_dnd_mute_sound"] is False

    with patch("src.tools.system_audio.set_system_volume") as mock_restore_vol:
        mock_restore_vol.return_value = {
            "status": "success",
            "volume_percent": 72,
            "is_muted": False,
        }
        restore_res = restaurar_cena(db_path=isolated_env)

    assert restore_res["status"] == "success"
    assert restore_res["counts"]["confirmed"] == 2
    assert monitor.get_settings().dnd_mute_sound is False
    assert monitor.get_settings().quiet_start_hour == 23
    assert monitor.get_settings().quiet_end_hour == 7
    assert get_saved_scene_snapshot(db_path=isolated_env) is None


def test_5_structured_per_step_report_in_bom_dia_and_boa_noite(isolated_env: Path):
    """
    Requirement 5: `bom_dia` and `boa_noite` generate complete per-step reports
    even when one external service (e.g. Gmail) fails.
    """
    with (
        patch("src.tools.google_calendar.list_events") as mock_cal,
        patch("src.tools.google_tasks.list_tasks") as mock_tasks,
        patch("src.tools.gmail.list_unread_emails") as mock_gmail,
        patch("src.tools.system_telemetry.get_system_telemetry") as mock_tel,
    ):
        mock_cal.return_value = {
            "status": "success",
            "events": [{"summary": "Reunião de Arquitetura"}],
        }
        mock_tasks.return_value = {
            "status": "success",
            "tasks": [{"title": "Revisar PR das Cenas"}],
        }
        mock_gmail.return_value = {
            "status": "error",
            "message": "Falha temporária de rede ao consultar Gmail.",
        }
        mock_tel.return_value = {
            "status": "success",
            "cpu_percent": 14,
            "ram_percent": 48,
            "battery": {"percent": 92},
        }

        res = executar_cena("bom_dia", db_path=isolated_env)

    assert res["status"] == "partial"
    assert res["counts"] == {"total": 4, "confirmed": 3, "sent_unverified": 0, "failed": 1}
    step_map = {s["step_id"]: s for s in res["steps"]}
    assert step_map["calendar_today"]["verification_level"] == "confirmed"
    assert step_map["tasks_pending"]["verification_level"] == "confirmed"
    assert step_map["gmail_unread"]["verification_level"] == "failed"
    assert step_map["windows_telemetry"]["verification_level"] == "confirmed"


def test_6_modo_foco_and_listar_cenas_without_real_devices(isolated_env: Path):
    """
    Requirement 6: Simulate Modo Foco (DND + Windows media stop + persistent focus timer)
    and `listar_cenas` completely offline.
    """
    with (
        patch("src.tools.system_audio.set_system_volume") as mock_vol,
        patch("src.tools.system_audio.control_system_media") as mock_media,
    ):
        mock_vol.return_value = {"status": "success", "volume_percent": 60, "is_muted": False}
        mock_media.return_value = {"status": "success", "message": "Stop enviado."}

        res = executar_cena("modo_foco", duracao_foco_minutos=30, db_path=isolated_env)

    assert res["counts"] == {"total": 3, "confirmed": 2, "sent_unverified": 1, "failed": 0}
    step_map = {s["step_id"]: s for s in res["steps"]}
    assert step_map["proactive_dnd_sound"]["verification_level"] == "confirmed"
    assert step_map["windows_media_stop"]["verification_level"] == "sent_unverified"
    assert step_map["focus_timer"]["verification_level"] == "confirmed"

    catalog = listar_cenas(db_path=isolated_env)
    assert catalog["status"] == "success"
    assert catalog["has_saved_snapshot"] is True
    assert len(catalog["scenes"]) == 5


def test_7_unified_dispatcher_and_module_registry_integration():
    """Verify all 6 scene tools are registered in ALL_ATON_TOOLS, dispatch_tool, and ModuleRegistry."""
    from src.core.module_registry import get_module_registry
    from src.tools import ALL_ATON_TOOLS, dispatch_tool

    tool_names = {entry["name"] for entry in ALL_ATON_TOOLS}
    for expected_tool in (
        "executar_cena",
        "restaurar_cena",
        "listar_cenas",
        "propor_cena_personalizada",
        "confirmar_rotina_personalizada",
        "remover_cena_personalizada",
    ):
        assert expected_tool in tool_names

    res = dispatch_tool("listar_cenas", {})
    assert res["status"] == "success"

    reg = get_module_registry()
    detail = reg.detail_module("scenes")
    assert detail["status"] == "success"
    assert detail["id"] == "scenes"
    assert len(detail["ferramentas_registradas"]) == 6


# ===========================================================================
# Etapa 3 Tests: Custom Voice Routines, Confirmation Gate, Security & Restart
# ===========================================================================


def test_8_custom_scene_creation_requires_confirmation_and_persists_across_restarts(isolated_env: Path):
    """
    Etapa 3 — Requirements 1, 4, 5:
    - Creating a custom routine returns `confirmation_required` and does NOT save until confirmed.
    - Confirming saves in SQLite inside a transaction.
    - Executing the custom routine saves a state snapshot, modifies volume/DND, and creates a
      persistent timer in SQLite.
    - Simulating an Aton restart (re-opening SQLite via new ReminderStore and querying custom scenes)
      recovers both the custom routine and the active persistent timer.
    - `restaurar_cena` restores the previous volume and DND state without touching permanent quiet hours.
    """
    steps = [
        {"acao": "silenciar_avisos"},
        {"acao": "ajustar_volume_pc", "nivel": 15},
        {"acao": "abrir_app_pc", "aplicativo": "notepad"},
        {"acao": "criar_timer", "minutos": 25, "titulo": "Pomodoro Estudo"},
    ]
    prop_res = propor_cena_personalizada(
        nome_cena="Modo Estudo",
        etapas=steps,
        db_path=isolated_env,
    )
    assert prop_res["status"] == "confirmation_required"
    proposal_id = prop_res["proposal_id"]

    # Must NOT exist in SQLite before confirmation
    assert get_custom_scene_from_db("modo_estudo", db_path=isolated_env) is None

    # Confirm creation
    confirm_res = confirmar_rotina_personalizada(proposal_id, db_path=isolated_env)
    assert confirm_res["status"] == "success"
    assert confirm_res["scene"] == "modo_estudo"

    # Now execute "Modo Estudo"
    with (
        patch("src.tools.system_audio.set_system_volume") as mock_vol,
        patch("src.tools.windows_apps.open_application") as mock_open,
    ):
        mock_vol.side_effect = [
            # Snapshot read (original volume 80%)
            {"status": "success", "volume_percent": 80, "is_muted": False},
            # Target volume 15%
            {"status": "success", "volume_percent": 15, "is_muted": False},
        ]
        mock_open.return_value = {"status": "success", "confirmed": True}

        exec_res = executar_cena("Modo Estudo", db_path=isolated_env)

    assert exec_res["status"] == "success"
    assert exec_res["counts"] == {"total": 4, "confirmed": 4, "sent_unverified": 0, "failed": 0}

    # Simulate Aton restart: instantiate fresh ReminderStore and query custom scenes from disk
    restarted_store = ReminderStore(path=isolated_env)
    active_timers = restarted_store.list(include_history=False)
    assert len(active_timers) == 1
    assert active_timers[0]["title"] == "Pomodoro Estudo"

    recovered_scene = get_custom_scene_from_db("modo_estudo", db_path=isolated_env)
    assert recovered_scene is not None
    assert recovered_scene["title"] == "Modo Estudo"
    assert len(recovered_scene["steps"]) == 4

    # Restore pre-scene state (volume back to 80%, DND sound back to False)
    with patch("src.tools.system_audio.set_system_volume") as mock_restore_vol:
        mock_restore_vol.return_value = {"status": "success", "volume_percent": 80, "is_muted": False}
        restored = restaurar_cena(db_path=isolated_env)
    assert restored["status"] == "success"
    assert restored["counts"]["confirmed"] == 2


def test_9_proposal_expiration_duplicate_confirmation_superseded_and_session_binding(isolated_env: Path):
    """
    Etapa 3 — Requirements 1 & 6:
    - Confirming an expired proposal (> 60s) is rejected (`proposal_expired`).
    - Confirming the same proposal twice is rejected (`duplicate_confirmation`).
    - Creating a second proposal in the same session supersedes the first (`proposal_superseded`).
    - Confirming from a different voice session is rejected (`session_mismatch`).
    """
    fake_now = [1000.0]
    mgr = get_scene_confirmation_manager()
    mgr._clock = lambda: fake_now[0]

    try:
        # 1. Expiration after 60s
        p1 = propor_cena_personalizada(
            "Rotina Expirada",
            [{"acao": "silenciar_avisos"}],
            session_id="sess_1",
            db_path=isolated_env,
        )
        fake_now[0] += 61.0
        exp_res = confirmar_rotina_personalizada(p1["proposal_id"], session_id="sess_1", db_path=isolated_env)
        assert exp_res["status"] == "proposal_expired"
        assert get_custom_scene_from_db("rotina_expirada", db_path=isolated_env) is None

        # 2. Superseding older proposal in same session
        p2_old = propor_cena_personalizada(
            "Rotina Antiga",
            [{"acao": "silenciar_avisos"}],
            session_id="sess_1",
            db_path=isolated_env,
        )
        p2_new = propor_cena_personalizada(
            "Rotina Nova",
            [{"acao": "ativar_avisos"}],
            session_id="sess_1",
            db_path=isolated_env,
        )
        sup_res = confirmar_rotina_personalizada(p2_old["proposal_id"], session_id="sess_1", db_path=isolated_env)
        assert sup_res["status"] == "proposal_superseded"

        # 3. Cross-session confirmation rejected
        mismatch_res = confirmar_rotina_personalizada(p2_new["proposal_id"], session_id="sess_2", db_path=isolated_env)
        assert mismatch_res["status"] == "session_mismatch"

        # 4. Valid confirmation succeeds once, duplicate confirmation rejected
        ok_res = confirmar_rotina_personalizada(p2_new["proposal_id"], session_id="sess_1", db_path=isolated_env)
        assert ok_res["status"] == "success"

        dup_res = confirmar_rotina_personalizada(p2_new["proposal_id"], session_id="sess_1", db_path=isolated_env)
        assert dup_res["status"] == "duplicate_confirmation"
    finally:
        mgr._clock = time.monotonic


def test_10_unauthorized_actions_and_unauthorized_app_identifiers_rejected(isolated_env: Path):
    """
    Etapa 3 — Requirements 2, 3 & 6:
    - Reject arbitrary OS commands or unknown actions (`executar_shell`, `rm -rf`).
    - Reject unauthorized app identifiers (`powershell`, `cmd`, `C:\\Windows\\System32\\cmd.exe`, `regedit`).
    - Reject closing Windows Explorer (`explorer`) in custom routines.
    """
    # Arbitrary action type
    bad_action = propor_cena_personalizada(
        "Cena Hacker",
        [{"acao": "executar_shell", "comando": "del /f /q *"}],
        db_path=isolated_env,
    )
    assert bad_action["status"] == "invalid_steps"
    assert "não é permitida pelo catálogo de segurança" in bad_action["message"]

    # Unauthorized shell/system app
    for forbidden_app in ("powershell", "cmd", "regedit", "taskmgr", "C:\\Windows\\System32\\cmd.exe", "notepad.exe"):
        bad_app = propor_cena_personalizada(
            "Cena App Proibido",
            [{"acao": "abrir_app_pc", "aplicativo": forbidden_app}],
            db_path=isolated_env,
        )
        assert bad_app["status"] == "invalid_steps"

    # Closing explorer is forbidden
    bad_close_explorer = propor_cena_personalizada(
        "Fechar Shell",
        [{"acao": "fechar_app_pc", "aplicativo": "explorer"}],
        db_path=isolated_env,
    )
    assert bad_close_explorer["status"] == "invalid_steps"
    assert "proteger o shell do Windows" in bad_close_explorer["message"]


def test_11_sensitive_action_close_app_requires_execution_confirmation_and_warns_unsaved_docs(isolated_env: Path):
    """
    Etapa 3 — Requirements 3 & 6:
    - A custom scene with `fechar_app_pc` warns about unsaved documents during creation.
    - When `executar_cena` is called on a saved sensitive scene, it returns `confirmation_required`
      (`operation == 'execute_sensitive_scene'`) instead of closing the app immediately.
    - Only after confirming the execution proposal does it close the app, reporting honestly
      whether the close was `confirmed` or `sent_unverified` (e.g. unsaved document dialog blocking exit).
    """
    prop = propor_cena_personalizada(
        "Encerrar Bloco de Notas",
        [
            {"acao": "silenciar_avisos"},
            {"acao": "fechar_app_pc", "aplicativo": "notepad"},
        ],
        db_path=isolated_env,
    )
    assert prop["status"] == "confirmation_required"
    assert prop["has_sensitive_actions"] is True
    assert "documentos não salvos" in prop["message"]

    # Confirm saving the scene
    save_res = confirmar_rotina_personalizada(prop["proposal_id"], db_path=isolated_env)
    assert save_res["status"] == "success"

    # Attempt to execute -> must block and ask for specific execution confirmation!
    exec_gate = executar_cena("Encerrar Bloco de Notas", db_path=isolated_env)
    assert exec_gate["status"] == "confirmation_required"
    assert exec_gate["operation"] == "execute_sensitive_scene"
    assert "documentos não salvos" in exec_gate["message"]

    # Confirm execution -> simulate Notepad staying open due to unsaved changes prompt ("inconclusive")
    with patch("src.tools.windows_apps.close_application") as mock_close:
        mock_close.return_value = {
            "status": "inconclusive",
            "message": "Janela recebeu WM_CLOSE, mas processo continua aberto.",
        }
        final_exec = confirmar_rotina_personalizada(exec_gate["proposal_id"], db_path=isolated_env)

    assert final_exec["status"] == "partial"
    assert final_exec["counts"] == {"total": 2, "confirmed": 1, "sent_unverified": 1, "failed": 0}
    step_close = {s["step_id"]: s for s in final_exec["steps"]}["step_2_fechar_app_pc"]
    assert step_close["verification_level"] == "sent_unverified"
    assert "documento não salvo" in step_close["message"]


def test_12_native_scenes_protected_against_overwrite_and_deletion_and_custom_deletion_requires_confirm(
    isolated_env: Path,
):
    """
    Etapa 3 — Requirements 4 & 6:
    - Native scenes (`bom_dia`, `modo_cinema`, `modo_foco`, `boa_noite`, `restaurar` and aliases)
      cannot be overwritten or deleted.
    - Deleting a custom scene requires two-phase confirmation.
    """
    for native_name in ("bom_dia", "Modo Cinema", "modo_foco", "Boa Noite", "restaurar", "cinema"):
        overwrite_attempt = propor_cena_personalizada(
            native_name,
            [{"acao": "silenciar_avisos"}],
            db_path=isolated_env,
        )
        assert overwrite_attempt["status"] == "protected_native_scene"

        delete_attempt = remover_cena_personalizada(native_name, db_path=isolated_env)
        assert delete_attempt["status"] == "protected_native_scene"

    # Create and confirm a custom scene, then test two-phase deletion
    p_create = propor_cena_personalizada(
        "Rotina Temporaria",
        [{"acao": "consultar_canal_youtube"}],
        db_path=isolated_env,
    )
    confirmar_rotina_personalizada(p_create["proposal_id"], db_path=isolated_env)
    assert get_custom_scene_from_db("rotina_temporaria", db_path=isolated_env) is not None

    p_del = remover_cena_personalizada("Rotina Temporaria", db_path=isolated_env)
    assert p_del["status"] == "confirmation_required"
    # Still exists before confirming deletion
    assert get_custom_scene_from_db("rotina_temporaria", db_path=isolated_env) is not None

    del_ok = confirmar_rotina_personalizada(p_del["proposal_id"], db_path=isolated_env)
    assert del_ok["status"] == "success"
    assert get_custom_scene_from_db("rotina_temporaria", db_path=isolated_env) is None
