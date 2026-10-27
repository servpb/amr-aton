"""Push-to-Talk and manual trigger controller for AMR Assistant."""

import logging
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class PushToTalk:
    """Manages manual push-to-talk activation via keyboard shortcut or manual trigger."""

    def __init__(
        self,
        hotkey: str = "ctrl+space",
        on_trigger_callback: Optional[Callable[[], None]] = None,
    ):
        self.hotkey = hotkey
        self.on_trigger_callback = on_trigger_callback
        self._is_active = False
        self._lock = threading.Lock()

    def trigger(self) -> None:
        """Trigger activation manually."""
        with self._lock:
            self._is_active = True
            logger.info(f"Push-to-talk triggered via {self.hotkey}")

        if self.on_trigger_callback:
            try:
                self.on_trigger_callback()
            except Exception as exc:
                logger.error(f"Error in push-to-talk trigger callback: {exc}")

    def release(self) -> None:
        """Release the push-to-talk state."""
        with self._lock:
            self._is_active = False
            logger.info("Push-to-talk released.")

    @property
    def is_active(self) -> bool:
        """Check if push-to-talk is currently pressed/active."""
        with self._lock:
            return self._is_active
