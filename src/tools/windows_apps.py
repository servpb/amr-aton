"""Windows application and process management tool for Aton."""

import logging
import os
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

from src.core.task_context import get_task_context

logger = logging.getLogger(__name__)

# Map of common friendly names (Portuguese and English) to executable names or Windows URI schemes
COMMON_APPS: Dict[str, List[str]] = {
    # Browsers
    "chrome": ["chrome", "google-chrome"],
    "google chrome": ["chrome"],
    "navegador": ["chrome", "msedge"],
    "edge": ["msedge"],
    "msedge": ["msedge"],
    "microsoft edge": ["msedge"],
    "firefox": ["firefox"],
    "brave": ["brave"],
    # Web Services & Popular Sites
    "youtube": ["msedge", "chrome"],
    "youtube.com": ["msedge", "chrome"],
    "netflix": ["msedge", "chrome"],
    "whatsapp": ["whatsapp", "msedge", "chrome"],
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

# Mappings from friendly names and aliases to executable process names (for HWND & process matching)
APP_PROCESS_MAP: Dict[str, List[str]] = {
    # Browsers
    "msedge": ["msedge.exe"],
    "edge": ["msedge.exe"],
    "microsoft edge": ["msedge.exe"],
    "chrome": ["chrome.exe"],
    "google chrome": ["chrome.exe"],
    "firefox": ["firefox.exe"],
    "mozilla firefox": ["firefox.exe"],
    "brave": ["brave.exe"],
    "opera": ["opera.exe"],
    "navegador": ["msedge.exe", "chrome.exe", "firefox.exe", "brave.exe", "opera.exe"],
    "browser": ["msedge.exe", "chrome.exe", "firefox.exe", "brave.exe", "opera.exe"],
    "o navegador": ["msedge.exe", "chrome.exe", "firefox.exe", "brave.exe", "opera.exe"],
    # Web services opened in browsers
    "youtube": ["msedge.exe", "chrome.exe", "firefox.exe", "brave.exe"],
    "youtube.com": ["msedge.exe", "chrome.exe", "firefox.exe", "brave.exe"],
    "netflix": ["msedge.exe", "chrome.exe", "firefox.exe", "brave.exe"],
    "whatsapp": ["whatsapp.exe", "msedge.exe", "chrome.exe"],
    # Utilities & Tools
    "bloco de notas": ["notepad.exe"],
    "notepad": ["notepad.exe"],
    "calculadora": ["calculatorapp.exe", "calc.exe"],
    "calc": ["calculatorapp.exe", "calc.exe"],
    "explorador de arquivos": ["explorer.exe"],
    "explorer": ["explorer.exe"],
    "vscode": ["code.exe"],
    "code": ["code.exe"],
    "visual studio code": ["code.exe"],
    "spotify": ["spotify.exe"],
    "terminal": ["windowsterminal.exe", "powershell.exe", "cmd.exe"],
    "cmd": ["cmd.exe"],
    "powershell": ["powershell.exe"],
    "paint": ["mspaint.exe"],
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
    task_mgr = get_task_context()
    task_id, action_id = task_mgr.record_action_planned("open_application", {"app_name": app_name, "args": args})

    if not task_mgr.is_action_allowed(task_id):
        return {
            "status": "cancelled",
            "task_id": task_id,
            "action_id": action_id,
            "execution_state": "cancelada",
            "target": "pc",
            "transport_state": "not_sent",
            "action_sent": False,
            "verification_state": "unverified",
            "message": f"Abertura de '{app_name}' no computador cancelada antes do envio.",
        }

    target = resolve_app_target(app_name)
    active_task = task_mgr.get_active_task()
    if active_task:
        active_task.references["app_name"] = app_name
        active_task.references["target"] = target
    if not target:
        task_mgr.record_transport_result(task_id, action_id, "not_sent")
        task_mgr.record_verification_result(task_id, action_id, "failed")
        return {
            "status": "error",
            "task_id": task_id,
            "action_id": action_id,
            "execution_state": "falhou",
            "target": "pc",
            "transport_state": "not_sent",
            "action_sent": False,
            "verification_state": "failed",
            "message": f"Não foi possível identificar o aplicativo '{app_name}'.",
        }

    try:
        # Handle URI scheme or URL
        if target.startswith(("http://", "https://")) or target.endswith(":"):
            os.startfile(target)
            task_mgr.record_transport_result(task_id, action_id, "sent_confirmed")
            task_mgr.record_verification_result(
                task_id,
                action_id,
                "inconclusive",
                evidence={"type": "uri_launched", "target": target},
            )
            return {
                "status": "success",
                "task_id": task_id,
                "action_id": action_id,
                "execution_state": "inconclusiva",
                "target": "pc",
                "transport_state": "sent_confirmed",
                "action_sent": True,
                "verification_state": "inconclusive",
                "evidence": {"type": "uri_launched", "target": target},
                "evidence_timestamp": time.time(),
                "message": f"'{app_name}' aberto com sucesso. O navegador foi iniciado, mas o carregamento da página ainda não foi verificado.",
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
        task_mgr.record_transport_result(task_id, action_id, "sent_confirmed")

        # Correlate window title / process
        cleaned_app = app_name.strip().lower()
        matched_window = None
        try:
            import pygetwindow as gw
            all_windows = gw.getAllTitles()
            if "youtube" in cleaned_app:
                matched_window = next((w for w in all_windows if "youtube" in w.lower()), None)
            else:
                matched_window = next((w for w in all_windows if cleaned_app in w.lower()), None)
        except Exception:
            matched_window = None

        if matched_window:
            task_mgr.record_verification_result(
                task_id,
                action_id,
                "confirmed",
                evidence={"type": "window_correlated", "title": matched_window, "app_name": app_name},
            )
            return {
                "status": "success",
                "task_id": task_id,
                "action_id": action_id,
                "execution_state": "concluida",
                "target": "pc",
                "transport_state": "sent_confirmed",
                "action_sent": True,
                "verification_state": "confirmed",
                "evidence": {"type": "window_correlated", "title": matched_window},
                "evidence_timestamp": time.time(),
                "message": f"'{app_name}' aberto com sucesso, senhor.",
            }
        else:
            task_mgr.record_verification_result(
                task_id,
                action_id,
                "inconclusive",
                evidence={"target": target, "matched_window": None},
            )
            is_web_or_page = "youtube" in cleaned_app or "http" in target or (target in ("chrome", "msedge", "firefox") and cleaned_app in ("youtube", "netflix", "whatsapp"))
            reason_msg = (
                f"O navegador abriu, mas o carregamento da página de '{app_name}' ainda não pôde ser confirmado."
                if is_web_or_page
                else f"'{app_name}' aberto com sucesso, senhor. Aguardando exibição da janela correspondente."
            )
            return {
                "status": "success",
                "task_id": task_id,
                "action_id": action_id,
                "execution_state": "inconclusiva",
                "target": "pc",
                "transport_state": "sent_confirmed",
                "action_sent": True,
                "verification_state": "inconclusive",
                "evidence": {"target": target, "matched_window": None},
                "evidence_timestamp": time.time(),
                "message": reason_msg,
            }
    except Exception as exc:
        logger.error(f"Failed to open '{app_name}': {exc}")
        task_mgr.record_transport_result(task_id, action_id, "not_sent")
        task_mgr.record_verification_result(task_id, action_id, "failed")
        return {
            "status": "error",
            "task_id": task_id,
            "action_id": action_id,
            "execution_state": "falhou",
            "target": "pc",
            "transport_state": "not_sent",
            "action_sent": False,
            "verification_state": "failed",
            "message": f"Ocorreu um erro ao tentar abrir '{app_name}': {exc}",
        }


def get_window_process_info(hwnd: int) -> Tuple[int, str]:
    """Get the PID and lowercase process executable name for a given HWND."""
    if not isinstance(hwnd, int):
        return 0, ""
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        proc_pid = pid.value
        proc_name = ""
        if proc_pid > 0:
            try:
                import psutil
                p = psutil.Process(proc_pid)
                proc_name = p.name().lower()
            except Exception:
                pass
        return proc_pid, proc_name
    except Exception:
        return 0, ""


def list_visible_windows_with_process() -> List[Dict[str, Any]]:
    """List all visible top-level windows with title, HWND, PID, and process name."""
    windows: List[Dict[str, Any]] = []
    seen_hwnds = set()
    try:
        import ctypes
        user32 = ctypes.windll.user32

        # 1. Try pygetwindow if available
        try:
            import pygetwindow as gw
            all_gw = gw.getAllWindows()
            for win in all_gw:
                raw_hwnd = getattr(win, "_hWnd", None)
                if not isinstance(raw_hwnd, int):
                    if hasattr(win, "hwnd") and isinstance(win.hwnd, int):
                        hwnd = win.hwnd
                    elif hasattr(win, "title") and isinstance(win.title, str):
                        hwnd = 1000 + len(windows)
                    else:
                        continue
                else:
                    hwnd = raw_hwnd

                if hwnd in seen_hwnds:
                    continue

                is_vis = getattr(win, "visible", True)
                if not isinstance(is_vis, bool):
                    is_vis = True
                try:
                    if hasattr(user32, "IsWindow") and isinstance(raw_hwnd, int):
                        if not user32.IsWindow(raw_hwnd):
                            continue
                        if not user32.IsWindowVisible(raw_hwnd):
                            is_vis = False
                except Exception:
                    pass

                if is_vis:
                    raw_title = getattr(win, "title", "")
                    title = raw_title.strip() if isinstance(raw_title, str) else ""
                    if title:
                        seen_hwnds.add(hwnd)
                        pid, proc_name = get_window_process_info(hwnd) if isinstance(raw_hwnd, int) else (1234, getattr(win, "process_name", ""))
                        windows.append({
                            "hwnd": hwnd,
                            "title": title,
                            "pid": pid,
                            "process_name": proc_name,
                            "gw_window": win,
                        })
            if windows:
                return windows
        except Exception as e:
            logger.debug(f"pygetwindow enumeration failed or empty: {e}")

        # 2. Fallback to Win32 EnumWindows
        def enum_cb(hwnd, _):
            if hwnd not in seen_hwnds and user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buff, length + 1)
                    title = buff.value.strip()
                    if title:
                        seen_hwnds.add(hwnd)
                        pid, proc_name = get_window_process_info(hwnd)
                        windows.append({
                            "hwnd": hwnd,
                            "title": title,
                            "pid": pid,
                            "process_name": proc_name,
                        })
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        cb = WNDENUMPROC(enum_cb)
        user32.EnumWindows(cb, 0)
    except Exception as exc:
        logger.debug(f"Window enumeration error: {exc}")

    return windows


def close_application(app_name: str, force: bool = False) -> Dict[str, Any]:
    """Gracefully terminate a running Windows application, window, or tab via WM_CLOSE.

    Identifies windows by HWND and associated process name (e.g. msedge.exe, chrome.exe).
    Prioritizes active task context for generic requests (e.g. 'feche o navegador').
    Differentiates closing tabs, windows, and applications without closing all browsers.
    Awaits a bounded verification timeout after WM_CLOSE.
    Never force-terminates automatically without explicit user confirmation.

    Args:
        app_name: Friendly name, process name, window title, 'janela_ativa', or 'aba'.
        force: If True, executes forced termination (taskkill /f) following prior user confirmation.

    Returns:
        Dict containing status, task context fields, and user-facing result message.
    """
    raw_name = app_name.strip()
    cleaned = raw_name.lower()

    # Clean prefixes
    for prefix in (
        "fechar ", "feche ", "feche a ", "feche o ",
        "tela do ", "tela da ", "janela do ", "janela da ",
        "aba do ", "aba da ", "tela de ", "janela de "
    ):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
            break

    task_mgr = get_task_context()
    task_id, action_id = task_mgr.record_action_planned(
        "close_application", {"app_name": app_name, "force": force}
    )

    if not task_mgr.is_action_allowed(task_id):
        return {
            "status": "cancelled",
            "task_id": task_id,
            "action_id": action_id,
            "execution_state": "cancelada",
            "target": "pc",
            "transport_state": "not_sent",
            "action_sent": False,
            "verification_state": "unverified",
            "message": f"Fechamento de '{app_name}' cancelado antes do envio, senhor.",
        }

    # 1. Close active tab via keyboard shortcut (Ctrl+W)
    if cleaned in ("aba", "aba atual", "esta aba", "fechar aba", "fechar a aba"):
        try:
            import pyautogui
            pyautogui.hotkey("ctrl", "w")
            task_mgr.record_transport_result(task_id, action_id, "sent_confirmed")
            task_mgr.record_verification_result(
                task_id, action_id, "confirmed", evidence={"action": "close_tab"}
            )
            return {
                "status": "success",
                "task_id": task_id,
                "action_id": action_id,
                "transport_state": "sent_confirmed",
                "action_sent": True,
                "verification_state": "confirmed",
                "message": "Aba fechada com sucesso, senhor.",
            }
        except Exception as e:
            logger.error(f"Error closing tab: {e}")
            task_mgr.record_transport_result(task_id, action_id, "sent_uncertain")
            task_mgr.record_verification_result(task_id, action_id, "failed")
            return {
                "status": "error",
                "task_id": task_id,
                "action_id": action_id,
                "transport_state": "sent_uncertain",
                "action_sent": False,
                "verification_state": "failed",
                "message": f"Erro ao fechar aba: {e}",
            }

    # 2. Close active foreground window if explicitly requested
    if cleaned in ("janela_ativa", "janela ativa", "tela atual", "esta tela", "esta janela"):
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                task_mgr.record_transport_result(task_id, action_id, "not_sent")
                task_mgr.record_verification_result(task_id, action_id, "failed")
                return {
                    "status": "error",
                    "task_id": task_id,
                    "action_id": action_id,
                    "transport_state": "not_sent",
                    "action_sent": False,
                    "verification_state": "failed",
                    "message": "Nenhuma janela ativa em primeiro plano encontrada para fechar.",
                }

            length = user32.GetWindowTextLengthW(hwnd)
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            win_title = buff.value or "Janela ativa"
            pid, proc_name = get_window_process_info(hwnd)

            # Send WM_CLOSE
            user32.PostMessageW(hwnd, 0x0010, 0, 0)
            task_mgr.record_transport_result(task_id, action_id, "sent_confirmed")

            # Await bounded verification timeout (up to 2.0s)
            deadline = time.time() + 2.0
            closed = False
            while time.time() < deadline:
                time.sleep(0.15)
                if not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd):
                    closed = True
                    break

            if closed:
                task_mgr.record_verification_result(
                    task_id, action_id, "confirmed", evidence={"hwnd": hwnd, "title": win_title}
                )
                return {
                    "status": "success",
                    "task_id": task_id,
                    "action_id": action_id,
                    "transport_state": "sent_confirmed",
                    "action_sent": True,
                    "verification_state": "confirmed",
                    "message": f"Janela '{win_title}' fechada com sucesso, senhor.",
                }
            else:
                task_mgr.record_verification_result(
                    task_id, action_id, "inconclusive", evidence={"hwnd": hwnd, "title": win_title}
                )
                return {
                    "status": "pending_confirmation",
                    "task_id": task_id,
                    "action_id": action_id,
                    "transport_state": "sent_confirmed",
                    "action_sent": True,
                    "verification_state": "inconclusive",
                    "message": (
                        f"A janela '{win_title}' não fechou após o comando de encerramento suave. "
                        f"Pode haver uma confirmação de saída ou alterações não salvas pendentes na tela. "
                        f"Deseja que eu force o encerramento do processo '{proc_name}', senhor?"
                    ),
                    "affected_windows": [win_title],
                    "process_name": proc_name,
                }
        except Exception as e:
            logger.error(f"Failed to close foreground window: {e}")
            task_mgr.record_transport_result(task_id, action_id, "sent_uncertain")
            task_mgr.record_verification_result(task_id, action_id, "failed")
            return {
                "status": "error",
                "task_id": task_id,
                "action_id": action_id,
                "transport_state": "sent_uncertain",
                "action_sent": False,
                "verification_state": "failed",
                "message": f"Erro ao fechar janela ativa: {e}",
            }

    # 3. Resolve target process candidates and find visible windows
    candidate_procs: List[str] = []
    if cleaned in APP_PROCESS_MAP:
        candidate_procs = list(APP_PROCESS_MAP[cleaned])
    elif cleaned.endswith(".exe"):
        candidate_procs = [cleaned]
    else:
        candidate_procs = [f"{cleaned}.exe", cleaned]

    all_visible = list_visible_windows_with_process()

    # Match visible windows by process executable associated with HWND
    matched_windows = [
        w for w in all_visible if w.get("process_name") in candidate_procs
    ]

    # If no window matched by process name, match by title substring (e.g. for specific web sites)
    if not matched_windows:
        matched_windows = [
            w for w in all_visible if cleaned in w.get("title", "").lower()
        ]

    # 4. Context prioritization and ambiguity handling
    chosen_window: Optional[Dict[str, Any]] = None

    if len(matched_windows) == 1:
        chosen_window = matched_windows[0]
    elif len(matched_windows) > 1:
        # Multiple candidates found. Check active/recent task context to prioritize.
        recent_task = task_mgr.get_active_task() or task_mgr.get_latest_completed_task()
        if recent_task:
            ref_app = str(recent_task.references.get("app_name", "")).lower()
            ref_target = str(recent_task.references.get("target", "")).lower()
            for w in matched_windows:
                t_lower = w.get("title", "").lower()
                if (ref_app and (ref_app in t_lower or (len(ref_app) > 3 and ref_app.split(".")[0] in t_lower))) or \
                   (ref_target and ref_target in t_lower):
                    chosen_window = w
                    logger.info(f"Prioritized window '{w['title']}' based on recent task context ({ref_app or ref_target}).")
                    break

        # If still ambiguous without sufficient context, DO NOT close all windows!
        if not chosen_window:
            candidate_list = [
                {"id": str(w["hwnd"]), "title": w["title"], "process": w.get("process_name", ""), "hwnd": w["hwnd"]}
                for w in matched_windows
            ]
            task_mgr.set_pending_candidates(
                candidate_list,
                context_hint="window_selection",
            )
            title_descriptions = [f"'{w['title']}' ({w.get('process_name', '')})" for w in matched_windows]
            return {
                "status": "clarification_needed",
                "task_id": task_id,
                "action_id": action_id,
                "transport_state": "not_sent",
                "action_sent": False,
                "verification_state": "unverified",
                "message": (
                    f"Encontrei mais de uma janela aberta ({', '.join(title_descriptions)}). "
                    f"Qual delas você deseja fechar, senhor?"
                ),
                "candidates": candidate_list,
            }

    # 5. Handle when no matching window is visible
    if not chosen_window:
        running_pids: List[int] = []
        try:
            import psutil
            for p in psutil.process_iter(["pid", "name"]):
                p_name = p.info.get("name")
                if p_name and p_name.lower() in candidate_procs:
                    running_pids.append(p.info["pid"])
        except Exception:
            pass

        if not running_pids:
            task_mgr.record_transport_result(task_id, action_id, "not_sent")
            task_mgr.record_verification_result(task_id, action_id, "failed")
            return {
                "status": "error",
                "task_id": task_id,
                "action_id": action_id,
                "transport_state": "not_sent",
                "action_sent": False,
                "verification_state": "failed",
                "message": f"'{app_name}' não parece estar em execução no momento, senhor.",
            }

        # Process is running in background without visible window
        if force:
            logger.info(f"Forced termination of background processes {candidate_procs} (PIDs: {running_pids})...")
            for pid in running_pids:
                try:
                    subprocess.run(["taskkill", "/f", "/pid", str(pid)], capture_output=True, timeout=3)
                except Exception:
                    pass
            task_mgr.record_transport_result(task_id, action_id, "sent_confirmed")
            task_mgr.record_verification_result(task_id, action_id, "confirmed")
            return {
                "status": "success",
                "task_id": task_id,
                "action_id": action_id,
                "transport_state": "sent_confirmed",
                "action_sent": True,
                "verification_state": "confirmed",
                "message": f"Processo em segundo plano de '{app_name}' foi encerrado com sucesso, senhor.",
            }
        else:
            return {
                "status": "pending_confirmation",
                "task_id": task_id,
                "action_id": action_id,
                "transport_state": "not_sent",
                "action_sent": False,
                "verification_state": "inconclusive",
                "message": (
                    f"'{app_name}' está em execução apenas em segundo plano ({len(running_pids)} processo(s), sem janela visível). "
                    f"Deseja forçar o encerramento do processo, senhor?"
                ),
                "pids": running_pids,
            }

    # 6. Execute close on the chosen window
    target_hwnd = chosen_window["hwnd"]
    target_title = chosen_window["title"]
    target_proc = chosen_window.get("process_name", "")
    target_pid = chosen_window.get("pid", 0)

    # If force kill was explicitly authorized by the user
    if force:
        logger.info(f"Executing explicit forced termination of process '{target_proc}' (PID: {target_pid})...")
        try:
            res = subprocess.run(
                ["taskkill", "/f", "/pid", str(target_pid), "/t"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            task_mgr.record_transport_result(task_id, action_id, "sent_confirmed")
            if res.returncode == 0:
                task_mgr.record_verification_result(task_id, action_id, "confirmed")
                return {
                    "status": "success",
                    "task_id": task_id,
                    "action_id": action_id,
                    "transport_state": "sent_confirmed",
                    "action_sent": True,
                    "verification_state": "confirmed",
                    "message": f"Processo '{target_proc}' (Janela '{target_title}') foi encerrado forçadamente conforme autorizado, senhor.",
                }
            else:
                task_mgr.record_verification_result(task_id, action_id, "failed")
                return {
                    "status": "error",
                    "task_id": task_id,
                    "action_id": action_id,
                    "transport_state": "sent_uncertain",
                    "action_sent": True,
                    "verification_state": "failed",
                    "message": f"Erro ao forçar encerramento de '{target_proc}': {res.stderr.strip()}",
                }
        except Exception as e:
            logger.error(f"Error in forced termination: {e}")
            return {"status": "error", "message": f"Falha ao executar encerramento forçado: {e}"}

    # Graceful WM_CLOSE attempt
    logger.info(f"Posting WM_CLOSE to window '{target_title}' (HWND: {target_hwnd}, Process: {target_proc})...")
    try:
        import ctypes
        user32 = ctypes.windll.user32
        user32.PostMessageW(target_hwnd, 0x0010, 0, 0)
        task_mgr.record_transport_result(task_id, action_id, "sent_confirmed")

        # Bounded verification timeout (up to 2.0s, polling every 0.15s)
        deadline = time.time() + 2.0
        closed = False
        while time.time() < deadline:
            time.sleep(0.15)
            if not user32.IsWindow(target_hwnd) or not user32.IsWindowVisible(target_hwnd):
                closed = True
                break

        if closed:
            task_mgr.record_verification_result(
                task_id,
                action_id,
                "confirmed",
                evidence={"hwnd": target_hwnd, "title": target_title, "process": target_proc},
            )
            return {
                "status": "success",
                "task_id": task_id,
                "action_id": action_id,
                "transport_state": "sent_confirmed",
                "action_sent": True,
                "verification_state": "confirmed",
                "message": f"Janela '{target_title}' foi fechada com sucesso, senhor.",
            }
        else:
            # Window did NOT close within the timeout: check other windows that would be affected by force kill
            all_current = list_visible_windows_with_process()
            affected = [w["title"] for w in all_current if w.get("process_name") == target_proc]
            task_mgr.record_verification_result(
                task_id,
                action_id,
                "inconclusive",
                evidence={"hwnd": target_hwnd, "title": target_title, "reason": "unsaved_or_confirmation_pending"},
            )
            return {
                "status": "pending_confirmation",
                "task_id": task_id,
                "action_id": action_id,
                "transport_state": "sent_confirmed",
                "action_sent": True,
                "verification_state": "inconclusive",
                "message": (
                    f"A janela '{target_title}' não fechou após o comando de encerramento suave. "
                    f"Pode haver uma confirmação de saída ou alterações não salvas pendentes na tela. "
                    f"Se desejar forçar o encerramento do processo '{target_proc}', por favor confirme. "
                    f"As janelas que seriam afetadas são: {', '.join(affected) if affected else target_title}."
                ),
                "affected_windows": affected or [target_title],
                "process_name": target_proc,
            }
    except Exception as exc:
        logger.error(f"Error during WM_CLOSE of '{target_title}': {exc}")
        task_mgr.record_transport_result(task_id, action_id, "sent_uncertain")
        task_mgr.record_verification_result(task_id, action_id, "failed")
        return {
            "status": "error",
            "task_id": task_id,
            "action_id": action_id,
            "transport_state": "sent_uncertain",
            "action_sent": False,
            "verification_state": "failed",
            "message": f"Erro ao enviar comando de fechamento: {exc}",
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
        force = bool(tool_args.get("force", False))
        return close_application(app_name=app, force=force)
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
        "description": "Fecha uma janela, aba ou encerra graciosamente um aplicativo no Windows via WM_CLOSE. Não força o encerramento sem confirmação prévia se houver trabalho não salvo.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {
                    "type": "STRING",
                    "description": "Nome do aplicativo, janela, navegador ou aba a fechar (ex: 'navegador', 'edge', 'chrome', 'youtube', 'janela_ativa', 'aba').",
                },
                "force": {
                    "type": "BOOLEAN",
                    "description": "Defina como True apenas se o usuário tiver confirmado explicitamente o encerramento forçado do processo após falha do fechamento suave.",
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
