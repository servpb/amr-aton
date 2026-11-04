"""
Proactive Calendar Monitor & Notification Engine for Aton.

Implements the 6 reliability & safety requirements:
1. SQLite Persistence: stores notified occurrences and settings in SQLite so restarts never duplicate alerts.
2. Recurring Events & Rescheduled Events: identifies each occurrence uniquely by `(event_id, start_iso)` so weekly meetings alert every week and rescheduled events alert at their new time.
3. Tolerant 60s Window: triggers whenever `0 < time_until <= lead_minutes` (default 15 min) without requiring an exact 15:00 clock tick.
4. Persistent Do-Not-Disturb (DND) with Separate Sound vs. Visual Controls: `dnd_mute_sound` and `dnd_block_visual` persisted across restarts, plus automatic quiet hours (23:00–07:00).
5. Hourly Budget (Max 3 Alerts/Hour) with Summary Grouping: never drops important events; groups simultaneous or budget-exceeding events into a single consolidated summary alert.
6. Fault Tolerance: isolates network drops, OAuth token expiration, and API errors so the main voice loop and Gemini Live are never interrupted.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import logging
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.config import get_settings
from src.integrations.calendar_service import (
    DEFAULT_TIMEZONE,
    format_spoken_datetime_pt,
    format_spoken_time_pt,
    get_calendar_connection_service,
    get_now_in_user_tz,
    get_user_timezone,
    is_event_busy_for_user,
    wrap_untrusted_event_field,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "reminders.sqlite3"


@dataclass
class ProactiveSettings:
    """Persisted configuration for proactive calendar alerts."""

    enabled: bool = True
    lead_minutes: int = 15
    dnd_mute_sound: bool = False
    dnd_block_visual: bool = False
    quiet_start_hour: int = 23
    quiet_end_hour: int = 7
    max_alerts_per_hour: int = 3


class ProactiveCalendarMonitor:
    """
    Background monitor that checks upcoming Google Calendar events and delivers
    proactive 15-minute warnings with SQLite persistence, DND controls, hourly
    budget grouping, and audit explainability.
    """

    def __init__(
        self,
        db_path: Optional[Path | str] = None,
        service_provider: Optional[Callable[[], Tuple[Optional[Any], Optional[str], Optional[str]]]] = None,
    ) -> None:
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._service_provider = service_provider or (lambda: get_calendar_connection_service().get_service())
        self._lock = threading.RLock()
        self._last_error: Optional[str] = None
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Initialize SQLite tables for notified occurrences, settings, and audit log."""
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS proactive_calendar_settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    enabled INTEGER NOT NULL DEFAULT 1,
                    lead_minutes INTEGER NOT NULL DEFAULT 15,
                    dnd_mute_sound INTEGER NOT NULL DEFAULT 0,
                    dnd_block_visual INTEGER NOT NULL DEFAULT 0,
                    quiet_start_hour INTEGER NOT NULL DEFAULT 23,
                    quiet_end_hour INTEGER NOT NULL DEFAULT 7,
                    max_alerts_per_hour INTEGER NOT NULL DEFAULT 3,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO proactive_calendar_settings (
                    id, enabled, lead_minutes, dnd_mute_sound, dnd_block_visual,
                    quiet_start_hour, quiet_end_hour, max_alerts_per_hour, updated_at
                ) VALUES (1, 1, 15, 0, 0, 23, 7, 3, ?)
                """,
                (datetime.now(timezone.utc).isoformat(),),
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS proactive_calendar_notified (
                    occurrence_key TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL,
                    recurring_event_id TEXT,
                    event_title TEXT NOT NULL,
                    event_start_iso TEXT NOT NULL,
                    notified_at_epoch REAL NOT NULL,
                    notified_at_iso TEXT NOT NULL,
                    delivery_mode TEXT NOT NULL,
                    reason TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_proactive_notified_epoch
                ON proactive_calendar_notified (notified_at_epoch)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS proactive_calendar_alerts_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    delivered_at_epoch REAL NOT NULL,
                    delivered_at_iso TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    spoken_explanation TEXT NOT NULL,
                    sound_played INTEGER NOT NULL,
                    visual_shown INTEGER NOT NULL,
                    grouped_count INTEGER NOT NULL DEFAULT 1,
                    events_json TEXT NOT NULL
                )
                """
            )
            conn.commit()

    # ------------------------------------------------------------------
    # Settings Management (Requirement #4: Persistent DND & Separate Sound/Visual)
    # ------------------------------------------------------------------

    def get_settings(self) -> ProactiveSettings:
        """Read persisted proactive settings from SQLite."""
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM proactive_calendar_settings WHERE id = 1").fetchone()
            if not row:
                return ProactiveSettings()
            return ProactiveSettings(
                enabled=bool(row["enabled"]),
                lead_minutes=int(row["lead_minutes"]),
                dnd_mute_sound=bool(row["dnd_mute_sound"]),
                dnd_block_visual=bool(row["dnd_block_visual"]),
                quiet_start_hour=int(row["quiet_start_hour"]),
                quiet_end_hour=int(row["quiet_end_hour"]),
                max_alerts_per_hour=int(row["max_alerts_per_hour"]),
            )

    def update_settings(
        self,
        enabled: Optional[bool] = None,
        lead_minutes: Optional[int] = None,
        dnd_mute_sound: Optional[bool] = None,
        dnd_block_visual: Optional[bool] = None,
        quiet_start_hour: Optional[int] = None,
        quiet_end_hour: Optional[int] = None,
    ) -> ProactiveSettings:
        """Update and persist proactive settings in SQLite."""
        current = self.get_settings()
        new_enabled = current.enabled if enabled is None else bool(enabled)
        new_lead = current.lead_minutes if lead_minutes is None else max(1, min(120, int(lead_minutes)))
        new_mute_sound = current.dnd_mute_sound if dnd_mute_sound is None else bool(dnd_mute_sound)
        new_block_visual = current.dnd_block_visual if dnd_block_visual is None else bool(dnd_block_visual)
        new_q_start = current.quiet_start_hour if quiet_start_hour is None else max(0, min(23, int(quiet_start_hour)))
        new_q_end = current.quiet_end_hour if quiet_end_hour is None else max(0, min(23, int(quiet_end_hour)))

        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE proactive_calendar_settings
                SET enabled = ?,
                    lead_minutes = ?,
                    dnd_mute_sound = ?,
                    dnd_block_visual = ?,
                    quiet_start_hour = ?,
                    quiet_end_hour = ?,
                    updated_at = ?
                WHERE id = 1
                """,
                (
                    int(new_enabled),
                    new_lead,
                    int(new_mute_sound),
                    int(new_block_visual),
                    new_q_start,
                    new_q_end,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
        return self.get_settings()

    # ------------------------------------------------------------------
    # Occurrence Key & Deduplication (Requirement #1 & #2)
    # ------------------------------------------------------------------

    @staticmethod
    def build_occurrence_key(event: Dict[str, Any], start_dt: datetime) -> str:
        """
        Build a unique key for a specific event occurrence and start timestamp.
        - Recurring events have distinct instance IDs or distinct start_dt values per week.
        - If an event is rescheduled to a new start_dt, a new key is generated so the user
          is notified at the new time.
        """
        ev_id = str(event.get("id") or "unknown").strip()
        rec_id = str(event.get("recurringEventId") or "").strip()
        start_utc_str = start_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if rec_id:
            return f"rec::{rec_id}::{ev_id}::{start_utc_str}"
        return f"evt::{ev_id}::{start_utc_str}"

    def is_occurrence_notified(self, occurrence_key: str) -> bool:
        """Return True if this exact event occurrence + start time was already notified."""
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM proactive_calendar_notified WHERE occurrence_key = ?",
                (occurrence_key,),
            ).fetchone()
            return row is not None

    def _mark_occurrences_notified(
        self,
        items: List[Dict[str, Any]],
        now_epoch: float,
        now_iso: str,
        delivery_mode: str,
        reason: str,
    ) -> None:
        with self._lock, self._connect() as conn:
            for item in items:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO proactive_calendar_notified (
                        occurrence_key, event_id, recurring_event_id, event_title,
                        event_start_iso, notified_at_epoch, notified_at_iso, delivery_mode, reason
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item["occurrence_key"],
                        item["event_id"],
                        item.get("recurring_event_id"),
                        item["title"],
                        item["start_iso"],
                        now_epoch,
                        now_iso,
                        delivery_mode,
                        reason,
                    ),
                )
            conn.commit()

    def _count_alerts_in_last_hour(self, now_epoch: float) -> int:
        cutoff = now_epoch - 3600.0
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM proactive_calendar_alerts_log WHERE delivered_at_epoch >= ?",
                (cutoff,),
            ).fetchone()
            return int(row["cnt"]) if row else 0

    def _record_alert_log(
        self,
        now_epoch: float,
        now_iso: str,
        title: str,
        body: str,
        spoken_explanation: str,
        sound_played: bool,
        visual_shown: bool,
        events_payload: List[Dict[str, Any]],
    ) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO proactive_calendar_alerts_log (
                    delivered_at_epoch, delivered_at_iso, title, body,
                    spoken_explanation, sound_played, visual_shown, grouped_count, events_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now_epoch,
                    now_iso,
                    title,
                    body,
                    spoken_explanation,
                    int(sound_played),
                    int(visual_shown),
                    len(events_payload),
                    json.dumps(events_payload, ensure_ascii=False),
                ),
            )
            conn.commit()

    def get_last_alert_explanation(self) -> Dict[str, Any]:
        """Return the explanation of the most recent proactive calendar alert."""
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM proactive_calendar_alerts_log ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if not row:
                return {
                    "status": "empty",
                    "message": "Eu ainda não disparei nenhum aviso automático da agenda hoje.",
                }
            return {
                "status": "success",
                "delivered_at": row["delivered_at_iso"],
                "title": row["title"],
                "body": row["body"],
                "grouped_count": int(row["grouped_count"]),
                "sound_played": bool(row["sound_played"]),
                "visual_shown": bool(row["visual_shown"]),
                "events": json.loads(row["events_json"] or "[]"),
                "message": row["spoken_explanation"],
            }

    # ------------------------------------------------------------------
    # Quiet Hours Helper
    # ------------------------------------------------------------------

    @staticmethod
    def is_in_quiet_hours(now_dt: datetime, start_hour: int = 23, end_hour: int = 7) -> bool:
        """Return True if `now_dt.hour` falls within the quiet hours window."""
        h = now_dt.hour
        if start_hour == end_hour:
            return False
        if start_hour > end_hour:
            # Crosses midnight, e.g. 23:00 to 07:00
            return h >= start_hour or h < end_hour
        return start_hour <= h < end_hour

    # ------------------------------------------------------------------
    # Main Poll & Evaluation Cycle (Requirements #3, #4, #5, #6)
    # ------------------------------------------------------------------

    def check_and_deliver(
        self,
        notify_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        now_dt: Optional[datetime] = None,
        now_epoch: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Poll Google Calendar for upcoming events within `[now, now + lead_minutes]`.
        Fault-tolerant: never raises exceptions to caller.
        """
        try:
            cfg = self.get_settings()
            if not cfg.enabled:
                return {"status": "disabled", "delivered": 0}

            if cfg.dnd_block_visual and cfg.dnd_mute_sound:
                # Full DND blocks both visual and sound; wait until DND is lifted
                return {"status": "dnd_blocked_all", "delivered": 0}

            tz = get_user_timezone()
            current_dt = (now_dt or get_now_in_user_tz()).astimezone(tz)
            current_epoch = now_epoch if now_epoch is not None else time.time()

            service, resolved_account, err = self._service_provider()
            if service is None:
                self._last_error = err or "Service unavailable"
                return {"status": "service_unavailable", "delivered": 0, "reason": self._last_error}

            window_end_dt = current_dt + timedelta(minutes=cfg.lead_minutes)
            # Query slightly wider window to catch events starting in the next lead_minutes
            time_min_utc = (current_dt - timedelta(minutes=1)).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            time_max_utc = (window_end_dt + timedelta(minutes=1)).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

            events_resp = (
                service.events()
                .list(
                    calendarId="primary",
                    timeMin=time_min_utc,
                    timeMax=time_max_utc,
                    singleEvents=True,
                    orderBy="startTime",
                    maxResults=25,
                )
                .execute()
            )
            raw_items = events_resp.get("items", []) or []

            due_candidates: List[Dict[str, Any]] = []
            for ev in raw_items:
                if not is_event_busy_for_user(ev, account_email=resolved_account):
                    continue
                start_obj = ev.get("start") or {}
                # Only timed events have a 15-minute countdown
                start_iso_raw = start_obj.get("dateTime")
                if not start_iso_raw:
                    continue
                try:
                    ev_start_dt = datetime.fromisoformat(start_iso_raw.replace("Z", "+00:00")).astimezone(tz)
                except Exception:
                    continue

                seconds_until = (ev_start_dt - current_dt).total_seconds()
                # Requirement #3: Tolerant window (0 < seconds_until <= lead_minutes * 60)
                if not (0 < seconds_until <= cfg.lead_minutes * 60):
                    continue

                occ_key = self.build_occurrence_key(ev, ev_start_dt)
                if self.is_occurrence_notified(occ_key):
                    continue

                minutes_left = max(1, int(round(seconds_until / 60.0)))
                clean_title = wrap_untrusted_event_field(
                    ev.get("summary") or "Compromisso sem título",
                    max_len=90,
                    delimit=False,
                )
                clean_loc = wrap_untrusted_event_field(
                    ev.get("location") or "",
                    max_len=80,
                    delimit=False,
                )
                due_candidates.append(
                    {
                        "occurrence_key": occ_key,
                        "event_id": str(ev.get("id") or ""),
                        "recurring_event_id": ev.get("recurringEventId"),
                        "title": clean_title,
                        "location": clean_loc,
                        "start_iso": ev_start_dt.isoformat(),
                        "spoken_time": format_spoken_time_pt(ev_start_dt),
                        "minutes_left": minutes_left,
                    }
                )

            if not due_candidates:
                self._last_error = None
                return {"status": "ok", "delivered": 0}

            # Requirement #4: Evaluate Quiet Hours & Separate DND Sound vs. Visual
            in_quiet = self.is_in_quiet_hours(current_dt, cfg.quiet_start_hour, cfg.quiet_end_hour)
            allow_visual = not cfg.dnd_block_visual
            allow_sound = (not cfg.dnd_mute_sound) and (not in_quiet)

            # Requirement #5: Hourly Budget (Max 3 alerts/hour) & Grouping
            alerts_last_hour = self._count_alerts_in_last_hour(current_epoch)
            remaining_budget = max(0, cfg.max_alerts_per_hour - alerts_last_hour)

            if remaining_budget == 0:
                # Budget already reached: group all new candidates into a single quiet visual digest
                # so important appointments are never lost!
                allow_sound = False
                batches = [due_candidates]
            elif len(due_candidates) > remaining_budget or len(due_candidates) > 1:
                # Consolidate into a single summary notification so we never spam or drop events
                batches = [due_candidates]
            else:
                batches = [[due_candidates[0]]]

            delivered_count = 0
            for batch in batches:
                if len(batch) == 1:
                    item = batch[0]
                    mins = item["minutes_left"]
                    alert_title = f"Aton — Compromisso em {mins} min"
                    loc_suffix = f" ({item['location']})" if item["location"] else ""
                    alert_body = f"{item['title']} {item['spoken_time']}{loc_suffix}"
                    spoken_explanation = (
                        f"Eu avisei você porque o compromisso {item['title']} está marcado na sua agenda "
                        f"para {item['spoken_time']}, faltando {mins} minutos para começar."
                    )
                else:
                    titles_joined = "; ".join(f"{it['title']} ({it['spoken_time']})" for it in batch[:4])
                    if len(batch) > 4:
                        titles_joined += f" e mais {len(batch) - 4}"
                    alert_title = f"Aton — {len(batch)} compromissos nos próximos {cfg.lead_minutes} min"
                    alert_body = titles_joined
                    spoken_explanation = (
                        f"Eu agrupei um aviso resumido porque você tem {len(batch)} compromissos começando "
                        f"nos próximos {cfg.lead_minutes} minutos: {titles_joined}."
                    )

                payload = {
                    "title": alert_title,
                    "body": alert_body,
                    "spoken_explanation": spoken_explanation,
                    "allow_visual": allow_visual,
                    "allow_sound": allow_sound,
                    "events": batch,
                }

                if notify_callback is not None:
                    notify_callback(payload)

                delivery_mode = "visual_and_sound" if (allow_visual and allow_sound) else ("visual_only" if allow_visual else "logged_only")
                self._mark_occurrences_notified(
                    items=batch,
                    now_epoch=current_epoch,
                    now_iso=current_dt.isoformat(),
                    delivery_mode=delivery_mode,
                    reason=spoken_explanation,
                )
                self._record_alert_log(
                    now_epoch=current_epoch,
                    now_iso=current_dt.isoformat(),
                    title=alert_title,
                    body=alert_body,
                    spoken_explanation=spoken_explanation,
                    sound_played=allow_sound,
                    visual_shown=allow_visual,
                    events_payload=batch,
                )
                delivered_count += 1

            self._last_error = None
            return {
                "status": "delivered",
                "delivered": delivered_count,
                "events_notified": len(due_candidates),
                "sound_played": allow_sound,
                "visual_shown": allow_visual,
            }
        except Exception as exc:
            # Requirement #6: Fault tolerance — never crash the caller loop
            self._last_error = str(exc)
            logger.warning("Proactive calendar check skipped due to transient error: %s", exc)
            return {
                "status": "error_handled",
                "delivered": 0,
                "error": self._last_error,
            }


_PROACTIVE_MONITOR_SINGLETON: Optional[ProactiveCalendarMonitor] = None


def get_proactive_calendar_monitor() -> ProactiveCalendarMonitor:
    """Return the singleton ProactiveCalendarMonitor instance."""
    global _PROACTIVE_MONITOR_SINGLETON
    if _PROACTIVE_MONITOR_SINGLETON is None:
        _PROACTIVE_MONITOR_SINGLETON = ProactiveCalendarMonitor()
    return _PROACTIVE_MONITOR_SINGLETON


def set_proactive_calendar_monitor(monitor: Optional[ProactiveCalendarMonitor]) -> None:
    """Override or reset the singleton ProactiveCalendarMonitor instance (used by tests)."""
    global _PROACTIVE_MONITOR_SINGLETON
    _PROACTIVE_MONITOR_SINGLETON = monitor


