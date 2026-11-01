"""Restricted ADB controls for an explicitly configured Fire TV."""

import ipaddress
import json
import logging
from pathlib import Path
import re
import shutil
import subprocess
import urllib.parse
import threading
import time
from typing import Any, Dict, Optional, Tuple

from src.config import settings
from src.core.task_context import get_task_context
from src.core.fire_tv_discovery import (
    get_fire_tv_connection_manager,
    load_confirmed_fire_tv_state,
    normalize_mac,
)

logger = logging.getLogger(__name__)

_lock = threading.Lock()

# Package regex validator: standard Android package format
PACKAGE_REGEX = re.compile(r"^[a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)+$")

# Actions that allow count > 1
REPEATABLE_ACTIONS = {"up", "down", "left", "right", "rewind", "fast_forward"}

# Actions that must have count == 1
SINGLE_ACTIONS = {
    "home", "back", "select", "menu", "play", "pause", "stop", "next", "previous"
}

KEYS = {
    "home": 3,
    "back": 4,
    "up": 19,
    "down": 20,
    "left": 21,
    "right": 22,
    "select": 23,
    "menu": 82,
    "play": 126,
    "pause": 127,
    "stop": 86,
    "next": 87,
    "previous": 88,
    "rewind": 89,
    "fast_forward": 90,
}

DEFAULT_APPS: Dict[str, Dict[str, Any]] = {
    "youtube": {
        "package": "com.amazon.firetv.youtube",
        "aliases": ["youtube", "yt", "you tube"],
    },
    "netflix": {
        "package": "com.netflix.ninja",
        "aliases": ["netflix"],
    },
    "spotify": {
        "package": "com.spotify.tv.android",
        "aliases": ["spotify"],
    },
    "pluto": {
        "package": "tv.pluto.android",
        "aliases": ["pluto", "pluto tv"],
    },
    "unitv": {
        "package": "com.global.unitviptv",
        "aliases": ["unitv", "uni tv"],
    },
    "ibo": {
        "package": "com.newone.ibo",
        "aliases": ["ibo", "ibo player"],
    },
    "downloader": {
        "package": "com.esaba.downloader",
        "aliases": ["downloader"],
    },
    "airscreen": {
        "package": "com.ionitech.airscreen",
        "aliases": ["airscreen", "air screen"],
    },
}

APPS: Dict[str, Dict[str, Any]] = DEFAULT_APPS


def get_registered_apps() -> Dict[str, Dict[str, Any]]:
    """Return dictionary of registered Fire TV apps from JSON config or default fallback."""
    config_file = _get_config_file_path()
    if config_file.is_file():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "apps" in data and isinstance(data["apps"], dict):
                    return data["apps"]
        except Exception as exc:
            logger.warning(f"Error reading apps from {config_file}: {exc}")
    return DEFAULT_APPS


def _get_config_file_path() -> Path:
    """Return Path to external fire_tv_apps.json configuration."""
    project_root = Path(__file__).resolve().parent.parent.parent
    return project_root / "config" / "fire_tv_apps.json"


def load_fire_tv_apps() -> Tuple[Dict[str, str], Dict[str, str]]:
    """Load and validate external application registry and aliases from config/fire_tv_apps.json.

    Returns:
        Tuple of (app_canonical_to_package, alias_to_package).
    """
    config_file = _get_config_file_path()
    raw_apps = DEFAULT_APPS

    if config_file.is_file():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "apps" in data and isinstance(data["apps"], dict):
                    raw_apps = data["apps"]
        except Exception as exc:
            logger.warning(f"Failed to read fire_tv_apps.json ({exc}); falling back to default app definitions.")

    canonical_to_package: Dict[str, str] = {}
    alias_to_package: Dict[str, str] = {}

    for app_name, app_info in raw_apps.items():
        if not isinstance(app_info, dict):
            continue
        pkg = app_info.get("package", "").strip()
        if not pkg or not PACKAGE_REGEX.match(pkg):
            logger.warning(f"Invalid package identifier '{pkg}' for app '{app_name}'; skipping.")
            continue

        norm_app = app_name.strip().lower()
        canonical_to_package[norm_app] = pkg
        alias_to_package[norm_app] = pkg

        aliases = app_info.get("aliases", [])
        if isinstance(aliases, list):
            for alias in aliases:
                norm_alias = str(alias).strip().lower()
                if not norm_alias:
                    continue
                if norm_alias in alias_to_package and alias_to_package[norm_alias] != pkg:
                    logger.warning(
                        f"Alias conflict: '{norm_alias}' mapped to both '{alias_to_package[norm_alias]}' and '{pkg}'."
                    )
                else:
                    alias_to_package[norm_alias] = pkg

    return canonical_to_package, alias_to_package


def _run(arguments, timeout: int = 8):
    """Execute raw ADB command with safe boundaries (no shell, CREATE_NO_WINDOW)."""
    return subprocess.run(
        arguments,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        shell=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def _execute(arguments, is_read_only: bool = False) -> Dict[str, Any]:
    """Connect to the verified Fire Stick, ensure device state, and execute a bounded command.

    Args:
        arguments: Shell arguments list for ADB.
        is_read_only: True if the operation is idempotent/read-only (status, dumpsys, pm path).
    """
    conn_mgr = get_fire_tv_connection_manager()

    adb = settings.fire_tv_adb_path or shutil.which("adb")
    if not adb or (not Path(adb).is_file() and not shutil.which(adb)):
        return {"status": "error", "message": "Configure FIRE_TV_ADB_PATH com o caminho válido do adb.exe."}

    # Pre-validate candidate priority IP if configured to fail fast on invalid/loopback/public IP
    candidate_ip = conn_mgr.get_candidate_priority_ip()
    if isinstance(candidate_ip, str) and candidate_ip.strip():
        try:
            address = ipaddress.IPv4Address(candidate_ip.strip())
            if not address.is_private or address.is_loopback or address.is_unspecified or address.is_multicast:
                return {"status": "error", "message": "O Fire Stick precisa de um endereço IPv4 privado válido da rede local."}
        except ValueError:
            return {"status": "error", "message": "O Fire Stick precisa de um endereço IPv4 privado válido da rede local."}

    # Step 1: Ensure verified IP with identity confirmation (or limited discovery if changed)
    verified_ip, conn_msg = conn_mgr.get_verified_device_ip(runner_fn=_run)
    if not verified_ip:
        return {"status": "error", "message": conn_msg}

    try:
        address = ipaddress.IPv4Address(verified_ip)
        if not address.is_private or address.is_loopback or address.is_unspecified or address.is_multicast:
            return {"status": "error", "message": "O Fire Stick precisa de um endereço IPv4 privado válido da rede local."}
    except ValueError:
        return {"status": "error", "message": "O Fire Stick precisa de um endereço IPv4 privado válido da rede local."}

    serial = f"{verified_ip}:5555"

    try:
        with _lock:
            # Execute bounded command
            result = _run([adb, "-s", serial, "shell", *arguments], timeout=8)

        output = (result.stdout + result.stderr).strip()
        if result.returncode != 0 or any(
            marker in output.lower()
            for marker in (
                "error:",
                "exception",
                "no activities found",
                "monkey aborted",
                "permission denial",
                "device offline",
                "device unauthorized",
            )
        ):
            conn_mgr.invalidate_cache()
            if not is_read_only:
                # Sensitive physical action failed after/during send: do NOT blindly duplicate!
                return {
                    "status": "uncertain",
                    "message": "O comando pode ter sido enviado; não vou repeti-lo automaticamente.",
                }
            return {"status": "error", "message": f"O Fire Stick recusou a execução: {output or 'erro desconhecido'}"}

        return {"status": "success", "output": result.stdout.strip()}

    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        conn_mgr.invalidate_cache()
        if not is_read_only:
            return {
                "status": "uncertain",
                "message": "O comando pode ter sido enviado; não vou repeti-lo automaticamente.",
            }
        return {"status": "error", "message": str(exc)}


def _get_foreground_package() -> Optional[str]:
    """Query currently focused window/package on the Fire Stick without screen capture."""
    res = _execute(["dumpsys", "window", "windows"], is_read_only=True)
    if res.get("status") != "success":
        return None

    # Parse for mCurrentFocus or mFocusedApp
    output = res.get("output", "")
    for line in output.splitlines():
        if "mCurrentFocus" in line or "mFocusedApp" in line:
            # Format typical: Window{... u0 com.amazon.firetv.youtube/...}
            match = re.search(r"([a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)+)", line)
            if match:
                return match.group(1)
    return None


def launch_fire_tv_app(app_name: str) -> Dict[str, Any]:
    """Launch an application on Fire TV and verify foreground display."""
    task_mgr = get_task_context()
    task_id, action_id = task_mgr.record_action_planned("launch_fire_tv_app", {"app_name": app_name})

    if not task_mgr.is_action_allowed(task_id):
        return {
            "status": "cancelled",
            "task_id": task_id,
            "action_id": action_id,
            "execution_state": "cancelada",
            "target": "fire_tv",
            "transport_state": "not_sent",
            "action_sent": False,
            "verification_state": "unverified",
            "confirmed": False,
            "message": f"Abertura de '{app_name}' no Fire Stick cancelada antes do envio.",
        }

    canonical_apps, alias_map = load_fire_tv_apps()
    normalized_input = str(app_name).strip().lower()

    package = alias_map.get(normalized_input)
    if not package:
        task_mgr.record_transport_result(task_id, action_id, "not_sent")
        task_mgr.record_verification_result(task_id, action_id, "failed")
        available = sorted(list(canonical_apps.keys()))
        return {
            "status": "error",
            "task_id": task_id,
            "action_id": action_id,
            "execution_state": "falhou",
            "target": "fire_tv",
            "transport_state": "not_sent",
            "action_sent": False,
            "verification_state": "failed",
            "confirmed": False,
            "message": f"Aplicativo '{app_name}' não cadastrado no Fire Stick. Opções disponíveis: {', '.join(available)}.",
        }

    # 1. Verify package installation via pm path
    installed = _execute(["pm", "path", package], is_read_only=True)
    if installed.get("status") != "success":
        task_mgr.record_transport_result(task_id, action_id, "not_sent")
        task_mgr.record_verification_result(task_id, action_id, "failed")
        return {
            "status": "error",
            "task_id": task_id,
            "action_id": action_id,
            "execution_state": "falhou",
            "target": "fire_tv",
            "transport_state": "not_sent",
            "action_sent": False,
            "verification_state": "failed",
            "confirmed": False,
            "message": installed.get("message", "Falha ao consultar aplicativo."),
        }

    if not installed.get("output", "").startswith("package:"):
        task_mgr.record_transport_result(task_id, action_id, "not_sent")
        task_mgr.record_verification_result(task_id, action_id, "failed")
        return {
            "status": "error",
            "task_id": task_id,
            "action_id": action_id,
            "execution_state": "falhou",
            "target": "fire_tv",
            "transport_state": "not_sent",
            "action_sent": False,
            "verification_state": "failed",
            "confirmed": False,
            "message": f"O aplicativo '{app_name}' ({package}) não está instalado no Fire Stick.",
        }

    # 2. Dispatch launch via monkey
    launch_res = _execute(["monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"])
    if launch_res.get("status") != "success":
        transport_state = "sent_uncertain" if launch_res.get("status") == "uncertain" else "not_sent"
        task_mgr.record_transport_result(task_id, action_id, transport_state)
        task_mgr.record_verification_result(task_id, action_id, "failed")
        return {
            "status": launch_res.get("status", "error"),
            "task_id": task_id,
            "action_id": action_id,
            "execution_state": "falhou" if transport_state == "not_sent" else "inconclusiva",
            "target": "fire_tv",
            "transport_state": transport_state,
            "action_sent": transport_state != "not_sent",
            "verification_state": "failed",
            "confirmed": False,
            "message": f"Falha ao enviar comando de abertura para '{app_name}': {launch_res.get('message')}",
        }

    if "Events injected: 1" not in launch_res.get("output", ""):
        task_mgr.record_transport_result(task_id, action_id, "sent_uncertain")
        task_mgr.record_verification_result(task_id, action_id, "failed")
        return {
            "status": "error",
            "task_id": task_id,
            "action_id": action_id,
            "execution_state": "falhou",
            "target": "fire_tv",
            "transport_state": "sent_uncertain",
            "action_sent": True,
            "verification_state": "failed",
            "confirmed": False,
            "message": f"O comando para abrir '{app_name}' não foi aceito pelo sistema do Fire Stick.",
        }

    task_mgr.record_transport_result(task_id, action_id, "sent_confirmed")

    # 3. Verify foreground window with bounded polling (up to 2.5s)
    confirmed_in_foreground = False
    start_time = time.time()
    current_pkg = None
    while time.time() - start_time < 2.5:
        time.sleep(0.5)
        current_pkg = _get_foreground_package()
        if current_pkg and package in current_pkg:
            confirmed_in_foreground = True
            break

    if confirmed_in_foreground:
        task_mgr.record_verification_result(
            task_id,
            action_id,
            "confirmed",
            evidence={"type": "foreground_package", "package": current_pkg, "app_name": app_name},
        )
        return {
            "status": "success",
            "task_id": task_id,
            "action_id": action_id,
            "execution_state": "concluida",
            "target": "fire_tv",
            "transport_state": "sent_confirmed",
            "action_sent": True,
            "verification_state": "confirmed",
            "confirmed": True,
            "evidence": {"type": "foreground_package", "package": current_pkg},
            "evidence_timestamp": time.time(),
            "message": f"Aplicativo {app_name} aberto e confirmado no Fire Stick.",
        }
    else:
        task_mgr.record_verification_result(
            task_id,
            action_id,
            "inconclusive",
            evidence={"type": "foreground_package", "package": current_pkg},
        )
        return {
            "status": "success",
            "task_id": task_id,
            "action_id": action_id,
            "execution_state": "inconclusiva",
            "target": "fire_tv",
            "transport_state": "sent_confirmed",
            "action_sent": True,
            "verification_state": "inconclusive",
            "confirmed": False,
            "evidence": {"type": "foreground_package", "package": current_pkg},
            "evidence_timestamp": time.time(),
            "message": f"Comando para abrir {app_name} enviado ao Fire Stick, mas a exibição em primeiro plano ainda não foi confirmada pelo sistema.",
        }


def control_fire_tv(action: str, count: int = 1) -> Dict[str, Any]:
    """Execute navigation or media action with optional count bounded between 1 and 10."""
    normalized_action = str(action).strip().lower()
    key = KEYS.get(normalized_action)

    if key is None:
        return {
            "status": "error",
            "message": f"Comando '{action}' não permitido para o Fire Stick. Ações válidas: {', '.join(sorted(KEYS.keys()))}.",
        }

    # Validate count parameter
    try:
        count_int = int(count)
    except (TypeError, ValueError):
        return {"status": "error", "message": "Quantidade inválida. Informe um número inteiro entre 1 e 10."}

    if count_int < 1 or count_int > 10:
        return {"status": "error", "message": "Quantidade fora do limite permitido. Informe um número entre 1 e 10."}

    if count_int > 1 and normalized_action not in REPEATABLE_ACTIONS:
        return {
            "status": "error",
            "message": (
                f"A ação '{normalized_action}' não permite repetição múltipla. "
                "Utilize quantidade 1 para comandos únicos como selecionar, voltar ou início."
            ),
        }

    # Construct bounded keyevent arguments (e.g. input keyevent 22 22 22)
    key_args = [str(key)] * count_int
    result = _execute(["input", "keyevent", *key_args])

    if result.get("status") == "success":
        # Clear semantic messages
        if count_int > 1:
            if normalized_action == "right":
                msg = f"Navegou {count_int} vezes para a direita no Fire Stick."
            elif normalized_action == "left":
                msg = f"Navegou {count_int} vezes para a esquerda no Fire Stick."
            elif normalized_action == "up":
                msg = f"Navegou {count_int} vezes para cima no Fire Stick."
            elif normalized_action == "down":
                msg = f"Navegou {count_int} vezes para baixo no Fire Stick."
            elif normalized_action == "fast_forward":
                msg = f"Avançou a reprodução {count_int} vezes no Fire Stick."
            elif normalized_action == "rewind":
                msg = f"Retrocedeu a reprodução {count_int} vezes no Fire Stick."
            else:
                msg = f"Comando {normalized_action} executado {count_int} vezes no Fire Stick."
        else:
            if normalized_action == "next":
                msg = "Comando próximo conteúdo enviado ao Fire Stick."
            elif normalized_action == "previous":
                msg = "Comando conteúdo anterior enviado ao Fire Stick."
            elif normalized_action == "fast_forward":
                msg = "Avançar reprodução enviado ao Fire Stick."
            elif normalized_action == "rewind":
                msg = "Retroceder reprodução enviado ao Fire Stick."
            else:
                msg = f"Comando {normalized_action} enviado ao Fire Stick; o efeito depende do aplicativo ativo."

        result["message"] = msg
        result["action"] = normalized_action
        result["count"] = count_int

    return result


GENERIC_MUSIC_REGEX = re.compile(
    r"^(?:uma\s+m[uú]sica|m[uú]sicas?|m[uú]sica\s+boa|alguma\s+m[uú]sica|qualquer\s+m[uú]sica)\s+(?:do|da|de)\s+(.+)$",
    re.IGNORECASE,
)


def get_fire_tv_youtube_playback_state() -> Dict[str, Any]:
    """Inspect dumpsys media_session to verify real playback status on Fire TV."""
    res = _execute(["dumpsys", "media_session"], is_read_only=True)
    if res.get("status") != "success":
        return {"is_playing": False, "is_paused": False, "state_code": 0, "title": "", "error": res.get("message")}

    stdout = res.get("output", "")
    is_playing = False
    is_paused = False
    state_code = 0
    title = ""

    if "com.amazon.firetv.youtube" in stdout:
        state_match = re.search(r"package=com\.amazon\.firetv\.youtube[\s\S]*?state=PlaybackState\s*\{\s*state=(\d+)", stdout)
        if not state_match:
            state_match = re.search(r"state=PlaybackState\s*\{\s*state=(\d+)", stdout)
        if state_match:
            try:
                state_code = int(state_match.group(1))
                if state_code == 3:
                    is_playing = True
                elif state_code == 2:
                    is_paused = True
            except ValueError:
                pass

        desc_match = re.search(r"description=([^,\r\n]+)", stdout)
        if desc_match:
            title = desc_match.group(1).strip()
            if title.lower() in ("null", "none"):
                title = ""

    return {
        "is_playing": is_playing,
        "is_paused": is_paused,
        "state_code": state_code,
        "title": title,
    }


def search_fire_tv_youtube(query: str, destination: Optional[str] = "fire_tv") -> Dict[str, Any]:
    """Open YouTube search results on Fire TV without starting playback automatically."""
    cleaned_query = query.strip()
    if not cleaned_query:
        return {"status": "error", "message": "Nenhum termo de pesquisa fornecido."}

    encoded_query = urllib.parse.quote_plus(cleaned_query)
    search_url = f"https://www.youtube.com/results?search_query={encoded_query}"

    cmd = [
        "am", "start",
        "-a", "android.intent.action.VIEW",
        "-d", search_url,
        "-p", "com.amazon.firetv.youtube",
    ]
    exec_res = _execute(cmd)
    if exec_res.get("status") != "success":
        return exec_res

    wait_time = min(max(float(getattr(settings, "fire_tv_app_wait_seconds", 4.0)), 1.0), 6.0)
    confirmed = False
    start_t = time.time()
    while time.time() - start_t < wait_time:
        time.sleep(0.5)
        pkg = _get_foreground_package()
        if pkg and "com.amazon.firetv.youtube" in pkg:
            confirmed = True
            break

    if confirmed:
        return {
            "status": "success",
            "step": "search_opened_in_app",
            "query": cleaned_query,
            "confirmed": True,
            "message": f"Pesquisa por '{cleaned_query}' aberta no YouTube do Fire Stick.",
        }
    else:
        return {
            "status": "success",
            "step": "search_sent",
            "query": cleaned_query,
            "confirmed": False,
            "message": f"Pesquisa por '{cleaned_query}' enviada ao Fire Stick, aguardando inicialização...",
        }


def play_fire_tv_youtube(
    query: Optional[str] = None,
    video_id: Optional[str] = None,
    destination: Optional[str] = "fire_tv",
) -> Dict[str, Any]:
    """Search and launch playback of a specific song or video on Fire TV YouTube with verified state."""
    from src.tools.youtube_search import lookup_youtube_videos

    vid = (video_id or "").strip()
    q = (query or "").strip()

    if not vid and not q:
        return {
            "status": "needs_clarification",
            "message": "Por favor, informe o título da música ou vídeo que o senhor deseja tocar.",
        }

    target_vid = vid
    target_title = q

    if not target_vid:
        generic_match = GENERIC_MUSIC_REGEX.match(q)
        artist_name = generic_match.group(1).strip() if generic_match else None

        candidates = lookup_youtube_videos(q, max_results=3)
        if not candidates:
            return search_fire_tv_youtube(q, destination=destination)

        is_just_artist = bool(artist_name)
        if not is_just_artist:
            for c in candidates:
                if q.lower() == c.get("channel", "").lower():
                    is_just_artist = True
                    break

        if is_just_artist and len(candidates) > 1:
            cand_titles = [f"'{c['title']}'" for c in candidates[:2]]
            task_mgr = get_task_context()
            task_mgr.set_pending_candidates(candidates, context_hint="youtube_music")
            task = task_mgr.get_active_task()
            return {
                "status": "needs_clarification",
                "step": "multiple_candidates",
                "task_id": task.task_id if task else None,
                "execution_state": "aguardando_esclarecimento",
                "query": q,
                "candidates": [c["title"] for c in candidates],
                "message": f"Encontrei opções como {', ou '.join(cand_titles)}. Qual música o senhor prefere tocar, ou posso colocar a primeira?",
            }

        target_vid = candidates[0]["id"]
        target_title = candidates[0]["title"]

    watch_url = f"https://www.youtube.com/watch?v={target_vid}"
    cmd = [
        "am", "start",
        "-a", "android.intent.action.VIEW",
        "-d", watch_url,
        "-p", "com.amazon.firetv.youtube",
    ]
    exec_res = _execute(cmd)
    if exec_res.get("status") != "success":
        return exec_res

    playback_confirmed = False
    start_t = time.time()
    while time.time() - start_t < 3.5:
        time.sleep(0.7)
        state = get_fire_tv_youtube_playback_state()
        if state.get("is_playing"):
            playback_confirmed = True
            break

    if playback_confirmed:
        return {
            "status": "success",
            "step": "playback_confirmed",
            "video_id": target_vid,
            "title": target_title,
            "confirmed": True,
            "message": f"Reprodução confirmada: tocando '{target_title}' no YouTube do Fire Stick.",
        }
    else:
        return {
            "status": "success",
            "step": "video_selected_and_opened",
            "video_id": target_vid,
            "title": target_title,
            "confirmed": False,
            "message": f"Vídeo '{target_title}' escolhido e aberto no Fire Stick. Aguardando início da reprodução...",
        }


def get_fire_tv_status() -> Dict[str, Any]:
    """Check connectivity and model authorization status."""
    result = _execute(["getprop", "ro.product.model"], is_read_only=True)
    if result.get("status") == "success":
        model = result.get("output", "").strip() or "Desconhecido"
        result["message"] = f"Fire Stick conectado e autorizado. Modelo: {model}."
        result["model"] = model
    return result


def dispatch_fire_tv_tool(tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
    """Unified dispatcher for Fire TV tools with automatic session target context recording."""
    try:
        from src.core.target_context import get_target_context
        ctx = get_target_context()
    except Exception:
        ctx = None

    if tool_name == "launch_fire_tv_app":
        res = launch_fire_tv_app(tool_args.get("app_name", ""))
        if res.get("status") == "success" and ctx:
            ctx.set_target("fire_tv")
        return res

    if tool_name == "control_fire_tv":
        res = control_fire_tv(
            action=tool_args.get("action", ""),
            count=tool_args.get("count", 1),
        )
        if res.get("status") == "success" and ctx:
            ctx.set_target("fire_tv")
        return res

    if tool_name == "get_fire_tv_status":
        res = get_fire_tv_status()
        if res.get("status") == "success" and ctx:
            ctx.set_target("fire_tv")
        return res

    if tool_name == "search_fire_tv_youtube":
        res = search_fire_tv_youtube(
            query=tool_args.get("query", ""),
            destination=tool_args.get("destination", "fire_tv"),
        )
        if res.get("status") == "success" and ctx:
            ctx.set_target("fire_tv")
        return res

    if tool_name == "play_fire_tv_youtube":
        res = play_fire_tv_youtube(
            query=tool_args.get("query"),
            video_id=tool_args.get("video_id"),
            destination=tool_args.get("destination", "fire_tv"),
        )
        if res.get("status") == "success" and ctx:
            ctx.set_target("fire_tv")
        return res

    return {"status": "error", "message": f"Ferramenta de Fire Stick '{tool_name}' desconhecida."}


FIRE_TV_FUNCTION_DECLARATIONS = [
    {
        "name": "launch_fire_tv_app",
        "description": "Abre aplicativo no Amazon Fire TV Stick e confirma a exibição em primeiro plano. Use para pedidos de abrir apps no Fire Stick.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {
                    "type": "STRING",
                    "description": "Nome ou apelido do aplicativo (ex: youtube, netflix, spotify, pluto, unitv, ibo, downloader, airscreen).",
                    "enum": list(APPS.keys()),
                },
            },
            "required": ["app_name"],
        },
    },
    {
        "name": "control_fire_tv",
        "description": "Navega e controla reprodução no Fire Stick: início, voltar, direções (cima, baixo, esquerda, direita), selecionar, menu, reproduzir, pausar, avançar reprodução e próximo conteúdo. Aceita quantidade de 1 a 10 para repetição de setas e avanço. Não controla volume nem energia da televisão. Use para pedidos referentes ao Fire Stick.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "enum": list(KEYS),
                    "description": "Ação a executar no Fire Stick: home, back, up, down, left, right, select, menu, play, pause, stop, next, previous, rewind, fast_forward.",
                },
                "count": {
                    "type": "INTEGER",
                    "minimum": 1,
                    "maximum": 10,
                    "description": "Quantidade de repetições (1 a 10), válida apenas para navegação direcional (up, down, left, right) e seek (rewind, fast_forward). Padrão: 1.",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "get_fire_tv_status",
        "description": "Verifica a conexão e autorização do Amazon Fire TV Stick pela rede.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "search_fire_tv_youtube",
        "description": "Pesquisa vídeos ou músicas no aplicativo YouTube do Fire Stick e exibe os resultados na televisão sem iniciar reprodução automaticamente.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": "Termo de pesquisa (ex: 'Roberto Carlos', 'Receitas de bolo').",
                },
                "destination": {
                    "type": "STRING",
                    "enum": ["fire_tv", "pc"],
                    "description": "Destino do comando (padrão: 'fire_tv').",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "play_fire_tv_youtube",
        "description": "Busca e reproduz diretamente uma música ou vídeo específico no YouTube do Fire Stick, com verificação real de reprodução. Para pedidos genéricos sem título da música, solicita esclarecimento antes de tocar.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": "Título da música ou vídeo específico a tocar (ex: 'Como É Grande o Meu Amor por Você do Roberto Carlos').",
                },
                "video_id": {
                    "type": "STRING",
                    "description": "ID oficial de 11 caracteres do vídeo do YouTube (opcional se fornecida query).",
                },
                "destination": {
                    "type": "STRING",
                    "enum": ["fire_tv", "pc"],
                    "description": "Destino do comando (padrão: 'fire_tv').",
                },
            },
        },
    },
]
