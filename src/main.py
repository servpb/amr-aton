"""Main entrypoint for running the AMR Assistant on Windows."""

import asyncio
import logging
import signal
import sys

from src.config import settings
from src.core.assistant import AMRAssistant


def setup_logging() -> None:
    """Configure console logging format."""
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def print_banner() -> None:
    """Display startup banner."""
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


async def main() -> None:
    """Async main routine."""
    setup_logging()
    print_banner()

    assistant = AMRAssistant()

    # Background thread to allow waking up Aton by pressing Enter in the console
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
        print("\n[Encerrando Aton com seguranca...]")
        await assistant.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nAton finalizado com sucesso.")
        sys.exit(0)
