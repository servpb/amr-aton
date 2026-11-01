"""Windows System Tray integration for Aton.

Provides a resident presence in the Windows taskbar tray with visual state
indicators (Sleeping, Listening, Speaking, Muted), quick action menus,
and graceful application lifecycle control.
"""

import logging
import threading
import webbrowser
from typing import Callable, Optional
from PIL import Image, ImageDraw, ImageFont
import pystray
from pystray import MenuItem as item

logger = logging.getLogger(__name__)


def generate_tray_icon(
    state: str = "sleeping",
    size: int = 64,
) -> Image.Image:
    """Generate a clean, high-DPI icon image with state-driven colors and monogram."""
    # Palette definition for states
    palette = {
        "initializing": {"fill": (245, 158, 11), "outline": (251, 191, 36), "text": (255, 255, 255)},
        "local_listening": {"fill": (6, 182, 212), "outline": (103, 232, 249), "text": (255, 255, 255)},
        "sleeping": {"fill": (100, 116, 139), "outline": (148, 163, 184), "text": (255, 255, 255)},
        "ready": {"fill": (100, 116, 139), "outline": (148, 163, 184), "text": (255, 255, 255)},
        "listening": {"fill": (16, 185, 129), "outline": (110, 231, 183), "text": (255, 255, 255)},
        "speaking": {"fill": (14, 165, 233), "outline": (125, 211, 252), "text": (255, 255, 255)},
        "muted": {"fill": (239, 68, 68), "outline": (252, 165, 165), "text": (255, 255, 255)},
        "mic_error": {"fill": (220, 38, 38), "outline": (248, 113, 113), "text": (255, 255, 255)},
        "audio_error": {"fill": (225, 29, 72), "outline": (251, 113, 133), "text": (255, 255, 255)},
        "init_error": {"fill": (185, 28, 28), "outline": (239, 68, 68), "text": (255, 255, 255)},
    }
    colors = palette.get(state.lower(), palette["sleeping"])

    # Create transparent canvas
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    margin = 4
    # Outer circle
    draw.ellipse(
        (margin, margin, size - margin, size - margin),
        fill=colors["fill"],
        outline=colors["outline"],
        width=3,
    )

    # Draw centered "A" monogram
    # Approximate centering for 64x64 icon
    cx, cy = size // 2, size // 2
    # Draw simple clean geometric 'A'
    draw.line((cx - 10, cy + 12, cx, cy - 14), fill=colors["text"], width=3)
    draw.line((cx, cy - 14, cx + 10, cy + 12), fill=colors["text"], width=3)
    draw.line((cx - 6, cy + 3, cx + 6, cy + 3), fill=colors["text"], width=3)

    return img


class AtonSystemTray:
    """System tray manager for Windows background execution."""

    def __init__(
        self,
        hud_url: str = "http://localhost:8080",
        on_toggle_mute: Optional[Callable[[bool], None]] = None,
        on_request_briefing: Optional[Callable[[], None]] = None,
        on_exit: Optional[Callable[[], None]] = None,
        on_wake: Optional[Callable[[], None]] = None,
        on_retry_init: Optional[Callable[[], None]] = None,
        initial_state: str = "sleeping",
        initial_status_text: str = "Em espera (diga 'Aton')",
    ):
        self.hud_url = hud_url
        self.on_toggle_mute = on_toggle_mute
        self.on_request_briefing = on_request_briefing
        self.on_exit = on_exit
        self.on_wake = on_wake
        self.on_retry_init = on_retry_init

        self._state = initial_state
        self._is_muted = False
        self._status_text = initial_status_text
        self._icon: Optional[pystray.Icon] = None
        self._thread: Optional[threading.Thread] = None
        self._is_running = False

    @property
    def is_muted(self) -> bool:
        return self._is_muted

    @property
    def status_text(self) -> str:
        return self._status_text

    @property
    def state(self) -> str:
        return self._state

    def _build_menu(self) -> pystray.Menu:
        """Construct the context menu for the system tray icon."""
        menu_items = [
            item(lambda text: f"Status: {self._status_text}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            item("🎙️ Ativar Aton Agora (Ouvir)", self._handle_wake, default=True),
            item(
                "🔇 Mutar Microfone",
                self._handle_toggle_mute,
                checked=lambda item: self._is_muted,
            ),
        ]

        if self.on_retry_init is not None:
            menu_items.append(
                item("🔄 Tentar Recarregar Componentes", self._handle_retry_init)
            )

        menu_items.extend([
            item("📱 Abrir Painel Móvel (HUD)", self._handle_open_hud),
            item("📋 Resumo do Dia (Briefing)", self._handle_briefing),
            pystray.Menu.SEPARATOR,
            item("❌ Sair do Aton", self._handle_exit),
        ])

        return pystray.Menu(*menu_items)

    def _handle_retry_init(self, icon, item) -> None:
        """Handle retry initialization request from tray menu."""
        logger.info("Tray requested retry initialization")
        if self.on_retry_init:
            try:
                self.on_retry_init()
            except Exception as e:
                logger.error(f"Error in on_retry_init callback: {e}")

    def _handle_wake(self, icon, item) -> None:
        """Handle manual wake trigger from tray icon click."""
        logger.info("Tray requested manual wake-up")
        if self.on_wake:
            try:
                self.on_wake()
            except Exception as e:
                logger.error(f"Error in on_wake callback: {e}")

    def _handle_toggle_mute(self, icon, item) -> None:
        """Handle toggling the microphone mute from tray menu."""
        self._is_muted = not self._is_muted
        new_state = "muted" if self._is_muted else "sleeping"
        self.update_state(
            state=new_state,
            status_text="Microfone Silenciado" if self._is_muted else "Aguardando 'Aton'",
        )
        if self.on_toggle_mute:
            try:
                self.on_toggle_mute(self._is_muted)
            except Exception as e:
                logger.error(f"Error in on_toggle_mute callback: {e}")

    def _handle_open_hud(self, icon, item) -> None:
        """Open the Mobile Gateway HUD in the user's default browser."""
        try:
            logger.info(f"Opening HUD URL in default browser: {self.hud_url}")
            webbrowser.open(self.hud_url)
        except Exception as e:
            logger.error(f"Failed to open HUD URL: {e}")

    def _handle_briefing(self, icon, item) -> None:
        """Trigger executive briefing."""
        logger.info("Tray requested daily briefing")
        if self.on_request_briefing:
            try:
                self.on_request_briefing()
            except Exception as e:
                logger.error(f"Error in on_request_briefing callback: {e}")

    def _handle_exit(self, icon, item) -> None:
        """Handle exit request from tray icon."""
        logger.info("Aton exit requested from system tray")
        self.stop()
        if self.on_exit:
            try:
                self.on_exit()
            except Exception as e:
                logger.error(f"Error in on_exit callback: {e}")

    def update_state(self, state: str, status_text: Optional[str] = None) -> None:
        """Update the icon and tooltip dynamically according to assistant state."""
        self._state = state
        if status_text:
            self._status_text = status_text

        if self._icon and self._is_running:
            try:
                self._icon.icon = generate_tray_icon(state=self._state)
                self._icon.title = f"Aton - {self._status_text}"
            except Exception as e:
                logger.debug(f"Tray update exception (non-fatal): {e}")

    def start(self) -> None:
        """Start the system tray icon in a dedicated daemon thread."""
        if self._is_running:
            return

        self._is_running = True
        icon_img = generate_tray_icon(state=self._state)
        menu = self._build_menu()

        self._icon = pystray.Icon(
            name="aton_assistant",
            icon=icon_img,
            title=f"Aton - {self._status_text}",
            menu=menu,
        )

        def _run_tray():
            try:
                logger.info("Aton System Tray started in background")
                self._icon.run()
            except Exception as e:
                logger.error(f"System tray loop error: {e}")
            finally:
                self._is_running = False

        self._thread = threading.Thread(target=_run_tray, daemon=True, name="AtonTrayThread")
        self._thread.start()

    def stop(self) -> None:
        """Stop and remove the system tray icon."""
        if not self._is_running:
            return

        self._is_running = False
        if self._icon:
            try:
                self._icon.stop()
            except Exception as e:
                logger.debug(f"Error stopping tray icon: {e}")
        logger.info("Aton System Tray stopped")
