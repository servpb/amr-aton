"""Unit tests for Long-Term Semantic Memory and Daily Executive Briefing (Phase 5)."""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from src.core.memory import (
    MEMORY_FUNCTION_DECLARATIONS,
    dispatch_memory_tool,
    forget_memory,
    get_daily_briefing,
    recall_memory,
    remember_fact,
)
from src.tools import ALL_ATON_TOOLS, dispatch_tool


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database path for isolated testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def test_remember_fact_insert_and_update(temp_db):
    """Test inserting and updating memories (UPSERT behavior)."""
    # 1. Insert new fact
    res1 = remember_fact(
        category="preferência",
        key="resolucao_video",
        content="O usuário prefere exportar vídeos em 4K 60fps.",
        db_path=temp_db,
    )
    assert res1["status"] == "success"
    assert "4K 60fps" in res1["message"]
    assert res1["key"] == "resolucao_video"

    # 2. Update existing fact
    res2 = remember_fact(
        category="preferência",
        key="resolucao_video",
        content="O usuário prefere exportar vídeos em 8K HDR.",
        db_path=temp_db,
    )
    assert res2["status"] == "success"
    assert "8K HDR" in res2["message"]

    # Verify query returns updated version
    query_res = recall_memory(query="resolução", db_path=temp_db)
    assert query_res["status"] == "success"
    assert len(query_res["memories"]) == 1
    assert "8K HDR" in query_res["memories"][0]["content"]


def test_recall_memory_matching_and_not_found(temp_db):
    """Test querying memories with token matches and non-matching queries."""
    remember_fact(
        category="pessoal",
        key="aniversario",
        content="O aniversário do usuário é dia 15 de maio.",
        db_path=temp_db,
    )
    remember_fact(
        category="trabalho",
        key="projeto_principal",
        content="O projeto em desenvolvimento é o assistente Aton.",
        db_path=temp_db,
    )

    # 1. Match by query keyword
    res_bday = recall_memory(query="quando é meu aniversário?", db_path=temp_db)
    assert res_bday["status"] == "success"
    assert res_bday["count"] >= 1
    assert "15 de maio" in res_bday["message"]

    # 2. Match by category
    res_work = recall_memory(query="assistente", category="trabalho", db_path=temp_db)
    assert res_work["status"] == "success"
    assert "Aton" in res_work["message"]

    # 3. Not found
    res_none = recall_memory(query="qual a capital da França?", db_path=temp_db)
    assert res_none["status"] == "not_found"
    assert "Não encontrei nenhuma lembrança" in res_none["message"]


def test_forget_memory(temp_db):
    """Test deleting memories from database."""
    remember_fact("trabalho", "servidor_teste", "IP do servidor é 192.168.1.100", db_path=temp_db)

    # Delete existing
    res_del = forget_memory("servidor_teste", db_path=temp_db)
    assert res_del["status"] == "success"
    assert res_del["deleted"] == 1

    # Verify gone
    res_check = recall_memory("servidor", db_path=temp_db)
    assert res_check["status"] == "not_found"

    # Delete non-existing
    res_del_none = forget_memory("chave_inexistente", db_path=temp_db)
    assert res_del_none["status"] == "not_found"
    assert res_del_none["deleted"] == 0


def test_get_daily_briefing_aggregation():
    """Test generating a comprehensive morning executive briefing."""
    mock_cal = {
        "status": "success",
        "events": [
            {"summary": "Reunião de Diretoria", "display_time": "14:00"},
        ],
    }
    mock_tasks = {
        "status": "success",
        "tasks": [
            {"title": "Revisar relatório trimestral"},
            {"title": "Enviar proposta para cliente"},
        ],
    }
    mock_gmail = {
        "status": "success",
        "emails": [
            {"from": "Ana Gerente", "subject": "Aprovação do Projeto"},
        ],
    }

    with patch("src.tools.google_calendar.get_calendar_events", return_value=mock_cal), \
         patch("src.tools.google_tasks.list_tasks", return_value=mock_tasks), \
         patch("src.tools.gmail.list_unread_emails", return_value=mock_gmail):
        briefing = get_daily_briefing()
        assert briefing["status"] == "success"
        msg = briefing["message"]

        # Check all components in speech
        assert "resumo executivo" in msg
        assert "Reunião de Diretoria" in msg
        assert "Revisar relatório trimestral" in msg
        assert "Ana Gerente" in msg
        assert "Aprovação do Projeto" in msg
        assert "produtivo dia" in msg


def test_dispatch_memory_tools():
    """Test unified dispatcher for semantic memory tools."""
    with patch("src.core.memory.remember_fact", return_value={"status": "ok"}) as mock_rem:
        res = dispatch_tool("remember_fact", {"key": "musica", "content": "gosto de jazz"})
        assert res["status"] == "ok"
        mock_rem.assert_called_once()

    with patch("src.core.memory.recall_memory", return_value={"status": "ok"}) as mock_rec:
        res = dispatch_tool("recall_memory", {"query": "jazz"})
        assert res["status"] == "ok"
        mock_rec.assert_called_once()

    with patch("src.core.memory.forget_memory", return_value={"status": "ok"}) as mock_for:
        res = dispatch_tool("forget_memory", {"key": "musica"})
        assert res["status"] == "ok"
        mock_for.assert_called_once()

    with patch("src.core.memory.get_daily_briefing", return_value={"status": "ok"}) as mock_bri:
        res = dispatch_tool("get_daily_briefing", {})
        assert res["status"] == "ok"
        mock_bri.assert_called_once()

    # Errors on missing arguments
    assert dispatch_memory_tool("remember_fact", {})["status"] == "error"
    assert dispatch_memory_tool("recall_memory", {})["status"] == "error"
    assert dispatch_memory_tool("forget_memory", {})["status"] == "error"
    assert dispatch_memory_tool("unknown_memory_action", {})["status"] == "error"


def test_all_aton_tools_count_with_memory():
    """Verify ALL_ATON_TOOLS includes at least 28 tools."""
    assert len(ALL_ATON_TOOLS) >= 28
    names = [t["name"] for t in ALL_ATON_TOOLS]
    assert "remember_fact" in names
    assert "recall_memory" in names
    assert "forget_memory" in names
    assert "get_daily_briefing" in names
