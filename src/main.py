"""Main entrypoint for running the AMR Assistant on Windows."""

import asyncio
import logging
import os
from pathlib import Path
import sys

from src.config import settings


def setup_logging() -> None:
    """Configure file and console logging with UTF-8 support (safe for pythonw.exe)."""
    project_root = Path(__file__).resolve().parent.parent
    log_dir = project_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "aton.log"

    handlers: list[logging.Handler] = [
        logging.FileHandler(log_file, encoding="utf-8"),
    ]

    # Only attach StreamHandler if stderr exists and is a valid stream (not pythonw without console)
    if sys.stderr is not None:
        try:
            if hasattr(sys.stderr, "reconfigure"):
                sys.stderr.reconfigure(encoding="utf-8", errors="replace")
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            handlers.append(logging.StreamHandler(sys.stderr))
        except Exception:
            pass

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
        force=True,
    )


def print_banner() -> None:
    """Display startup banner safely (no-op if running under pythonw without stdout)."""
    if sys.stdout is None:
        return
    try:
        print("=" * 60)
        print("         ATON - Assistente Pessoal Inteligente")
        print("=" * 60)
        print(f" [Voz]: {settings.gemini_voice_name}")
        print(f" [Modelo Live]: {settings.gemini_live_model}")
        print(f" [Palavra-Chave]: '{settings.amr_wake_word}'")
        print(f" [Tempo de Conversa]: {settings.conversation_timeout_seconds}s de silencio")
        print("-" * 60)
        print(" >> Diga 'Aton' no microfone OU pressione [ENTER] no teclado!")
        print(" >> Pressione Ctrl + C para encerrar.")
        print("=" * 60)
    except Exception:
        pass


def _has_interactive_stdin() -> bool:
    """Return True if process has an interactive console stdin."""
    if sys.stdin is None:
        return False
    try:
        return sys.stdin.isatty()
    except Exception:
        return False


def _ensure_single_aton_instance() -> None:
    """Terminate any older running `src.main` processes so two Aton voices never speak simultaneously."""
    current_pid = os.getpid()
    parent_pid = os.getppid()
    try:
        import psutil

        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                pid = proc.info.get("pid")
                if not pid or pid in (current_pid, parent_pid):
                    continue
                cmdline = proc.info.get("cmdline") or []
                cmd_str = " ".join(str(part) for part in cmdline).lower()
                if "src.main" in cmd_str or "src\\main.py" in cmd_str or "src/main.py" in cmd_str:
                    logging.getLogger(__name__).info(
                        f"Encerrando instância anterior duplicada do Aton (PID {pid}) para evitar 2 vozes simultâneas."
                    )
                    proc.terminate()
                    try:
                        proc.wait(timeout=2.0)
                    except Exception:
                        proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception as exc:
        logging.getLogger(__name__).debug(f"Single-instance check skipped: {exc}")


async def main() -> None:
    """Async main routine."""
    import time
    t_boot_start = time.perf_counter()

    # Ensure working directory is always project root even when started by Windows Startup
    project_root = Path(__file__).resolve().parent.parent
    os.chdir(project_root)

    setup_logging()
    _ensure_single_aton_instance()
    logging.getLogger(__name__).info("🚀 Processo Aton iniciado. Inicializando presenca e hardware...")
    print_banner()

    # Early start system tray if enabled (gives instant visual feedback <1s in Windows taskbar)
    tray = None
    if settings.system_tray_enabled:
        try:
            from src.integrations.system_tray import AtonSystemTray
            tray = AtonSystemTray(
                hud_url=f"http://localhost:{settings.gateway_port}",
                initial_state="initializing",
                initial_status_text="Inicializando processo e hardware...",
            )
            tray.start()
        except Exception as exc:
            logging.getLogger(__name__).warning(f"Could not initialize system tray early: {exc}")

    from src.core.assistant import AMRAssistant

    assistant = AMRAssistant(tray=tray, t_boot_start=t_boot_start)

    # Attach assistant callbacks to already-running tray
    if tray is not None:
        tray.on_toggle_mute = assistant._on_tray_toggle_mute
        tray.on_request_briefing = assistant._on_tray_request_briefing
        tray.on_exit = assistant._on_tray_exit
        tray.on_wake = assistant._on_manual_trigger
        tray.on_retry_init = assistant._on_tray_retry_init

    # Background thread to allow waking up Aton by pressing Enter in the console
    if _has_interactive_stdin():
        import threading

        def listen_for_keyboard():
            while True:
                try:
                    line = sys.stdin.readline()
                    if not line:
                        break
                    assistant._on_manual_trigger()
                except Exception:
                    break

        keyboard_thread = threading.Thread(target=listen_for_keyboard, daemon=True)
        keyboard_thread.start()

    try:
        await assistant.run()
    except (KeyboardInterrupt, SystemExit):
        if sys.stdout is not None:
            try:
                print("\n[Encerrando Aton com seguranca...]")
            except Exception:
                pass
        await assistant.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)

