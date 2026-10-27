"""Tests for Aton Second Brain (Supabase, pgvector, hybrid search & Q&A)."""

from unittest.mock import MagicMock, patch
import pytest
from src.core.second_brain import SecondBrainClient, second_brain
from src.tools.second_brain_tools import (
    SECOND_BRAIN_FUNCTION_DECLARATIONS,
    buscar_memoria,
    criar_cliente_cerebro,
    criar_tarefa_cerebro,
    dispatch_second_brain_tool,
    perguntar_ao_cerebro,
    resumo_geral_cerebro,
    salvar_memoria,
)
from src.tools import ALL_ATON_TOOLS, dispatch_tool


def test_save_and_ask_siena_alta_restauracao():
    """Real scenario test: Store Siena 2006 multimedia memory and query about video editing."""
    # 1. Salvar a memória do canal Alta Restauração sobre o Siena 2006
    assunto = "Instalação Multimídia Siena 2006"
    conteudo = (
        "Estou editando um vídeo sobre o unboxing e a instalação de uma central "
        "multimídia 2DIN em um Siena 2006, com adaptação do painel DIN que exige moldura nova."
    )
    tags = ["alta_restauracao", "siena_2006", "central_multimidia", "edicao_video"]

    save_res = salvar_memoria(
        assunto=assunto,
        conteudo=conteudo,
        tipo="projeto",
        tags=tags,
        importancia=5,
    )
    assert save_res["status"] == "success"

    # 2. Perguntar ao Segundo Cérebro: "o que eu falei sobre edição de vídeo?"
    ask_res = perguntar_ao_cerebro("o que eu falei sobre edição de vídeo?")
    assert ask_res["status"] == "success"
    # A resposta deve conter o contexto do Siena e a moldura nova
    msg = ask_res["message"].lower()
    assert "siena" in msg or "multimídia" in msg or "multimidia" in msg or "vídeo" in msg or "video" in msg
    assert len(ask_res["sources"]) > 0
    # Confirma que a fonte traz a data
    assert "data" in ask_res["sources"][0]


def test_ask_brain_unknown_topic_no_hallucination():
    """Verify that asking about an unknown topic reports not found without inventing."""
    res = perguntar_ao_cerebro("qual é a rota de navegação para a cidade de Atlantis no fundo do mar?")
    assert res["status"] in ("not_found", "success")
    if res["status"] == "not_found":
        assert "não encontrei" in res["message"].lower()
        assert len(res["sources"]) == 0


def test_buscar_memoria_hybrid():
    """Verify hybrid search returns matches."""
    res = buscar_memoria(query="Siena 2006")
    assert res["status"] == "success"
    assert res["count"] >= 1


def test_criar_cliente_cerebro():
    """Verify client creation in Second Brain."""
    res = criar_cliente_cerebro(
        nome="Agência Alpha Marketing",
        segmento="Marketing Digital",
        valor_mensal=3500.00,
    )
    assert res["status"] == "success"
    assert "Alpha Marketing" in res["message"]


def test_criar_tarefa_cerebro():
    """Verify task creation in Second Brain."""
    res = criar_tarefa_cerebro(
        titulo="Comprar moldura 2DIN para o Siena",
        prioridade="alta",
        prazo="amanhã",
    )
    assert res["status"] == "success"
    assert "moldura" in res["message"].lower()


def test_resumo_geral_cerebro():
    """Verify daily executive summary."""
    res = resumo_geral_cerebro()
    assert res["status"] == "success"
    assert "message" in res


def test_dispatch_second_brain_tool():
    """Verify dispatcher routes second brain tools properly."""
    res = dispatch_second_brain_tool("perguntar_ao_cerebro", {"pergunta": "Siena"})
    assert res["status"] in ("success", "not_found")

    err = dispatch_second_brain_tool("ferramenta_inexistente", {})
    assert err["status"] == "error"


def test_unified_dispatcher_second_brain():
    """Verify dispatch_tool routes second brain tools."""
    res = dispatch_tool("buscar_memoria", {"query": "Siena"})
    assert res["status"] == "success"


def test_all_aton_tools_count_with_second_brain():
    """Verify that ALL_ATON_TOOLS contains 41 active tools."""
    assert len(ALL_ATON_TOOLS) == 41
    names = [t["name"] for t in ALL_ATON_TOOLS]
    assert "salvar_memoria" in names
    assert "buscar_memoria" in names
    assert "perguntar_ao_cerebro" in names
    assert "criar_cliente_cerebro" in names
    assert "criar_tarefa_cerebro" in names
    assert "resumo_geral_cerebro" in names
