"""Unit tests for Google Tasks integration (Phase 4)."""

import io
import json
from unittest.mock import MagicMock, patch

import pytest

from src.tools import ALL_ATON_TOOLS, dispatch_tool
from src.tools.google_tasks import (
    GOOGLE_TASKS_FUNCTION_DECLARATIONS,
    complete_task,
    create_task,
    dispatch_tasks_tool,
    list_tasks,
)


def test_list_tasks_unauthenticated():
    """Verify behavior when no credentials exist."""
    with patch("src.tools.google_tasks._get_credentials", return_value=None):
        res = list_tasks()
        assert res["status"] == "not_authenticated"
        assert "Google Tarefas ainda não está autenticado" in res["message"]
        assert res["tasks"] == []


def test_list_tasks_empty():
    """Verify behavior when user has no pending tasks."""
    mock_creds = MagicMock()
    mock_creds.valid = True
    mock_creds.token = "mock_token"

    mock_resp = io.BytesIO(json.dumps({"items": []}).encode("utf-8"))

    with patch("src.tools.google_tasks._get_credentials", return_value=mock_creds), \
         patch("urllib.request.urlopen", return_value=mock_resp):
        res = list_tasks()
        assert res["status"] == "success"
        assert res["count"] == 0
        assert "não tem nenhuma tarefa pendente" in res["message"]


def test_list_tasks_success():
    """Verify listing pending tasks and formatting spoken response."""
    mock_creds = MagicMock()
    mock_creds.valid = True
    mock_creds.token = "mock_token"

    sample_tasks = {
        "items": [
            {"id": "tsk_1", "title": "Comprar café", "status": "needsAction"},
            {"id": "tsk_2", "title": "Enviar relatório", "status": "needsAction"},
            {"id": "tsk_3", "title": "Tarefa concluída", "status": "completed"},
        ]
    }
    mock_resp = io.BytesIO(json.dumps(sample_tasks).encode("utf-8"))

    with patch("src.tools.google_tasks._get_credentials", return_value=mock_creds), \
         patch("urllib.request.urlopen", return_value=mock_resp):
        res = list_tasks(show_completed=False)
        assert res["status"] == "success"
        assert res["count"] == 2
        assert len(res["tasks"]) == 2
        assert res["tasks"][0]["title"] == "Comprar café"
        assert "Você tem 2 tarefas pendentes" in res["message"]


def test_create_task_unauthenticated():
    """Verify create_task when unauthenticated."""
    with patch("src.tools.google_tasks._get_credentials", return_value=None):
        res = create_task("Ligar para o banco")
        assert res["status"] == "not_authenticated"


def test_create_task_success():
    """Verify creating a new task with due date."""
    mock_creds = MagicMock()
    mock_creds.valid = True
    mock_creds.token = "mock_token"

    sample_created = {
        "id": "new_tsk_99",
        "title": "Pagar fatura",
        "due": "2026-10-30T00:00:00.000Z",
    }
    mock_resp = io.BytesIO(json.dumps(sample_created).encode("utf-8"))

    with patch("src.tools.google_tasks._get_credentials", return_value=mock_creds), \
         patch("urllib.request.urlopen", return_value=mock_resp):
        res = create_task(
            title="Pagar fatura",
            notes="No aplicativo do banco",
            due_date="amanhã",
        )
        assert res["status"] == "success"
        assert res["task_id"] == "new_tsk_99"
        assert "Tarefa 'Pagar fatura' adicionada com sucesso" in res["message"]


def test_complete_task_by_id():
    """Verify completing task directly by ID."""
    mock_creds = MagicMock()
    mock_creds.valid = True
    mock_creds.token = "mock_token"

    sample_patch_resp = {
        "id": "tsk_abc123xyz456789",
        "title": "Comprar pão",
        "status": "completed",
    }
    mock_resp = io.BytesIO(json.dumps(sample_patch_resp).encode("utf-8"))

    with patch("src.tools.google_tasks._get_credentials", return_value=mock_creds), \
         patch("urllib.request.urlopen", return_value=mock_resp):
        res = complete_task(task_id_or_title="tsk_abc123xyz456789")
        assert res["status"] == "success"
        assert res["task_id"] == "tsk_abc123xyz456789"
        assert "marcada como concluída com sucesso" in res["message"]


def test_complete_task_by_title_matching():
    """Verify completing task by natural title match."""
    mock_creds = MagicMock()
    mock_creds.valid = True
    mock_creds.token = "mock_token"

    existing_tasks = {
        "status": "success",
        "tasks": [
            {"id": "tsk_matched_id", "title": "Comprar pão de queijo"},
            {"id": "tsk_other", "title": "Lavar o carro"},
        ],
    }

    sample_patch_resp = {
        "id": "tsk_matched_id",
        "title": "Comprar pão de queijo",
        "status": "completed",
    }
    mock_resp = io.BytesIO(json.dumps(sample_patch_resp).encode("utf-8"))

    with patch("src.tools.google_tasks._get_credentials", return_value=mock_creds), \
         patch("src.tools.google_tasks.list_tasks", return_value=existing_tasks), \
         patch("urllib.request.urlopen", return_value=mock_resp):
        res = complete_task(task_id_or_title="comprar pão")
        assert res["status"] == "success"
        assert res["task_id"] == "tsk_matched_id"
        assert "Comprar pão de queijo" in res["message"]


def test_dispatch_tasks_tools():
    """Test unified dispatcher for Google Tasks."""
    with patch("src.tools.google_tasks.list_tasks", return_value={"status": "ok"}) as mock_list:
        res = dispatch_tool("list_tasks", {"show_completed": False})
        assert res["status"] == "ok"
        mock_list.assert_called_once()

    with patch("src.tools.google_tasks.create_task", return_value={"status": "ok"}) as mock_create:
        res = dispatch_tool("create_task", {"title": "Lembrar reunião"})
        assert res["status"] == "ok"
        mock_create.assert_called_once()

    with patch("src.tools.google_tasks.complete_task", return_value={"status": "ok"}) as mock_comp:
        res = dispatch_tool("complete_task", {"task_id_or_title": "Lembrar reunião"})
        assert res["status"] == "ok"
        mock_comp.assert_called_once()

    # Missing task ID / title
    res_err = dispatch_tasks_tool("complete_task", {})
    assert res_err["status"] == "error"

    # Unknown tool
    res_unk = dispatch_tasks_tool("unknown_tasks_action", {})
    assert res_unk["status"] == "error"


def test_all_aton_tools_count_with_tasks():
    """Verify ALL_ATON_TOOLS includes at least 24 tools."""
    assert len(ALL_ATON_TOOLS) >= 24
    names = [t["name"] for t in ALL_ATON_TOOLS]
    assert "list_tasks" in names
    assert "create_task" in names
    assert "complete_task" in names
