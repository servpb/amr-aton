"""Task status inspection, choice resolution, and cancellation tools for Aton."""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from src.core.task_context import get_task_context

logger = logging.getLogger(__name__)

TASK_TOOLS_DECLARATIONS = [
    {
        "name": "consultar_status_tarefa",
        "description": "Consulta o andamento, última evidência ou estado atual da tarefa em execução no computador ou Fire Stick. Use quando o senhor perguntar 'Ele abriu?', 'O que você está fazendo?', 'Deu certo?' ou 'Está tocando?'.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "verificar_ao_vivo": {
                    "type": "BOOLEAN",
                    "description": "Se verdadeiro, realiza uma leitura rápida do dispositivo/computador no momento para confirmar a presença atual sem repetir a ação física.",
                },
                "pergunta": {
                    "type": "STRING",
                    "description": "Pergunta ou dúvida do senhor sobre a tarefa (ex: 'ele abriu?', 'está tocando?').",
                },
            },
        },
    },
    {
        "name": "selecionar_opcao_pendente",
        "description": "Resolve e executa uma escolha feita pelo senhor a partir de opções apresentadas anteriormente na tarefa (ex: 'a segunda', 'a primeira', 'número 2', 'a terceira').",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "escolha": {
                    "type": "STRING",
                    "description": "Identificador ordinal falado pelo senhor, como 'a segunda', 'a primeira', 'opção 3', 'número 1'.",
                },
            },
            "required": ["escolha"],
        },
    },
    {
        "name": "cancelar_tarefa_atual",
        "description": "Cancela a tarefa ativa em andamento no Aton, impedindo etapas físicas subsequentes e informando honestamente se algum comando já havia sido enviado.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "motivo": {
                    "type": "STRING",
                    "description": "Motivo do cancelamento (opcional).",
                },
            },
        },
    },
]


def consultar_status_tarefa(
    verificar_ao_vivo: bool = False,
    pergunta: str = "",
) -> Dict[str, Any]:
    """Inspect current task status, differentiating historical evidence from live query."""
    mgr = get_task_context()
    task = mgr.get_latest_task_or_completed()

    if not task:
        return {
            "status": "success",
            "task_present": False,
            "message": "Não há nenhuma tarefa em andamento nesta conversa, senhor. A qual aplicativo ou comando você está se referindo?",
        }

    p_norm = pergunta.strip().lower()
    needs_live_check = verificar_ao_vivo or any(
        kw in p_norm for kw in ("abriu", "aberto", "tocando", "agora", "ao vivo", "presente", "está na tela")
    )

    # 1. Live read-only verification without repeating action
    if needs_live_check:
        if task.target == "fire_tv":
            try:
                from src.tools.fire_tv import _get_foreground_package, load_fire_tv_apps
                _, alias_map = load_fire_tv_apps()
                app_name = task.parameters.get("app_name", "").lower()
                expected_pkg = alias_map.get(app_name, "")

                current_pkg = _get_foreground_package()
                if current_pkg and expected_pkg and expected_pkg in current_pkg:
                    return {
                        "status": "success",
                        "task_id": task.task_id,
                        "modo": "verificacao_ao_vivo",
                        "estado": "confirmado_ao_vivo",
                        "message": f"Sim, verifiquei agora e o aplicativo {task.parameters.get('app_name', 'solicitado')} está em primeiro plano no Fire Stick.",
                    }
                elif current_pkg:
                    return {
                        "status": "success",
                        "task_id": task.task_id,
                        "modo": "verificacao_ao_vivo",
                        "estado": "inconclusivo_ao_vivo",
                        "message": f"Verifiquei o Fire Stick agora, mas o aplicativo não está em primeiro plano (o pacote atual é {current_pkg}).",
                    }
            except Exception as exc:
                logger.debug(f"Live check error on Fire TV: {exc}")

        elif task.target == "pc":
            try:
                import pygetwindow as gw
                app_name = task.parameters.get("app_name", "").lower()
                all_titles = [t.lower() for t in gw.getAllTitles() if t.strip()]
                matched = any(app_name in t for t in all_titles) if app_name else False
                if matched:
                    return {
                        "status": "success",
                        "task_id": task.task_id,
                        "modo": "verificacao_ao_vivo",
                        "estado": "confirmado_ao_vivo",
                        "message": f"Sim, verifiquei agora e a janela de '{task.parameters.get('app_name')}' está aberta no computador.",
                    }
                else:
                    return {
                        "status": "success",
                        "task_id": task.task_id,
                        "modo": "verificacao_ao_vivo",
                        "estado": "inconclusivo_ao_vivo",
                        "message": f"Verifiquei o computador agora, mas não encontrei janela aberta correspondente a '{task.parameters.get('app_name')}'.",
                    }
            except Exception as exc:
                logger.debug(f"Live check error on PC: {exc}")

    # 2. Historical evidence report
    time_str = "recentemente"
    if task.evidence_timestamp:
        try:
            dt = datetime.fromtimestamp(task.evidence_timestamp, tz=timezone.utc)
            time_str = dt.strftime("%H:%M:%S UTC")
        except Exception:
            pass

    evidence_desc = ""
    if task.evidence:
        evidence_desc = f" (evidência registrada: {task.evidence})"

    if task.verification_state == "confirmed":
        msg = f"Na última verificação feita às {time_str}, o pedido para '{task.summary}' foi confirmado com sucesso no {task.target_label}."
    elif task.verification_state == "inconclusive":
        msg = f"O comando para '{task.summary}' foi enviado às {time_str}, mas a exibição no {task.target_label} ainda não foi confirmada."
    elif task.is_cancelled:
        msg = f"A tarefa para '{task.summary}' foi cancelada ({task.cancellation_reason or 'a pedido do senhor'})."
    else:
        msg = f"A tarefa para '{task.summary}' está no estado: {task.state}."

    return {
        "status": "success",
        "task_id": task.task_id,
        "modo": "evidencia_historica",
        "estado": task.state,
        "transporte": task.transport_state,
        "verificacao": task.verification_state,
        "horario_evidencia": time_str,
        "evidence": task.evidence,
        "message": msg,
    }


def selecionar_opcao_pendente(escolha: str) -> Dict[str, Any]:
    """Resolve ordinal choice from current task and trigger selection."""
    mgr = get_task_context()
    success, chosen, feedback = mgr.resolve_ordinal_choice(escolha)

    if not success or not chosen:
        return {
            "status": "needs_clarification",
            "message": feedback,
        }

    task = mgr.get_active_task()
    target = (task.target if task else None) or mgr.get_active_target() or "fire_tv"

    # If candidate is a YouTube video
    video_id = chosen.get("id") or chosen.get("video_id")
    title = chosen.get("title", "")

    if video_id:
        if target == "fire_tv":
            from src.tools.fire_tv import play_fire_tv_youtube
            return play_fire_tv_youtube(video_id=video_id, destination="fire_tv")
        else:
            from src.tools.web_browser import play_pc_youtube
            return play_pc_youtube(video_id=video_id, query=title)

    return {
        "status": "success",
        "chosen_item": chosen,
        "message": f"Opção selecionada: '{title}'.",
    }


def cancelar_tarefa_atual(motivo: str = "Cancelado pelo usuário") -> Dict[str, Any]:
    """Cancel the active task and report honest status."""
    mgr = get_task_context()
    return mgr.cancel_active_task(reason=motivo)


def dispatch_task_tool(tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatcher for task context query and choice resolution tools."""
    if tool_name == "consultar_status_tarefa":
        return consultar_status_tarefa(
            verificar_ao_vivo=bool(tool_args.get("verificar_ao_vivo", False)),
            pergunta=str(tool_args.get("pergunta", "")),
        )
    if tool_name == "selecionar_opcao_pendente":
        return selecionar_opcao_pendente(str(tool_args.get("escolha", "")))
    if tool_name == "cancelar_tarefa_atual":
        return cancelar_tarefa_atual(str(tool_args.get("motivo", "Cancelado pelo usuário")))

    return {"status": "error", "message": f"Ferramenta de tarefa '{tool_name}' não reconhecida."}

