"""
Voice tools for inspecting and configuring Aton's Proactive Calendar Notifications:
- explicar_ultimo_aviso: explains why Aton triggered the most recent proactive alert.
- configurar_avisos_proativos: configures lead minutes and persistent Do-Not-Disturb
  (separate sound vs. visual notification controls).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.core.proactive_calendar import get_proactive_calendar_monitor


def explicar_ultimo_aviso() -> Dict[str, Any]:
    """Return the spoken explanation for the most recent proactive calendar alert."""
    return get_proactive_calendar_monitor().get_last_alert_explanation()


def configurar_avisos_proativos(
    ativado: Optional[bool] = None,
    minutos_antecedencia: Optional[int] = None,
    silenciar_som: Optional[bool] = None,
    bloquear_notificacao_visual: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Update and persist proactive calendar notification settings in SQLite.
    Supports independent control of sound (silenciar_som) and visual tray notifications
    (bloquear_notificacao_visual) so settings survive Aton restarts.
    """
    monitor = get_proactive_calendar_monitor()
    updated = monitor.update_settings(
        enabled=ativado,
        lead_minutes=minutos_antecedencia,
        dnd_mute_sound=silenciar_som,
        dnd_block_visual=bloquear_notificacao_visual,
    )

    if not updated.enabled:
        msg = "Pronto, desativei os avisos proativos automáticos da agenda."
    elif updated.dnd_block_visual and updated.dnd_mute_sound:
        msg = "Pronto, ativei o modo Não Perturbe total: som e notificações visuais da agenda estão bloqueados."
    elif updated.dnd_mute_sound:
        msg = (
            f"Pronto, ativei o modo silencioso para os avisos da agenda ({updated.lead_minutes} minutos antes): "
            "o som está bloqueado, mantendo apenas a notificação visual."
        )
    elif updated.dnd_block_visual:
        msg = (
            f"Pronto, bloqueei as notificações visuais da agenda ({updated.lead_minutes} minutos antes), "
            "mantendo apenas o aviso sonoro."
        )
    else:
        msg = (
            f"Pronto, os avisos proativos da agenda estão ativos para alertar até "
            f"{updated.lead_minutes} minutos antes de cada compromisso."
        )

    return {
        "status": "success",
        "enabled": updated.enabled,
        "lead_minutes": updated.lead_minutes,
        "dnd_mute_sound": updated.dnd_mute_sound,
        "dnd_block_visual": updated.dnd_block_visual,
        "quiet_hours": f"{updated.quiet_start_hour:02d}:00-{updated.quiet_end_hour:02d}:00",
        "message": msg,
    }


PROACTIVE_CALENDAR_DECLARATIONS: List[Dict[str, Any]] = [
    {
        "name": "explicar_ultimo_aviso",
        "description": (
            "Explica o motivo do último aviso proativo automático disparado pelo Aton sobre a agenda. "
            "Use quando o usuário perguntar 'Por que você me avisou isso?', 'Qual foi esse aviso?' ou 'O que apitou agora?'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "configurar_avisos_proativos",
        "description": (
            "Configura os avisos proativos automáticos do Google Agenda (antecedência em minutos e modo Não Perturbe "
            "com controle separado para som e notificação visual), mantendo a configuração salva no banco SQLite mesmo após reiniciar."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "ativado": {
                    "type": "BOOLEAN",
                    "description": "Liga (true) ou desliga (false) o monitoramento proativo da agenda.",
                },
                "minutos_antecedencia": {
                    "type": "INTEGER",
                    "description": "Minutos de antecedência para avisar antes do compromisso (padrão: 15).",
                },
                "silenciar_som": {
                    "type": "BOOLEAN",
                    "description": "Se verdadeiro, bloqueia o bipe sonoro nos avisos proativos (Modo Não Perturbe Sonoro).",
                },
                "bloquear_notificacao_visual": {
                    "type": "BOOLEAN",
                    "description": "Se verdadeiro, bloqueia também a notificação visual na bandeja do Windows.",
                },
            },
            "required": [],
        },
    },
]

PROACTIVE_TOOL_NAMES = {d["name"] for d in PROACTIVE_CALENDAR_DECLARATIONS}


def dispatch_proactive_tool(tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatch proactive calendar tools."""
    args = dict(tool_args or {})
    if tool_name == "explicar_ultimo_aviso":
        return explicar_ultimo_aviso()
    if tool_name == "configurar_avisos_proativos":
        return configurar_avisos_proativos(
            ativado=args.get("ativado"),
            minutos_antecedencia=args.get("minutos_antecedencia"),
            silenciar_som=args.get("silenciar_som"),
            bloquear_notificacao_visual=args.get("bloquear_notificacao_visual"),
        )
    return {"status": "error", "message": f"Ferramenta proativa desconhecida: {tool_name}"}

