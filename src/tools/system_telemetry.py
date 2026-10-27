"""System Telemetry Tool for Aton.

Provides real-time system diagnostic and resource monitoring on Windows
including CPU usage, RAM consumption, battery health, and disk space.
"""

import logging
from typing import Any, Dict, Optional
import psutil

logger = logging.getLogger(__name__)


def get_system_telemetry(metric: str = "all") -> Dict[str, Any]:
    """Retrieve diagnostic telemetry metrics for the local PC.

    Args:
        metric: Metric to query ('all', 'battery', 'cpu', 'memory', 'disk').

    Returns:
        Dict with status, conversational message in Portuguese, and metrics data.
    """
    metric = (metric or "all").lower().strip()
    data: Dict[str, Any] = {}
    narrative_parts = []

    try:
        # Battery Telemetry
        if metric in ("all", "battery", "bateria"):
            battery = psutil.sensors_battery()
            if battery is None:
                data["battery"] = {
                    "has_battery": False,
                    "description": "Conectado diretamente à energia (computador de mesa ou sem bateria móvel).",
                }
                if metric in ("battery", "bateria"):
                    narrative_parts.append(
                        "O computador está conectado diretamente à tomada sem bateria detectada."
                    )
            else:
                plugged_str = "carregando" if battery.power_plugged else "na bateria"
                data["battery"] = {
                    "has_battery": True,
                    "percent": round(battery.percent, 1),
                    "power_plugged": battery.power_plugged,
                    "secs_left": battery.secsleft if battery.secsleft > 0 else None,
                }
                time_str = ""
                if not battery.power_plugged and battery.secsleft > 0:
                    hours = battery.secsleft // 3600
                    minutes = (battery.secsleft % 3600) // 60
                    time_str = f", com autonomia estimada de {hours} horas e {minutes} minutos"
                narrative_parts.append(
                    f"A bateria está em {round(battery.percent)}% ({plugged_str}{time_str})"
                )

        # CPU Telemetry
        if metric in ("all", "cpu", "processador"):
            cpu_percent = psutil.cpu_percent(interval=0.1)
            cpu_count = psutil.cpu_count(logical=True)
            data["cpu"] = {
                "percent": cpu_percent,
                "logical_cores": cpu_count,
            }
            narrative_parts.append(
                f"Uso do processador em {cpu_percent}% com {cpu_count} núcleos lógicos"
            )

        # Memory Telemetry
        if metric in ("all", "memory", "ram", "memoria"):
            mem = psutil.virtual_memory()
            total_gb = round(mem.total / (1024**3), 1)
            used_gb = round(mem.used / (1024**3), 1)
            avail_gb = round(mem.available / (1024**3), 1)
            data["memory"] = {
                "percent": mem.percent,
                "total_gb": total_gb,
                "used_gb": used_gb,
                "available_gb": avail_gb,
            }
            narrative_parts.append(
                f"Memória RAM em {mem.percent}% ({used_gb} GB usados de {total_gb} GB, restando {avail_gb} GB livres)"
            )

        # Disk Space Telemetry (Drive C:)
        if metric in ("all", "disk", "disco", "armazenamento"):
            disk = psutil.disk_usage("C:\\")
            d_total_gb = round(disk.total / (1024**3), 1)
            d_free_gb = round(disk.free / (1024**3), 1)
            data["disk"] = {
                "percent": disk.percent,
                "total_gb": d_total_gb,
                "free_gb": d_free_gb,
            }
            narrative_parts.append(
                f"Disco C: {d_free_gb} GB livres de um total de {d_total_gb} GB ({disk.percent}% ocupado)"
            )

        message = (
            "Status do sistema: " + "; ".join(narrative_parts) + "."
            if narrative_parts
            else "Nenhuma métrica correspondente encontrada."
        )

        logger.info(f"System telemetry queried (metric='{metric}'): {message}")
        return {
            "status": "success",
            "message": message,
            "metric": metric,
            "data": data,
        }

    except Exception as e:
        logger.error(f"Error obtaining system telemetry: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"Não foi possível obter a telemetria do sistema: {str(e)}",
        }


# Declarations for Gemini Live API
SYSTEM_TELEMETRY_FUNCTION_DECLARATIONS = [
    {
        "name": "get_system_telemetry",
        "description": "Obtém informações de diagnóstico e telemetria do PC do usuário em tempo real (bateria, CPU, memória RAM e espaço em disco livre).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "metric": {
                    "type": "STRING",
                    "description": "Métrica específica desejada: 'all' (resumo completo), 'battery' (nível e carregamento de bateria), 'cpu' (uso do processador), 'memory' (memória RAM) ou 'disk' (espaço no disco C). Padrão é 'all'.",
                }
            },
        },
    }
]


def dispatch_telemetry_tool(tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatch telemetry tool calls."""
    if tool_name == "get_system_telemetry":
        metric = tool_args.get("metric", "all")
        return get_system_telemetry(metric=metric)
    return {
        "status": "error",
        "message": f"Ferramenta de telemetria desconhecida '{tool_name}'.",
    }
