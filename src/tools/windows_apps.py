"""Windows application and process management tool for Aton."""

import logging
import os
import shutil
import subprocess
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Map of common friendly names (Portuguese and English) to executable names or Windows URI schemes
COMMON_APPS: Dict[str, List[str]] = {
    # Browsers
    "chrome": ["chrome", "google-chrome"],
    "google chrome": ["chrome"],
    "navegador": ["chrome", "msedge"],
    "edge": ["msedge"],
    "microsoft edge": ["msedge"],
    "firefox": ["firefox"],
    "brave": ["brave"],
    # Utilities
    "bloco de notas": ["notepad"],
    "notepad": ["notepad"],
    "calculadora": ["calc", "calculator:"],
    "calc": ["calc", "calculator:"],
    "explorador de arquivos": ["explorer"],
    "explorer": ["explorer"],
    "meus arquivos": ["explorer"],
    "arquivos": ["explorer"],
    "prompt de comando": ["cmd"],
    "cmd": ["cmd"],
    "terminal": ["wt", "powershell", "cmd"],
    "powershell": ["powershell"],
    "gerenciador de tarefas": ["taskmgr"],
    "task manager": ["taskmgr"],
    "paint": ["mspaint"],
    "configuracoes": ["ms-settings:"],
    "configurações": ["ms-settings:"],
    "settings": ["ms-settings:"],
    # Dev & Media
    "vs code": ["code"],
    "vscode": ["code"],
    "visual studio code": ["code"],
    "spotify": ["spotify"],
}

# Recognized friendly names for running process identification
FRIENDLY_PROCESS_NAMES: Dict[str, str] = {
    "chrome.exe": "Google Chrome",
    "msedge.exe": "Microsoft Edge",
    "firefox.exe": "Mozilla Firefox",
    "brave.exe": "Brave Browser",
    "notepad.exe": "Bloco de Notas",
    "calculatorapp.exe": "Calculadora",
    "calc.exe": "Calculadora",
    "explorer.exe": "Explorador de Arquivos",
    "code.exe": "Visual Studio Code",
    "spotify.exe": "Spotify",
    "taskmgr.exe": "Gerenciador de Tarefas",
    "cmd.exe": "Prompt de Comando",
    "powershell.exe": "PowerShell",
    "windowsterminal.exe": "Windows Terminal",
    "mspaint.exe": "Paint",
}


def resolve_app_target(app_name: str) -> Optional[str]:
    """Resolve a friendly name or command to an executable or URI scheme."""
    cleaned = app_name.strip().lower()

    # Check for direct URL
    if cleaned.startswith(("http://", "https://", "www.")):
        if cleaned.startswith("www."):
            return f"https://{cleaned}"
        return cleaned

    # Check for domain-like requests (e.g. 'youtube.com', 'google.com')
    if "." in cleaned and not cleaned.endswith((".exe", ".bat", ".cmd")):
        return f"https://{cleaned}"

    # Check in aliases
    if cleaned in COMMON_APPS:
        candidates = COMMON_APPS[cleaned]
        for candidate in candidates:
            if candidate.endswith(":"):
                return candidate
            if shutil.which(candidate) is not None:
                return candidate
        # If not found in PATH, return first alias (Windows start might find it)
        return candidates[0]

    # Return as-is if no alias found
    return cleaned


def open_application(app_name: str, args: Optional[str] = None) -> Dict[str, Any]:
    """Open an application, website, or Windows utility.

    Args:
        app_name: Friendly name, executable, or URL.
        args: Optional extra arguments or parameters.

    Returns:
        Dict containing status and user-facing result message.
    """
    logger.info(f"Opening application '{app_name}' (args: {args})...")
    target = resolve_app_target(app_name)
    if not target:
        return {
            "status": "error",
            "message": f"Não foi possível identificar o aplicativo '{app_name}'.",
        }

    try:
        # Handle URI scheme or URL
        if target.startswith(("http://", "https://")) or target.endswith(":"):
            os.startfile(target)
            return {
                "status": "success",
                "message": f"'{app_name}' aberto com sucesso.",
            }

        # Build execution command
        cmd = [target]
        if args:
            cmd.extend(args.split())

        # Launch detached subprocess in background (does not block audio loop)
        subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return {
            "status": "success",
            "message": f"'{app_name}' aberto com sucesso, senhor.",
        }
    except Exception as exc:
        logger.error(f"Failed to open '{app_name}': {exc}")
        return {
            "status": "error",
            "message": f"Ocorreu um erro ao tentar abrir '{app_name}': {exc}",
        }


def close_application(app_name: str) -> Dict[str, Any]:
    """Gracefully terminate a running Windows application by name.

    Args:
        app_name: Friendly name or process name.

    Returns:
        Dict containing status and user-facing result message.
    """
    cleaned = app_name.strip().lower()
    target_exe = None

    if cleaned in COMMON_APPS:
        first_alias = COMMON_APPS[cleaned][0]
        if not first_alias.endswith(":"):
            target_exe = f"{first_alias}.exe" if not first_alias.endswith(".exe") else first_alias
    elif cleaned.endswith(".exe"):
        target_exe = cleaned
    else:
        target_exe = f"{cleaned}.exe"

    if not target_exe:
        return {
            "status": "error",
            "message": f"Não foi possível determinar o processo para fechar '{app_name}'.",
        }

    logger.info(f"Closing application process '{target_exe}'...")
    try:
        # Run taskkill safely
        result = subprocess.run(
            ["taskkill", "/im", target_exe, "/t"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return {
                "status": "success",
                "message": f"'{app_name}' foi encerrado com sucesso, senhor.",
            }
        else:
            return {
                "status": "error",
                "message": f"'{app_name}' não parece estar em execução no momento.",
            }
    except Exception as exc:
        logger.error(f"Error terminating process '{target_exe}': {exc}")
        return {
            "status": "error",
            "message": f"Erro ao fechar '{app_name}': {exc}",
        }


def list_running_applications() -> Dict[str, Any]:
    """List recognizable interactive applications currently running on Windows."""
    logger.info("Listing active Windows applications...")
    try:
        result = subprocess.run(
            ["tasklist", "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return {"status": "error", "message": "Não foi possível listar os processos ativos."}

        active_apps = set()
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(",")
            if parts:
                proc_name = parts[0].replace('"', "").lower()
                if proc_name in FRIENDLY_PROCESS_NAMES:
                    active_apps.add(FRIENDLY_PROCESS_NAMES[proc_name])

        if not active_apps:
            return {
                "status": "success",
                "message": "Nenhum dos aplicativos monitorados está aberto no momento.",
                "apps": [],
            }

        apps_list = sorted(list(active_apps))
        message = f"Aplicativos abertos no momento: {', '.join(apps_list)}."
        return {
            "status": "success",
            "message": message,
            "apps": apps_list,
        }
    except Exception as exc:
        logger.error(f"Error listing running applications: {exc}")
        return {
            "status": "error",
            "message": f"Erro ao consultar aplicativos em execução: {exc}",
        }


def dispatch_tool(tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
    """Route tool calls from Gemini Live to appropriate local Windows functions."""
    if tool_name == "open_application":
        app = tool_args.get("app_name", "")
        args = tool_args.get("args")
        return open_application(app_name=app, args=args)
    elif tool_name == "close_application":
        app = tool_args.get("app_name", "")
        return close_application(app_name=app)
    elif tool_name == "list_running_applications":
        return list_running_applications()
    else:
        return {
            "status": "error",
            "message": f"Ferramenta desconhecida '{tool_name}'.",
        }


# Gemini Live Function Declarations
WINDOWS_APP_FUNCTION_DECLARATIONS = [
    {
        "name": "open_application",
        "description": "Abre um aplicativo, software instalado no computador ou endereço da web no Windows.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {
                    "type": "STRING",
                    "description": "Nome do programa ou site a ser aberto (ex: 'bloco de notas', 'calculadora', 'chrome', 'youtube.com', 'vscode', 'spotify').",
                },
                "args": {
                    "type": "STRING",
                    "description": "Argumentos adicionais ou parâmetros de linha de comando (opcional).",
                },
            },
            "required": ["app_name"],
        },
    },
    {
        "name": "close_application",
        "description": "Fecha um aplicativo ou software atualmente em execução no Windows.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {
                    "type": "STRING",
                    "description": "Nome do aplicativo a fechar (ex: 'bloco de notas', 'chrome', 'calc', 'spotify').",
                },
            },
            "required": ["app_name"],
        },
    },
    {
        "name": "list_running_applications",
        "description": "Consulta os aplicativos e janelas principais que estão abertos no Windows.",
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        },
    },
]
