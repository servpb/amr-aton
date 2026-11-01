"""Unit tests for structured task context and result verification in Aton."""

import time
from unittest.mock import MagicMock, patch
import pytest

from src.core.task_context import (
    TaskContext,
    TaskContextManager,
    get_task_context,
)
from src.tools.task_tools import (
    TASK_TOOLS_DECLARATIONS,
    cancelar_tarefa_atual,
    consultar_status_tarefa,
    dispatch_task_tool,
    selecionar_opcao_pendente,
)


@pytest.fixture
def task_mgr():
    """Isolated task context manager for testing."""
    mgr = TaskContextManager(timeout_seconds=5.0)
    return mgr


# 1. Transições de estado válidas
def test_valid_task_state_transitions(task_mgr):
    task = task_mgr.start_task(summary="Abrir YouTube no Fire Stick", target="fire_tv")
    assert task.state == "pronta"
    assert task.current_step == "compreendido"

    # Action planned
    task_id, act_id = task_mgr.record_action_planned("launch_fire_tv_app", {"app_name": "youtube"})
    assert task.state == "executando"
    assert task.current_step == "acao_planejada"

    # Transport confirmed
    task_mgr.record_transport_result(task_id, act_id, "sent_confirmed")
    assert task.transport_state == "sent_confirmed"
    assert task.current_step == "comando_enviado"

    # Verification confirmed
    task_mgr.record_verification_result(
        task_id,
        act_id,
        "confirmed",
        evidence={"type": "foreground_package", "package": "com.amazon.firetv.youtube"},
    )
    assert task.state == "concluida"
    assert task.verification_state == "confirmed"
    assert task.current_step == "resultado_confirmado"
    assert task.evidence["package"] == "com.amazon.firetv.youtube"


# 2. Retomada de pedido pendente após esclarecimento
def test_resume_after_destination_clarification(task_mgr):
    task_mgr.set_pending_action("open_app", {"app_name": "youtube"})
    assert task_mgr.get_pending_action() is not None

    from src.core.destination_guard import resolve_clarified_destination

    with patch("src.core.destination_guard.get_target_context", return_value=task_mgr), \
         patch("src.tools.fire_tv.launch_fire_tv_app") as mock_launch:
        mock_launch.return_value = {
            "status": "success",
            "confirmed": True,
            "message": "Aplicativo youtube aberto e confirmado no Fire Stick.",
        }
        res = resolve_clarified_destination("No Fire Stick")
        assert res["status"] == "success"
        mock_launch.assert_called_once_with("youtube")
        assert task_mgr.get_active_target() == "fire_tv"
        assert task_mgr.get_pending_action() is None


# 3. Escolha de uma opção realmente apresentada
def test_ordinal_choice_resolution_against_real_candidates(task_mgr):
    task = task_mgr.start_task(summary="Tocar Roberto Carlos")
    candidates = [
        {"id": "vid_111", "title": "Detalhes - Roberto Carlos"},
        {"id": "vid_222", "title": "Como É Grande o Meu Amor Por Você - Roberto Carlos"},
        {"id": "vid_333", "title": "Emoções - Roberto Carlos"},
    ]
    task_mgr.set_pending_candidates(candidates)

    assert task.state == "aguardando_esclarecimento"
    assert task.pending_clarification == "choice"

    # Test "a segunda"
    success, chosen, feedback = task_mgr.resolve_ordinal_choice("a segunda")
    assert success is True
    assert chosen["id"] == "vid_222"
    assert chosen["title"] == "Como É Grande o Meu Amor Por Você - Roberto Carlos"
    assert task.state == "pronta"
    assert task.pending_clarification is None

    # Test tool selecionar_opcao_pendente
    with patch("src.tools.task_tools.get_task_context", return_value=task_mgr), \
         patch("src.tools.fire_tv.play_fire_tv_youtube") as mock_play:
        mock_play.return_value = {"status": "success", "confirmed": True, "message": "Tocando no Fire Stick."}
        # Re-set candidates and call tool
        task_mgr.set_pending_candidates(candidates)
        tool_res = selecionar_opcao_pendente("a primeira")
        assert tool_res["status"] == "success"
        mock_play.assert_called_once_with(video_id="vid_111", destination="fire_tv")


# 4. Rejeição de ordinais inválidos ou sem lista prévia
def test_ordinal_choice_invalid_and_empty(task_mgr):
    # No task / no candidates
    success, chosen, feedback = task_mgr.resolve_ordinal_choice("a segunda")
    assert success is False
    assert "Nenhuma lista" in feedback

    # Out-of-bounds candidate
    task = task_mgr.start_task(summary="Opções limitadas")
    task_mgr.set_pending_candidates([{"id": "v1", "title": "Único Vídeo"}])
    success, chosen, feedback = task_mgr.resolve_ordinal_choice("a terceira")
    assert success is False
    assert "inválida" in feedback
    assert "Apresentei apenas 1" in feedback


# 5. Invalidação de opções antigas quando novo pedido chega
def test_invalidation_of_old_candidates_on_new_request(task_mgr):
    task1 = task_mgr.start_task(summary="Pedido 1")
    task_mgr.set_pending_candidates([{"id": "old_1", "title": "Vídeo Antigo"}])
    assert len(task1.references["candidates"]) == 1

    # New task starts
    task2 = task_mgr.start_task(summary="Pedido 2 Novo")
    assert task2.task_id != task1.task_id
    assert "candidates" not in task2.references or len(task2.references["candidates"]) == 0

    # Old choice fails on new task
    success, chosen, feedback = task_mgr.resolve_ordinal_choice("a primeira")
    assert success is False


# 6. Cancelamento antes do envio impede ação física
def test_cancellation_before_send_blocks_physical_execution(task_mgr):
    task = task_mgr.start_task(summary="Abrir Downloader", target="fire_tv")
    task_id, act_id = task_mgr.record_action_planned("launch_fire_tv_app", {"app_name": "downloader"})

    cancel_res = task_mgr.cancel_active_task(reason="Usuário pediu para cancelar")
    assert cancel_res["status"] == "cancelled"
    assert cancel_res["action_already_sent"] is False
    assert "antes do envio" in cancel_res["message"]

    # is_action_allowed must return False
    assert task_mgr.is_action_allowed(task_id) is False


# 7. Cancelamento depois do envio informa honestamente que o comando foi despachado
def test_cancellation_after_send_reports_sent_status(task_mgr):
    task = task_mgr.start_task(summary="Abrir Netflix", target="fire_tv")
    task_id, act_id = task_mgr.record_action_planned("launch_fire_tv_app", {"app_name": "netflix"})
    task_mgr.record_transport_result(task_id, act_id, "sent_confirmed")

    cancel_res = task_mgr.cancel_active_task(reason="Mudou de ideia")
    assert cancel_res["status"] == "cancelled"
    assert cancel_res["action_already_sent"] is True
    assert "já havia sido enviado" in cancel_res["message"]
    assert "interrompi as próximas etapas" in cancel_res["message"]


# 8. Descarte de callbacks assíncronos com task_id defasado
def test_stale_task_id_callback_ignored(task_mgr):
    task1 = task_mgr.start_task(summary="Tarefa Antiga")
    old_task_id = task1.task_id
    old_action_id = "act_old_123"

    # New task starts
    task2 = task_mgr.start_task(summary="Tarefa Nova")
    new_task_id = task2.task_id

    # Late verification from old task attempts to report
    res_transport = task_mgr.record_transport_result(old_task_id, old_action_id, "sent_confirmed")
    assert res_transport is False

    res_verify = task_mgr.record_verification_result(old_task_id, old_action_id, "confirmed", {"pkg": "old"})
    assert res_verify is False

    # New task must remain untouched
    assert task2.verification_state == "unverified"
    assert task2.evidence is None


# 9. Comando enviado sem confirmação no prazo (inconclusive)
def test_command_sent_without_confirmation_inconclusive(task_mgr):
    task = task_mgr.start_task(summary="Abrir App Pesado", target="fire_tv")
    task_id, act_id = task_mgr.record_action_planned("launch_fire_tv_app", {"app_name": "app_pesado"})
    task_mgr.record_transport_result(task_id, act_id, "sent_confirmed")

    task_mgr.record_verification_result(task_id, act_id, "inconclusive", evidence={"last_pkg": "com.amazon.tv.launcher"})
    assert task.state == "inconclusiva"
    assert task.verification_state == "inconclusive"
    assert task.transport_state == "sent_confirmed"


# 10. Falha de transporte com resultado incerto (sent_uncertain)
def test_transport_uncertain_failure_prevents_retry(task_mgr):
    task = task_mgr.start_task(summary="Comando com perda de rede", target="fire_tv")
    task_id, act_id = task_mgr.record_action_planned("control_fire_tv", {"action": "select"})

    task_mgr.record_transport_result(task_id, act_id, "sent_uncertain")
    assert task.transport_state == "sent_uncertain"
    # Action was potentially sent, so we do not treat it as not sent
    assert task.current_step == "falha_transporte"


# 11. Limpeza ao dormir cancela tarefa ativa e impede novas etapas
def test_clear_on_sleep_cancels_and_clears(task_mgr):
    task = task_mgr.start_task(summary="Tarefa em execução")
    task_id, act_id = task_mgr.record_action_planned("open_application", {"app_name": "chrome"})

    task_mgr.clear_on_sleep()
    assert task_mgr.get_active_task() is None
    assert task_mgr.get_active_target() is None

    # Stale action must be disallowed
    assert task_mgr.is_action_allowed(task_id) is False


# 12. Correlacionamento de evidência no PC (processo existente não confirma página)
def test_pc_window_correlation_distinguishes_page_load(task_mgr):
    from src.tools.windows_apps import open_application

    with patch("src.core.task_context.get_task_context", return_value=task_mgr), \
         patch("os.startfile"), \
         patch("subprocess.Popen"), \
         patch("pygetwindow.getAllTitles", return_value=["Google Chrome - Nova Guia"]):

        # Opening "youtube" when only blank Chrome is open
        res = open_application("youtube")
        assert res["status"] == "success"
        assert res["verification_state"] == "inconclusive"
        assert "não foi verificado" in res["message"] or "não pôde ser confirmado" in res["message"]


# 13. consultar_status_tarefa diferencia evidência histórica de consulta ao vivo
def test_consultar_status_tarefa_historical_vs_live(task_mgr):
    task = task_mgr.start_task(summary="Abrir YouTube", target="fire_tv", parameters={"app_name": "youtube"})
    task_id, act_id = task_mgr.record_action_planned("launch_fire_tv_app", {"app_name": "youtube"})
    task_mgr.record_transport_result(task_id, act_id, "sent_confirmed")
    task_mgr.record_verification_result(
        task_id, act_id, "confirmed", evidence={"package": "com.amazon.firetv.youtube"}
    )

    with patch("src.tools.task_tools.get_task_context", return_value=task_mgr):
        # 1. Historical query (default)
        hist = consultar_status_tarefa(verificar_ao_vivo=False, pergunta="como está?")
        assert hist["status"] == "success"
        assert hist["modo"] == "evidencia_historica"
        assert "Na última verificação feita" in hist["message"]

        # 2. Live query ("ele abriu?")
        with patch("src.tools.fire_tv._get_foreground_package", return_value="com.amazon.firetv.youtube"):
            live = consultar_status_tarefa(verificar_ao_vivo=True, pergunta="ele abriu?")
            assert live["status"] == "success"
            assert live["modo"] == "verificacao_ao_vivo"
            assert "está em primeiro plano" in live["message"]


# 14. Despachante integra as ferramentas de tarefa
def test_task_tools_dispatcher_integration(task_mgr):
    with patch("src.tools.task_tools.get_task_context", return_value=task_mgr):
        # Declarations schema check
        decl_names = [d["name"] for d in TASK_TOOLS_DECLARATIONS]
        assert "consultar_status_tarefa" in decl_names
        assert "selecionar_opcao_pendente" in decl_names
        assert "cancelar_tarefa_atual" in decl_names

        # Dispatcher calls
        res_status = dispatch_task_tool("consultar_status_tarefa", {})
        assert res_status["status"] == "success"

        res_cancel = dispatch_task_tool("cancelar_tarefa_atual", {"motivo": "Teste"})
        assert res_cancel["status"] == "cancelled"
