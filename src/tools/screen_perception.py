"""Screen Perception & Interface Interaction Tools for Aton.

Provides Gemini Live API tools to inspect the active screen, read documents/forms,
locate interactive controls (buttons, links, fields) via multimodal vision,
execute mouse clicks, clipboard-based typing, and page scrolling.
"""

import logging
import time
from typing import Any, Dict, List, Optional
import pyautogui
import pyperclip

from src.core.screen_perceiver import screen_perceiver

logger = logging.getLogger(__name__)

# Palavras-chave associadas a ações destrutivas ou de alto impacto
HIGH_IMPACT_KEYWORDS = [
    "excluir", "deletar", "apagar", "remover", "formatar",
    "comprar", "pagar", "transferir", "finalizar compra",
    "enviar mensagem", "publicar", "descartar",
]


def descrever_tela(alvo: str = "janela_ativa", detalhe: str = "resumo") -> Dict[str, Any]:
    """Capture screen and describe what is visible in natural Brazilian Portuguese."""
    logger.info(f"Executando descrever_tela (alvo={alvo}, detalhe={detalhe})")

    prompt = (
        "Descreva de forma concisa, executiva e direta o que está aberto e visível nesta tela ou janela. "
        "Mencione o aplicativo, a finalidade do conteúdo, abas ou seções principais. "
        "Responda em linguagem falável natural, sem asteriscos, emojis ou tabelas."
    )
    if detalhe == "detalhado":
        prompt += " Inclua detalhes adicionais sobre botões principais, campos e estado atual da interface."

    res = screen_perceiver.analyze_visual_content(prompt=prompt, target=alvo)

    if res.get("status") == "success":
        win_title = res.get("window", {}).get("title", "")
        message = res.get("text", "")
        return {
            "status": "success",
            "message": message,
            "window_title": win_title,
            "target": alvo,
        }

    return {
        "status": "error",
        "message": res.get("message", "Não foi possível analisar visualmente a tela."),
        "window": res.get("window"),
    }


def ler_conteudo_tela(alvo: str = "janela_ativa", trecho: str = "tudo") -> Dict[str, Any]:
    """Extract and read visible text, articles, or forms from the screen."""
    logger.info(f"Executando ler_conteudo_tela (alvo={alvo}, trecho={trecho})")

    prompt = (
        "Faça a leitura fluida e ordenada do texto visível na interface. "
        "Preserve a ordem de leitura lógica e identifique o conteúdo principal (como artigos, mensagens ou relatórios). "
        "Se o conteúdo for longo, forneça uma leitura estruturada com os pontos centrais. "
        "Evite códigos ou termos técnicos de sistema, focando no conteúdo de leitura do usuário."
    )
    if trecho != "tudo":
        prompt += f" Foque especificamente no trecho ou seção: '{trecho}'."

    res = screen_perceiver.analyze_visual_content(prompt=prompt, target=alvo)

    if res.get("status") == "success":
        return {
            "status": "success",
            "message": res.get("text", ""),
            "window_title": res.get("window", {}).get("title", ""),
        }

    return {
        "status": "error",
        "message": res.get("message", "Não foi possível ler o conteúdo textual da tela."),
        "window": res.get("window"),
    }


def localizar_e_clicar_elemento(
    descricao_elemento: str,
    tipo_clique: str = "simples",
    confirmacao_previa: bool = False,
    alvo: str = "janela_ativa",
) -> Dict[str, Any]:
    """Locate UI element by description using Gemini Vision bounding boxes and click on it."""
    logger.info(f"Executando localizar_e_clicar_elemento ('{descricao_elemento}', tipo={tipo_clique})")

    desc_lower = descricao_elemento.lower()

    # Gate de Segurança para Ações de Alto Impacto
    is_high_impact = any(k in desc_lower for k in HIGH_IMPACT_KEYWORDS)
    if is_high_impact and not confirmacao_previa:
        return {
            "status": "confirmation_required",
            "message": (
                f"Esta é uma ação de impacto significativo ('{descricao_elemento}'). "
                "Por segurança, confirme verbalmente antes de eu executar o clique."
            ),
            "elemento": descricao_elemento,
            "tipo_clique": tipo_clique,
        }

    # Localizar coordenadas exatas do elemento
    loc = screen_perceiver.locate_element_coordinates(element_description=descricao_elemento, target=alvo)

    if loc.get("status") != "success":
        return {
            "status": "not_found",
            "message": f"Não consegui identificar com segurança o elemento '{descricao_elemento}' na tela.",
            "detalhes": loc.get("message"),
        }

    x = loc["screen_x"]
    y = loc["screen_y"]

    try:
        # Mover o cursor suavemente até o elemento
        pyautogui.moveTo(x, y, duration=0.25)
        time.sleep(0.05)

        if tipo_clique == "duplo":
            pyautogui.doubleClick(x, y)
        elif tipo_clique == "direito":
            pyautogui.rightClick(x, y)
        else:
            pyautogui.click(x, y)

        return {
            "status": "success",
            "message": f"Elemento '{loc.get('elemento')}' clicado com sucesso na tela ({x}, {y}).",
            "elemento": loc.get("elemento"),
            "posicao": {"x": x, "y": y},
            "janela": loc.get("window_title"),
        }
    except Exception as e:
        logger.error(f"Erro ao executar clique em ({x}, {y}): {e}")
        return {
            "status": "error",
            "message": f"Falha ao executar o clique no elemento: {e}",
        }


def preencher_campo_na_tela(
    descricao_campo: str,
    texto: str,
    alvo: str = "janela_ativa",
) -> Dict[str, Any]:
    """Locate text input field on screen, click to focus, and type text using clipboard."""
    logger.info(f"Executando preencher_campo_na_tela ('{descricao_campo}')")

    loc = screen_perceiver.locate_element_coordinates(element_description=descricao_campo, target=alvo)

    if loc.get("status") != "success":
        return {
            "status": "not_found",
            "message": f"Não encontrei o campo '{descricao_campo}' para preenchimento.",
        }

    x = loc["screen_x"]
    y = loc["screen_y"]

    try:
        # Clicar no campo para obter foco
        pyautogui.moveTo(x, y, duration=0.25)
        pyautogui.click(x, y)
        time.sleep(0.1)

        # Inserir texto via clipboard para preservar acentos e pontuação em português
        pyperclip.copy(texto)
        pyautogui.hotkey("ctrl", "v")

        return {
            "status": "success",
            "message": f"Campo '{loc.get('elemento')}' focado e preenchido com sucesso.",
            "campo": loc.get("elemento"),
            "texto_inserido": texto,
        }
    except Exception as e:
        logger.error(f"Erro ao preencher campo na tela: {e}")
        return {
            "status": "error",
            "message": f"Falha ao preencher o campo na tela: {e}",
        }


def rolar_tela(direcao: str = "baixo", quantidade: int = 3) -> Dict[str, Any]:
    """Scroll screen up or down."""
    logger.info(f"Executando rolar_tela (direcao={direcao}, quantidade={quantidade})")

    # Cada unidade corresponde a aproximadamente 120 pixels de scroll
    clicks = int(quantidade * 120)
    scroll_amount = -clicks if direcao.lower() == "baixo" else clicks

    try:
        pyautogui.scroll(scroll_amount)
        return {
            "status": "success",
            "message": f"Tela rolada para {direcao} ({quantidade} passos).",
            "direcao": direcao,
            "quantidade": quantidade,
        }
    except Exception as e:
        logger.error(f"Erro ao rolar tela: {e}")
        return {
            "status": "error",
            "message": f"Falha ao rolar a tela: {e}",
        }


# Declarations for Gemini Live API Tool Calling
SCREEN_PERCEPTION_FUNCTION_DECLARATIONS = [
    {
        "name": "descrever_tela",
        "description": "Captura sob demanda a janela ativa ou a tela inteira e descreve de forma executiva e concisa o que está visível (aplicativo, conteúdo, status).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "alvo": {
                    "type": "STRING",
                    "description": "Alvo da captura: 'janela_ativa' (padrão) ou 'fullscreen' (tela cheia).",
                },
                "detalhe": {
                    "type": "STRING",
                    "description": "Nível de detalhamento: 'resumo' (padrão) ou 'detalhado'.",
                },
            },
        },
    },
    {
        "name": "ler_conteudo_tela",
        "description": "Lê e extrai o texto visível da janela ativa ou de um trecho específico de um documento, página web ou formulário aberto.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "alvo": {
                    "type": "STRING",
                    "description": "Alvo da leitura: 'janela_ativa' (padrão) ou 'fullscreen'.",
                },
                "trecho": {
                    "type": "STRING",
                    "description": "Foco da leitura: 'tudo' (padrão) ou nome de uma seção específica.",
                },
            },
        },
    },
    {
        "name": "localizar_e_clicar_elemento",
        "description": "Localiza visualmente um botão, link, menu ou ícone na tela por sua descrição e executa o clique do mouse. Ações de alto impacto (excluir, compras, etc.) exigem confirmação prévia.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "descricao_elemento": {
                    "type": "STRING",
                    "description": "Descrição do elemento a ser clicado (ex: 'botão salvar', 'link de configurações', 'ícone de fechar').",
                },
                "tipo_clique": {
                    "type": "STRING",
                    "description": "Tipo de clique: 'simples' (padrão), 'duplo' ou 'direito'.",
                },
                "confirmacao_previa": {
                    "type": "BOOLEAN",
                    "description": "Definir como true se o usuário já confirmou expressamente a execução da ação de impacto.",
                },
                "alvo": {
                    "type": "STRING",
                    "description": "Alvo: 'janela_ativa' ou 'fullscreen'.",
                },
            },
            "required": ["descricao_elemento"],
        },
    },
    {
        "name": "preencher_campo_na_tela",
        "description": "Localiza visualmente uma caixa de entrada ou campo de busca na tela, clica para obter foco e digita o texto informado preservando acentuação.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "descricao_campo": {
                    "type": "STRING",
                    "description": "Descrição do campo a ser preenchido (ex: 'campo de pesquisa', 'caixa de e-mail').",
                },
                "texto": {
                    "type": "STRING",
                    "description": "Texto a ser inserido no campo.",
                },
                "alvo": {
                    "type": "STRING",
                    "description": "Alvo: 'janela_ativa' ou 'fullscreen'.",
                },
            },
            "required": ["descricao_campo", "texto"],
        },
    },
    {
        "name": "rolar_tela",
        "description": "Rola a página ou documento ativo para cima ou para baixo para permitir leitura e navegação contínua.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "direcao": {
                    "type": "STRING",
                    "description": "Direção da rolagem: 'baixo' (padrão) ou 'cima'.",
                },
                "quantidade": {
                    "type": "INTEGER",
                    "description": "Intensidade da rolagem (1 a 10 passos). Padrão é 3.",
                },
            },
        },
    },
]


def dispatch_screen_perception_tool(tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatch screen perception and interaction tools."""
    if tool_name == "descrever_tela":
        return descrever_tela(
            alvo=tool_args.get("alvo", "janela_ativa"),
            detalhe=tool_args.get("detalhe", "resumo"),
        )
    elif tool_name == "ler_conteudo_tela":
        return ler_conteudo_tela(
            alvo=tool_args.get("alvo", "janela_ativa"),
            trecho=tool_args.get("trecho", "tudo"),
        )
    elif tool_name == "localizar_e_clicar_elemento":
        return localizar_e_clicar_elemento(
            descricao_elemento=tool_args.get("descricao_elemento", ""),
            tipo_clique=tool_args.get("tipo_clique", "simples"),
            confirmacao_previa=bool(tool_args.get("confirmacao_previa", False)),
            alvo=tool_args.get("alvo", "janela_ativa"),
        )
    elif tool_name == "preencher_campo_na_tela":
        return preencher_campo_na_tela(
            descricao_campo=tool_args.get("descricao_campo", ""),
            texto=tool_args.get("texto", ""),
            alvo=tool_args.get("alvo", "janela_ativa"),
        )
    elif tool_name == "rolar_tela":
        return rolar_tela(
            direcao=tool_args.get("direcao", "baixo"),
            quantidade=int(tool_args.get("quantidade", 3)),
        )

    return {
        "status": "error",
        "message": f"Ferramenta de percepção de tela desconhecida: '{tool_name}'.",
    }
