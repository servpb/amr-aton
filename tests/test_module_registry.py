"""Unit tests for Aton Module Registry, capability explanation, and autoconhecimento introspection."""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.core.module_registry import (
    ModuleRegistry,
    get_module_registry,
    _check_fire_tv_status,
)
from src.tools import ALL_ATON_TOOLS, dispatch_tool
from src.tools.module_tools import (
    MODULE_TOOLS_DECLARATIONS,
    detalhar_modulo,
    listar_modulos,
    listar_recursos_pendentes,
)


@pytest.fixture
def registry():
    return get_module_registry()


# 1. Ferramentas registradas aparecem no catálogo de módulos
def test_registered_tools_appear_in_catalog(registry):
    overview = registry.list_modules_overview()
    assert overview["status"] == "success"
    assert overview["total_modulos"] > 0
    assert overview["total_areas"] >= 4

    # Detail fire_tv module
    detail = registry.detail_module("fire_tv")
    assert detail["status"] == "success"
    assert "launch_fire_tv_app" in detail["ferramentas_registradas"]
    assert "control_fire_tv" in detail["ferramentas_registradas"]


# 2. Ferramentas removidas não continuam anunciadas
def test_removed_tools_not_announced(registry):
    # Mock active tools set omitting 'launch_fire_tv_app'
    with patch.object(registry, "_get_active_tool_names", return_value={"control_fire_tv"}):
        detail = registry.detail_module("fire_tv")
        assert detail["status"] == "success"
        assert "launch_fire_tv_app" not in detail["ferramentas_registradas"]
        assert "control_fire_tv" in detail["ferramentas_registradas"]


# 3. Módulos sem configuração recebem estado adequado e honesto
def test_unconfigured_and_unavailable_status(registry):
    # Smart TV direct volume/power is unavailable
    tv_detail = registry.detail_module("smart_tv")
    assert tv_detail["estado"] == "indisponivel"
    assert "não disponível nesta versão" in tv_detail["motivo_estado"]

    # Pending list returns modules needing configuration or unavailable
    pending = registry.list_unconfigured_or_pending()
    assert pending["status"] == "success"
    slugs = [p["id"] for p in pending["modulos_pendentes"]]
    assert "smart_tv" in slugs


# 4. Falhas de dependência não derrubam a consulta
def test_evaluator_exception_gracefully_handled(registry):
    broken_mod = registry._definitions[0]
    original_eval = broken_mod._status_evaluator
    try:
        broken_mod._status_evaluator = MagicMock(side_effect=RuntimeError("Simulated dependency crash"))
        status, reason, last_ver = broken_mod.evaluate_status({"launch_fire_tv_app"})
        assert status == "estado_desconhecido"
        assert "Simulated dependency crash" in reason
    finally:
        broken_mod._status_evaluator = original_eval


# 5. Resolução de nomes e apelidos flexíveis
def test_alias_resolution(registry):
    # Match via aliases
    for alias in ["fire stick", "stick", "firetv", "fire tv"]:
        res = registry.detail_module(alias)
        assert res["status"] == "success"
        assert res["id"] == "fire_tv"

    # Match youtube alias
    yt = registry.detail_module("youtube canal")
    assert yt["status"] == "success"
    assert yt["id"] == "youtube"

    # Ambiguous alias
    with patch.object(registry, "_definitions", [
        MagicMock(slug="app_1", name="App 1", aliases=["teste"], expected_tool_names=["t1"], evaluate_status=lambda s: ("disponivel", "", None)),
        MagicMock(slug="app_2", name="App 2", aliases=["teste"], expected_tool_names=["t2"], evaluate_status=lambda s: ("disponivel", "", None)),
    ]):
        amb = registry.detail_module("teste")
        assert amb["status"] == "ambiguous"
        assert "mais de um módulo" in amb["message"]

    # Unknown alias
    unknown = registry.detail_module("modulo_fantasma_inexistente")
    assert unknown["status"] == "not_found"


# 6. Privacidade: nenhum segredo é exposto
def test_zero_secrets_exposed(registry):
    # Inspect all module details and overviews
    overview = registry.list_modules_overview()
    overview_str = json.dumps(overview, ensure_ascii=False).lower()

    for secret_word in ["api_key", "secret", "password", "service_role", "bearer", "ghp_"]:
        assert secret_word not in overview_str

    # Fire TV state must mask serial
    ftv_detail = registry.detail_module("fire_tv")
    ftv_str = json.dumps(ftv_detail, ensure_ascii=False)
    assert "G071CQ2042741DJK" not in ftv_str
    if ftv_detail.get("ultima_verificacao"):
        assert "G071...1DJK" in ftv_detail["ultima_verificacao"]["serial"]


# 7. Listar módulos não realiza chamadas de rede ou ações físicas
def test_listing_modules_makes_no_external_calls(registry):
    with patch("subprocess.run") as mock_subproc, patch("socket.socket") as mock_sock:
        res = registry.list_modules_overview()
        assert res["status"] == "success"
        det = registry.detail_module("fire_tv")
        assert det["status"] == "success"

        # Neither subprocess nor sockets were spawned
        mock_subproc.assert_not_called()
        mock_sock.assert_not_called()


# 8. Ferramentas chegam às declarações do Gemini e ao despachante
def test_module_tools_reach_dispatcher_and_declarations():
    decl_names = [d["name"] for d in MODULE_TOOLS_DECLARATIONS]
    assert "listar_modulos" in decl_names
    assert "detalhar_modulo" in decl_names
    assert "listar_recursos_pendentes" in decl_names

    all_names = [t["name"] for t in ALL_ATON_TOOLS]
    for d_name in decl_names:
        assert d_name in all_names

    # Test dispatch_tool routing
    res_list = dispatch_tool("listar_modulos", {})
    assert res_list["status"] == "success"
    assert "total_modulos" in res_list

    res_det = dispatch_tool("detalhar_modulo", {"modulo": "fire_tv"})
    assert res_det["status"] == "success"
    assert res_det["id"] == "fire_tv"

    res_pend = dispatch_tool("listar_recursos_pendentes", {})
    assert res_pend["status"] == "success"


# 9. Integração com consultar_autoconhecimento
def test_consultar_autoconhecimento_integration():
    from src.core.second_brain import SecondBrainClient
    client = SecondBrainClient()

    # Question about modules
    res_mod = client.consultar_autoconhecimento("Quais módulos você tem?")
    assert res_mod["status"] == "success"
    assert "áreas principais" in res_mod["message"]

    # Question about what Aton can do in Fire Stick
    res_ftv = client.consultar_autoconhecimento("O que você faz no Fire Stick?")
    assert res_ftv["status"] == "success"
    assert "Fire TV Stick" in res_mod["message"] or "Fire TV Stick" in res_ftv["message"]



# 10. Cadastro sem verificação informa necessidade de checagem
def test_fire_tv_status_configured_without_prior_verification(registry, monkeypatch):
    from unittest.mock import patch
    with patch("src.core.module_registry.load_confirmed_fire_tv_state", return_value={}):
        monkeypatch.setattr("src.config.settings.fire_tv_ip", "192.168.0.13")
        monkeypatch.setattr("src.config.settings.fire_tv_adb_path", "C:/Windows/notepad.exe")

        det = registry.detail_module("fire_tv")
        assert det["status"] == "success"
        assert "ainda precisa de verificação" in det["motivo_estado"]
        assert "identidade foi conferida" not in det["motivo_estado"]
        assert "192.168.0.13" not in det["motivo_estado"]
        assert "192.168.0.13" not in det["mensagem_voz"]
        assert det["ultima_verificacao"]["verificacao_anterior"] is False
        assert det["ultima_verificacao"]["conectividade_atual"] == "nao_verificada_nesta_consulta"


# 11. Registro de checagem anterior reconhece identidade conferida sem afirmar conexão viva
def test_fire_tv_status_verified_prior_record(registry, monkeypatch):
    from unittest.mock import patch
    fake_state = {
        "confirmed_ip": "192.168.0.13",
        "serial": "G071TESTSERIAL1234",
        "confirmed_at": 1730300000,
        "model": "AFTSS",
    }
    with patch("src.core.module_registry.load_confirmed_fire_tv_state", return_value=fake_state):
        monkeypatch.setattr("src.config.settings.fire_tv_adb_path", "C:/Windows/notepad.exe")

        det = registry.detail_module("fire_tv")
        assert det["status"] == "success"
        assert "identidade foi conferida na última conexão" in det["motivo_estado"]
        assert "Posso verificar se ele está disponível agora" in det["motivo_estado"]
        assert "192.168.0.13" not in det["motivo_estado"]
        assert "192.168.0.13" not in det["mensagem_voz"]
        assert det["ultima_verificacao"]["verificacao_anterior"] is True
        assert "data_confirmacao" in det["ultima_verificacao"]
        assert det["ultima_verificacao"]["data_confirmacao"] != ""
        assert det["ultima_verificacao"]["conectividade_atual"] == "nao_verificada_nesta_consulta"


# 12. Ausência de afirmações de conectividade atual na fala
def test_no_live_connectivity_assertion_or_ip_leak_in_speech(registry):
    det = registry.detail_module("fire_tv")
    assert det["status"] == "success"
    # Never claim it is connected right now just by checking catalog
    assert "está conectado agora" not in det["mensagem_voz"].lower()
    assert "conectado no momento" not in det["mensagem_voz"].lower()
    # IP is omitted in voice text unless specifically asked
    assert "192.168." not in det["mensagem_voz"]
