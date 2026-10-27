"""Tests for Screen Perception and UI Interaction Module.

Validates on-demand screen capture, active window detection, Gemini Vision
coordinate mapping, safety gates for destructive actions, and dispatchers.
"""

from unittest.mock import MagicMock, patch
from PIL import Image
import pytest

from src.core.screen_perceiver import ScreenPerceiver, screen_perceiver
from src.tools import ALL_ATON_TOOLS, dispatch_tool
from src.tools.screen_perception import (
    SCREEN_PERCEPTION_FUNCTION_DECLARATIONS,
    descrever_tela,
    dispatch_screen_perception_tool,
    ler_conteudo_tela,
    localizar_e_clicar_elemento,
    preencher_campo_na_tela,
    rolar_tela,
)


def test_active_window_info_detection():
    """Verify that active window detection returns expected fields and valid rect."""
    info = screen_perceiver.get_active_window_info()
    assert "title" in info
    assert "rect" in info
    assert "width" in info
    assert "height" in info
    assert len(info["rect"]) == 4
    assert info["width"] >= 0
    assert info["height"] >= 0


def test_capture_screen_returns_pil_image():
    """Verify that screen capture produces a valid PIL image."""
    img, info = screen_perceiver.capture_screen(target="fullscreen")
    assert isinstance(img, Image.Image)
    assert img.width > 100
    assert img.height > 100
    assert "rect" in info


def test_optimize_image_for_gemini():
    """Verify image compression and base64 encoding."""
    test_img = Image.new("RGB", (1920, 1080), color=(100, 150, 200))
    b64_str, scale = screen_perceiver.optimize_image_for_gemini(test_img, max_dim=1280)
    assert isinstance(b64_str, str)
    assert len(b64_str) > 50
    assert scale <= 1.0


def test_locate_element_coordinates_calculation():
    """Verify normalized bounding box [ymin, xmin, ymax, xmax] converts to absolute screen coordinates."""
    mock_perceiver = ScreenPerceiver(gemini_api_key="mock_key")
    
    # Mock visual analysis returning bounding box for a button in center of a 1000x800 window at offset (100, 50)
    fake_json_reply = (
        '{\n'
        '  "encontrado": true,\n'
        '  "elemento": "Botão Salvar",\n'
        '  "tipo": "botao",\n'
        '  "box_2d": [400, 450, 500, 550],\n'
        '  "confianca": "alta"\n'
        '}'
    )

    with patch.object(mock_perceiver, "analyze_visual_content") as mock_analyze:
        mock_analyze.return_value = {
            "status": "success",
            "text": fake_json_reply,
            "window": {"rect": (100, 50, 1100, 850), "title": "Editor de Teste"},
            "image_size": (1000, 800),
        }

        res = mock_perceiver.locate_element_coordinates(element_description="Botão Salvar")
        assert res["status"] == "success"
        assert res["elemento"] == "Botão Salvar"
        # Center of box [400..500, 450..550] is y=450, x=500.
        # Scaled to 1000x800: x=500, y=360.
        # Added window offset (100, 50): screen_x = 100 + 500 = 600, screen_y = 50 + 360 = 410.
        assert res["screen_x"] == 600
        assert res["screen_y"] == 410


def test_descrever_tela_mock():
    """Verify descrever_tela formats successful message from visual analysis."""
    with patch("src.tools.screen_perception.screen_perceiver.analyze_visual_content") as mock_analyze:
        mock_analyze.return_value = {
            "status": "success",
            "text": "Está visível o navegador Chrome com a aba do YouTube aberta.",
            "window": {"title": "Google Chrome"},
        }

        res = descrever_tela(alvo="janela_ativa", detalhe="resumo")
        assert res["status"] == "success"
        assert "Chrome" in res["message"]
        assert res["window_title"] == "Google Chrome"


def test_ler_conteudo_tela_mock():
    """Verify ler_conteudo_tela extracts and returns text."""
    with patch("src.tools.screen_perception.screen_perceiver.analyze_visual_content") as mock_analyze:
        mock_analyze.return_value = {
            "status": "success",
            "text": "Título: Relatório Financeiro. Receita: R$ 50.000.",
            "window": {"title": "Relatório.docx"},
        }

        res = ler_conteudo_tela(alvo="janela_ativa")
        assert res["status"] == "success"
        assert "Relatório Financeiro" in res["message"]


def test_localizar_e_clicar_high_impact_safety_gate():
    """Verify destructive actions require explicit prior confirmation."""
    destructive_queries = [
        "botão de excluir arquivo permanente",
        "deletar banco de dados",
        "apagar mensagens",
        "finalizar compra no carrinho",
        "pagar fatura",
    ]
    for q in destructive_queries:
        res = localizar_e_clicar_elemento(descricao_elemento=q, confirmacao_previa=False)
        assert res["status"] == "confirmation_required"
        assert "impacto significativo" in res["message"].lower() or "segurança" in res["message"].lower()


def test_localizar_e_clicar_with_confirmation_and_mock():
    """Verify clicking executes mouse move and click when coordinates are found."""
    with patch("src.tools.screen_perception.screen_perceiver.locate_element_coordinates") as mock_locate, \
         patch("src.tools.screen_perception.pyautogui.moveTo") as mock_move, \
         patch("src.tools.screen_perception.pyautogui.click") as mock_click:

        mock_locate.return_value = {
            "status": "success",
            "elemento": "botão salvar",
            "screen_x": 500,
            "screen_y": 300,
            "window_title": "Word",
        }

        res = localizar_e_clicar_elemento(descricao_elemento="botão salvar", confirmacao_previa=True)
        assert res["status"] == "success"
        assert "clicado com sucesso" in res["message"]
        mock_move.assert_called_once_with(500, 300, duration=0.25)
        mock_click.assert_called_once_with(500, 300)


def test_preencher_campo_na_tela_mock():
    """Verify focusing field and pasting text via clipboard."""
    with patch("src.tools.screen_perception.screen_perceiver.locate_element_coordinates") as mock_locate, \
         patch("src.tools.screen_perception.pyautogui.moveTo"), \
         patch("src.tools.screen_perception.pyautogui.click"), \
         patch("src.tools.screen_perception.pyautogui.hotkey") as mock_hotkey, \
         patch("src.tools.screen_perception.pyperclip.copy") as mock_copy:

        mock_locate.return_value = {
            "status": "success",
            "elemento": "campo de pesquisa",
            "screen_x": 400,
            "screen_y": 200,
        }

        res = preencher_campo_na_tela(descricao_campo="campo de pesquisa", texto="Relatório de Otimização")
        assert res["status"] == "success"
        mock_copy.assert_called_once_with("Relatório de Otimização")
        mock_hotkey.assert_called_once_with("ctrl", "v")


def test_rolar_tela_actions():
    """Verify scrolling up and down with pyautogui."""
    with patch("src.tools.screen_perception.pyautogui.scroll") as mock_scroll:
        res_down = rolar_tela(direcao="baixo", quantidade=3)
        assert res_down["status"] == "success"
        mock_scroll.assert_called_with(-360)

        res_up = rolar_tela(direcao="cima", quantidade=2)
        assert res_up["status"] == "success"
        mock_scroll.assert_called_with(240)


def test_declarations_and_dispatchers():
    """Verify all 5 tools are declared, included in ALL_ATON_TOOLS, and routed correctly."""
    assert len(SCREEN_PERCEPTION_FUNCTION_DECLARATIONS) == 5
    names = [d["name"] for d in SCREEN_PERCEPTION_FUNCTION_DECLARATIONS]
    assert "descrever_tela" in names
    assert "ler_conteudo_tela" in names
    assert "localizar_e_clicar_elemento" in names
    assert "preencher_campo_na_tela" in names
    assert "rolar_tela" in names

    all_names = [t["name"] for t in ALL_ATON_TOOLS if "name" in t]
    for n in names:
        assert n in all_names

    with patch("src.tools.screen_perception.rolar_tela") as mock_rolar:
        mock_rolar.return_value = {"status": "success", "message": "rolou"}
        
        # Test tool dispatcher directly
        res_direct = dispatch_screen_perception_tool("rolar_tela", {"direcao": "baixo", "quantidade": 2})
        assert res_direct["status"] == "success"

        # Test unified tools dispatcher
        res_unified = dispatch_tool("rolar_tela", {"direcao": "baixo", "quantidade": 2})
        assert res_unified["status"] == "success"
