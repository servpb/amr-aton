"""
Google Workspace & Google Calendar Voice-First Tools (Phase 4 / Voice Upgrade).
Provides full natural-language schedule management for Aton:
- Events: list_events, create_event, edit_event, delete_event
- Calendars: list_calendars, create_calendar, edit_calendar, delete_calendar
- Support & Safety: get_current_time, confirm_action, check_calendar_connection
- Legacy compatibility aliases: get_calendar_events, create_calendar_event
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime, time as dt_time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import logging
from src.config import get_settings
from src.integrations.calendar_service import (
    CALENDAR_SCOPES as SCOPES,
    DEFAULT_TIMEZONE,
    build_next_7_days_table,
    detect_event_conflicts,
    format_spoken_datetime_pt,
    get_calendar_confirmation_manager,
    get_calendar_connection_service,
    get_now_in_user_tz,
    get_user_timezone,
    get_weekday_pt,
    is_primary_calendar,
    lookup_contact_by_name,
    normalize_spoken_name,
    sanitize_and_delimit_event,
    strip_until_from_rrule,
    suggest_free_business_slots,
    update_rrule_with_until,
    wrap_untrusted_event_field,
)
logger = logging.getLogger(__name__)

MAX_SPOKEN_EVENTS_PER_PAGE = 3


def get_calendar_service(account: Optional[str] = None) -> Any:
    """
    Backward-compatible helper returning an authenticated Google Calendar API v3
    Resource without opening a browser during voice operation.
    """
    service, _, _ = get_calendar_connection_service().get_service(account=account)
    return service


def parse_datetime_flexible(dt_str: str, default_hour: int = 9) -> datetime:
    """
    Parse an ISO 8601 string or Portuguese natural date/time expression into a
    timezone-aware datetime in the user's configured timezone (America/Fortaleza).
    """
    tz = get_user_timezone()
    now = get_now_in_user_tz()
    cleaned = (dt_str or "").strip()

    if not cleaned:
        return now.replace(hour=default_hour, minute=0, second=0, microsecond=0)

    # 1. Try standard ISO 8601 parsing first
    try:
        iso_candidate = cleaned.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(iso_candidate)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=tz)
        return parsed.astimezone(tz)
    except ValueError:
        pass

    lower = cleaned.lower()

    # 2. Relative day resolution
    base_date = now.date()
    if "depois de amanh" in lower:
        base_date = now.date() + timedelta(days=2)
    elif "amanh" in lower:
        base_date = now.date() + timedelta(days=1)
    elif "ontem" in lower:
        base_date = now.date() - timedelta(days=1)
    else:
        # Check explicit DD/MM/YYYY or DD/MM
        date_match = re.search(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", lower)
        if date_match:
            day = int(date_match.group(1))
            month = int(date_match.group(2))
            year = int(date_match.group(3)) if date_match.group(3) else now.year
            if year < 100:
                year += 2000
            try:
                base_date = date(year, month, day)
            except ValueError:
                pass
        else:
            # Check weekday name in Portuguese
            weekday_map = {
                "segunda": 0,
                "terça": 1,
                "terca": 1,
                "quarta": 2,
                "quinta": 3,
                "sexta": 4,
                "sábado": 5,
                "sabado": 5,
                "domingo": 6,
            }
            for w_name, w_idx in weekday_map.items():
                if w_name in lower:
                    days_ahead = (w_idx - now.weekday()) % 7
                    if days_ahead == 0 and ("que vem" in lower or "próxima" in lower or "proxima" in lower):
                        days_ahead = 7
                    elif days_ahead == 0:
                        days_ahead = 0
                    base_date = now.date() + timedelta(days=days_ahead)
                    break

    # 3. Extract time (e.g., '14:30', '14h30', '14h', 'às 15')
    hour, minute = default_hour, 0
    time_match = re.search(r"(\d{1,2})\s*(?::|h)\s*(\d{2})?", lower)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2)) if time_match.group(2) else 0
    else:
        at_match = re.search(r"(?:às|as)\s+(\d{1,2})(?:\s*e\s*meia)?", lower)
        if at_match:
            hour = int(at_match.group(1))
            if "meia" in lower:
                minute = 30

    if ("tarde" in lower or "noite" in lower) and 1 <= hour <= 11:
        hour += 12

    hour = max(0, min(23, hour))
    minute = max(0, min(59, minute))
    return datetime(base_date.year, base_date.month, base_date.day, hour, minute, 0, tzinfo=tz)


def _is_date_only_string(value: str) -> bool:
    """Return True if the input string is strictly a YYYY-MM-DD date without time."""
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", (value or "").strip()))


def _resolve_time_window(
    time_min: Optional[str],
    time_max: Optional[str],
) -> Tuple[datetime, datetime, str]:
    """Resolve time_min and time_max into timezone-aware datetimes and a spoken label."""
    tz = get_user_timezone()
    now = get_now_in_user_tz()

    t_min_raw = (time_min or "").strip().lower()
    if not t_min_raw or t_min_raw in ("today", "hoje"):
        start_dt = now
        end_dt = now.replace(hour=23, minute=59, second=59, microsecond=0)
        label = "hoje"
    elif t_min_raw in ("tomorrow", "amanha", "amanhã"):
        tmr = now + timedelta(days=1)
        start_dt = tmr.replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt = tmr.replace(hour=23, minute=59, second=59, microsecond=0)
        label = "amanhã"
    elif t_min_raw in ("week", "semana"):
        start_dt = now
        end_dt = (now + timedelta(days=7)).replace(hour=23, minute=59, second=59, microsecond=0)
        label = "nos próximos 7 dias"
    else:
        if _is_date_only_string(time_min or ""):
            d = date.fromisoformat((time_min or "").strip())
            start_dt = datetime.combine(d, dt_time(0, 0, 0), tzinfo=tz)
            end_dt = datetime.combine(d, dt_time(23, 59, 59), tzinfo=tz)
        else:
            start_dt = parse_datetime_flexible(time_min or "", default_hour=0)
            end_dt = start_dt.replace(hour=23, minute=59, second=59, microsecond=0)
        label = format_spoken_datetime_pt(start_dt.date(), reference_now=now, all_day=True).replace(", o dia todo", "")

    if time_max and time_max.strip():
        if _is_date_only_string(time_max):
            d_max = date.fromisoformat(time_max.strip())
            end_dt = datetime.combine(d_max, dt_time(23, 59, 59), tzinfo=tz)
        else:
            end_dt = parse_datetime_flexible(time_max, default_hour=23)

    if end_dt <= start_dt:
        end_dt = start_dt + timedelta(hours=23, minutes=59)

    return start_dt, end_dt, label


# ==============================================================================
# 1. Support & Context Tools
# ==============================================================================


def get_current_time(timezone_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Return the authoritative current date, time, weekday (calculated in code),
    and the next-7-days reference table. Used whenever a voice session crosses
    midnight or needs fresh temporal grounding.
    """
    now = get_now_in_user_tz(timezone_name)
    weekday_pt = get_weekday_pt(now)
    spoken = format_spoken_datetime_pt(now, reference_now=now, all_day=False)
    table_7d = build_next_7_days_table(reference_now=now)
    tz_label = str(now.tzinfo or DEFAULT_TIMEZONE)

    return {
        "status": "success",
        "iso_now": now.isoformat(),
        "date_br": now.strftime("%d/%m/%Y"),
        "time_24h": now.strftime("%H:%M"),
        "weekday": weekday_pt,
        "timezone": tz_label,
        "spoken_now": spoken,
        "next_7_days_table": table_7d,
        "message": f"Agora é {spoken}.",
    }


def check_calendar_connection(account: Optional[str] = None) -> Dict[str, Any]:
    """
    Passively verify whether Google Calendar OAuth 2.0 credentials are valid.
    Never triggers an interactive browser flow.
    """
    res = get_calendar_connection_service().check_connection(account=account)
    return {
        "status": "success" if res.get("ok") else "error",
        **res,
    }


def confirm_action(
    proposal_id: str,
    confirmed_name: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Confirm and execute a pending destructive or high-impact calendar action
    (delete_event, edit_event, or delete_calendar).
    Enforces 60-second TTL, single-use consumption, voice session binding, and
    secondary calendar spoken name verification.
    """
    manager = get_calendar_confirmation_manager()
    validation = manager.confirm_proposal(
        proposal_id=proposal_id,
        session_id=session_id,
        confirmed_name=confirmed_name,
    )
    if not validation.get("ok"):
        return {
            "status": validation.get("status", "error"),
            "message": validation.get("message", "Não foi possível confirmar a ação."),
        }

    proposal = validation["proposal"]
    action = proposal.action
    payload = dict(proposal.payload)
    payload["_confirmed"] = True

    if action == "delete_event":
        return delete_event(**payload)
    if action == "edit_event":
        return edit_event(**payload)
    if action == "delete_calendar":
        return delete_calendar(**payload)

    return {
        "status": "error",
        "message": f"Ação pendente desconhecida: {action}.",
    }


# ==============================================================================
# 2. Event Tools (list_events, create_event, edit_event, delete_event)
# ==============================================================================


def list_events(
    calendar_id: str = "primary",
    time_min: Optional[str] = None,
    time_max: Optional[str] = None,
    query: Optional[str] = None,
    max_results: int = 20,
    page_offset: int = 0,
    account: Optional[str] = None,
) -> Dict[str, Any]:
    """
    List events from Google Calendar within a time range or search query.
    Delivers untrusted event content delimited and truncated, and reads at most
    3 events per spoken response page to avoid cognitive overload on voice.
    """
    settings = get_settings()
    target_cal = (calendar_id or settings.google_calendar_id or "primary").strip()
    service = get_calendar_service(account=account)
    if not service:
        return {
            "status": "error",
            "message": "A conexão com o Google Agenda não está ativa. Peça para autenticar no terminal.",
        }

    now = get_now_in_user_tz()
    start_dt, end_dt, period_label = _resolve_time_window(time_min, time_max)
    max_results = max(1, min(50, int(max_results or 20)))
    page_offset = max(0, int(page_offset or 0))

    try:
        req_kwargs: Dict[str, Any] = {
            "calendarId": target_cal,
            "timeMin": start_dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "timeMax": end_dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "maxResults": max_results,
            "singleEvents": True,
            "orderBy": "startTime",
        }
        if query and query.strip():
            req_kwargs["q"] = query.strip()

        events_result = service.events().list(**req_kwargs).execute()
        raw_items = events_result.get("items", []) or []

        sanitized_all = [sanitize_and_delimit_event(item, reference_now=now) for item in raw_items]
        total_count = len(sanitized_all)

        if total_count == 0:
            return {
                "status": "success",
                "count": 0,
                "events": [],
                "remaining_count": 0,
                "message": f"Você está livre {period_label}, sem compromissos agendados.",
            }

        page_slice = sanitized_all[page_offset : page_offset + MAX_SPOKEN_EVENTS_PER_PAGE]
        remaining = max(0, total_count - (page_offset + len(page_slice)))

        spoken_parts = [f"{ev['title']}, {ev['spoken_time']}" for ev in page_slice]
        any_suspicious = any(ev.get("suspicious_content_detected") for ev in page_slice)

        if total_count == 1:
            msg = f"Você tem um compromisso {period_label}: {spoken_parts[0]}."
        else:
            joined = "; ".join(spoken_parts)
            msg = f"Você tem {total_count} compromissos {period_label}. Os principais são: {joined}."
            if remaining > 0:
                msg += f" Existem mais {remaining} compromissos. Quer que eu continue?"

        if any_suspicious:
            msg += " Atenção: um dos eventos contém texto suspeito na descrição e foi isolado por segurança."

        return {
            "status": "success",
            "count": total_count,
            "events": page_slice,
            "all_events": sanitized_all,
            "page_offset": page_offset,
            "remaining_count": remaining,
            "next_page_offset": (page_offset + MAX_SPOKEN_EVENTS_PER_PAGE) if remaining > 0 else None,
            "untrusted_data": True,
            "suspicious_content_detected": any_suspicious,
            "message": msg,
        }
    except Exception as exc:
        logger.error("Google Calendar list_events error: %s", exc)
        return {
            "status": "error",
            "message": "Não consegui consultar os compromissos da sua agenda agora.",
        }


def _resolve_attendees_for_voice(
    attendees: Optional[List[str]],
    attendees_confirmed: bool,
    service: Any,
    calendar_id: str,
    spoken_when: str,
) -> Tuple[Optional[List[Dict[str, str]]], Optional[Dict[str, Any]]]:
    """
    Validate and resolve attendees according to Adjustment #8:
    - Never invent emails.
    - If a name without '@' is provided, search prior contacts and only suggest.
    - Never send email invites unless `attendees_confirmed=True`.
    """
    if not attendees:
        return None, None

    resolved_emails: List[Dict[str, str]] = []
    suggestions_found: List[Dict[str, str]] = []
    missing_names: List[str] = []

    for raw_item in attendees:
        entry = (raw_item or "").strip()
        if not entry:
            continue
        if "@" in entry:
            resolved_emails.append({"email": entry.lower()})
        else:
            matches = lookup_contact_by_name(entry, service=service, calendar_id=calendar_id)
            if len(matches) == 1:
                suggestions_found.append(matches[0])
                resolved_emails.append({"email": matches[0]["email"], "displayName": matches[0]["name"]})
            elif len(matches) > 1:
                options_spoken = ", ".join(f"{m['name']} ({m['email']})" for m in matches[:3])
                return None, {
                    "status": "contact_disambiguation_required",
                    "candidates": matches[:3],
                    "message": (
                        f"Encontrei mais de um contato para {entry}: {options_spoken}. "
                        "Qual deles você quer convidar?"
                    ),
                }
            else:
                missing_names.append(entry)

    if missing_names:
        names_str = ", ".join(missing_names)
        return None, {
            "status": "contact_email_required",
            "missing_contacts": missing_names,
            "message": (
                f"Não encontrei o e-mail de {names_str} nos seus contatos. "
                "Por favor, soletre o endereço de e-mail para eu confirmar antes de enviar o convite."
            ),
        }

    if resolved_emails and not attendees_confirmed:
        if suggestions_found:
            first = suggestions_found[0]
            return None, {
                "status": "contact_confirmation_required",
                "suggested_contacts": suggestions_found,
                "proposed_attendees": resolved_emails,
                "message": (
                    f"Encontrei o contato {first['name']} com o e-mail {first['email']}. "
                    f"Posso enviar o convite para esse endereço {spoken_when}?"
                ),
            }
        emails_list = ", ".join(item["email"] for item in resolved_emails)
        return None, {
            "status": "attendee_confirmation_required",
            "proposed_attendees": resolved_emails,
            "message": (
                f"Isso enviará um convite por e-mail para {emails_list} {spoken_when}. "
                "Você confirma o envio do convite?"
            ),
        }

    return resolved_emails, None


def create_event(
    title: str,
    start: str,
    end: Optional[str] = None,
    calendar_id: str = "primary",
    description: Optional[str] = None,
    location: Optional[str] = None,
    attendees: Optional[List[str]] = None,
    reminders: Optional[int] = 10,
    recurrence: Optional[List[str]] = None,
    add_meet_link: bool = False,
    all_day: bool = False,
    force_conflict: bool = False,
    attendees_confirmed: bool = False,
    account: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a new event in Google Calendar with built-in conflict detection,
    3 business-hours slot suggestions, prior contact lookup, and voice defaults
    (1-hour duration, 10-minute reminder, primary calendar, all-day when no time given).
    """
    if not title or not title.strip():
        return {"status": "error", "message": "Qual é o título do compromisso que você quer agendar?"}
    if not start or not start.strip():
        return {"status": "error", "message": "Em qual dia e horário você quer marcar esse compromisso?"}

    settings = get_settings()
    target_cal = (calendar_id or settings.google_calendar_id or "primary").strip()
    conn_service = get_calendar_connection_service()
    service = get_calendar_service(account=account)
    if not service:
        return {
            "status": "error",
            "message": "A conexão com o Google Agenda não está ativa. Autentique no terminal primeiro.",
        }

    resolved_account = conn_service.resolve_account(account)
    tz = get_user_timezone()
    tz_name = getattr(settings, "google_calendar_timezone", DEFAULT_TIMEZONE) or DEFAULT_TIMEZONE
    now = get_now_in_user_tz()

    is_all_day = bool(all_day or _is_date_only_string(start))
    if is_all_day:
        try:
            start_date = date.fromisoformat(start.strip()[:10])
        except ValueError:
            start_date = parse_datetime_flexible(start).date()
        if end and _is_date_only_string(end):
            end_date = date.fromisoformat(end.strip()[:10])
            if end_date <= start_date:
                end_date = start_date + timedelta(days=1)
        else:
            end_date = start_date + timedelta(days=1)
        start_dt = datetime.combine(start_date, dt_time(0, 0, 0), tzinfo=tz)
        end_dt = datetime.combine(end_date, dt_time(0, 0, 0), tzinfo=tz)
        spoken_when = format_spoken_datetime_pt(start_date, reference_now=now, all_day=True)
    else:
        start_dt = parse_datetime_flexible(start, default_hour=9)
        if end and end.strip():
            end_dt = parse_datetime_flexible(end, default_hour=(start_dt.hour + 1) % 24)
            if end_dt <= start_dt:
                end_dt = start_dt + timedelta(hours=1)
        else:
            end_dt = start_dt + timedelta(hours=1)
        spoken_when = format_spoken_datetime_pt(start_dt, reference_now=now, all_day=False)

    # 1. Check attendees & prior contact lookup before creating or sending emails
    resolved_attendees, attendee_gate = _resolve_attendees_for_voice(
        attendees=attendees,
        attendees_confirmed=attendees_confirmed,
        service=service,
        calendar_id=target_cal,
        spoken_when=spoken_when,
    )
    if attendee_gate is not None:
        return attendee_gate

    # 2. Built-in Conflict Detection (unless force_conflict=True or all-day event)
    if not force_conflict and not is_all_day:
        try:
            day_min = datetime.combine(start_dt.date() - timedelta(days=1), dt_time(0, 0, 0), tzinfo=tz)
            day_max = datetime.combine(end_dt.date() + timedelta(days=1), dt_time(23, 59, 59), tzinfo=tz)
            existing_resp = (
                service.events()
                .list(
                    calendarId=target_cal,
                    timeMin=day_min.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                    timeMax=day_max.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            existing_items = existing_resp.get("items", []) or []
            conflicts = detect_event_conflicts(
                events=existing_items,
                start_dt=start_dt,
                end_dt=end_dt,
                account_email=resolved_account,
            )
            if conflicts:
                duration_mins = max(15, int((end_dt - start_dt).total_seconds() // 60))
                suggestions = suggest_free_business_slots(
                    events=existing_items,
                    desired_start=start_dt,
                    duration_minutes=duration_mins,
                    account_email=resolved_account,
                    max_suggestions=3,
                )
                conflict_names = ", ".join(c["title"] for c in conflicts[:2])
                sug_spoken = ", ".join(s["spoken"] for s in suggestions)
                msg = f"Você já tem {conflict_names} nesse horário. Quer criar mesmo assim"
                if sug_spoken:
                    msg += f", ou prefere um destes horários livres: {sug_spoken}?"
                else:
                    msg += ", ou prefere outro horário?"
                return {
                    "status": "conflict_detected",
                    "conflicts": conflicts,
                    "suggested_slots": suggestions,
                    "message": msg,
                }
        except Exception as exc:
            logger.debug("Conflict check skipped due to non-fatal error: %s", exc)

    # 3. Build Event Payload with Voice-First Defaults
    reminder_minutes = 10 if reminders is None else int(reminders)
    event_body: Dict[str, Any] = {
        "summary": title.strip(),
        "reminders": {
            "useDefault": False,
            "overrides": [{"method": "popup", "minutes": max(0, reminder_minutes)}],
        },
    }

    if is_all_day:
        event_body["start"] = {"date": start_dt.date().isoformat()}
        event_body["end"] = {"date": end_dt.date().isoformat()}
    else:
        event_body["start"] = {"dateTime": start_dt.isoformat(), "timeZone": tz_name}
        event_body["end"] = {"dateTime": end_dt.isoformat(), "timeZone": tz_name}

    if description and description.strip():
        event_body["description"] = description.strip()
    if location and location.strip():
        event_body["location"] = location.strip()
    if resolved_attendees:
        event_body["attendees"] = resolved_attendees
    if recurrence:
        event_body["recurrence"] = [r if r.upper().startswith("RRULE:") else f"RRULE:{r}" for r in recurrence]
    if add_meet_link:
        event_body["conferenceData"] = {
            "createRequest": {
                "requestId": uuid.uuid4().hex,
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        }

    try:
        insert_kwargs: Dict[str, Any] = {
            "calendarId": target_cal,
            "body": event_body,
        }
        if add_meet_link:
            insert_kwargs["conferenceDataVersion"] = 1
        if resolved_attendees:
            insert_kwargs["sendUpdates"] = "all"

        created = service.events().insert(**insert_kwargs).execute()
        return {
            "status": "success",
            "event": {
                "id": created.get("id", ""),
                "title": created.get("summary", title.strip()),
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat(),
                "all_day": is_all_day,
                "spoken_time": spoken_when,
                "html_link": created.get("htmlLink", ""),
                "has_meet_link": bool(created.get("hangoutLink") or created.get("conferenceData")),
            },
            "message": f"Pronto, agendei {title.strip()} para {spoken_when}.",
        }
    except Exception as exc:
        logger.error("Failed to create Google Calendar event: %s", exc)
        return {
            "status": "error",
            "message": f"Não consegui criar o compromisso {title.strip()} na sua agenda.",
        }


def edit_event(
    event_id: str,
    calendar_id: str = "primary",
    title: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    attendees: Optional[List[str]] = None,
    reminders: Optional[int] = None,
    recurrence: Optional[List[str]] = None,
    add_meet_link: Optional[bool] = None,
    recurrence_scope: Optional[str] = None,
    force_conflict: bool = False,
    account: Optional[str] = None,
    _confirmed: bool = False,
) -> Dict[str, Any]:
    """
    Edit an existing Google Calendar event.
    - Checks conflicts automatically when changing time.
    - Requires recurrence_scope ('this', 'following', or 'all') for recurring events.
    - Explicitly splits recurring series with UNTIL + new series when recurrence_scope == 'following'.
    - Requires confirm_action when modifying recurring series or events with attendees.
    """
    if not event_id or not event_id.strip():
        return {"status": "error", "message": "Informe qual compromisso deve ser editado."}

    settings = get_settings()
    target_cal = (calendar_id or settings.google_calendar_id or "primary").strip()
    conn_service = get_calendar_connection_service()
    service = get_calendar_service(account=account)
    if not service:
        return {"status": "error", "message": "A conexão com o Google Agenda não está ativa."}

    resolved_account = conn_service.resolve_account(account)
    tz = get_user_timezone()
    tz_name = getattr(settings, "google_calendar_timezone", DEFAULT_TIMEZONE) or DEFAULT_TIMEZONE
    now = get_now_in_user_tz()

    try:
        existing = service.events().get(calendarId=target_cal, eventId=event_id.strip()).execute()
    except Exception as exc:
        logger.error("Failed to load event %s for editing: %s", event_id, exc)
        return {"status": "error", "message": "Não encontrei esse compromisso na sua agenda."}

    is_recurring = bool(existing.get("recurringEventId") or existing.get("recurrence"))
    has_attendees = bool(existing.get("attendees"))
    scope_norm = (recurrence_scope or "").strip().lower()

    if is_recurring and scope_norm not in ("this", "following", "all"):
        return {
            "status": "recurrence_scope_required",
            "event_id": event_id,
            "message": (
                "Este é um compromisso recorrente. Você quer alterar só esta ocorrência, "
                "esta e as seguintes, ou todas?"
            ),
        }

    # Check conflicts when start or end time is being changed
    new_start_dt: Optional[datetime] = None
    new_end_dt: Optional[datetime] = None
    if start:
        new_start_dt = parse_datetime_flexible(start)
        if end:
            new_end_dt = parse_datetime_flexible(end, default_hour=(new_start_dt.hour + 1) % 24)
        else:
            # Preserve original duration if possible
            orig_start_str = (existing.get("start") or {}).get("dateTime")
            orig_end_str = (existing.get("end") or {}).get("dateTime")
            if orig_start_str and orig_end_str:
                try:
                    os_dt = datetime.fromisoformat(orig_start_str.replace("Z", "+00:00"))
                    oe_dt = datetime.fromisoformat(orig_end_str.replace("Z", "+00:00"))
                    new_end_dt = new_start_dt + max(timedelta(minutes=15), (oe_dt - os_dt))
                except Exception:
                    new_end_dt = new_start_dt + timedelta(hours=1)
            else:
                new_end_dt = new_start_dt + timedelta(hours=1)

        if not force_conflict:
            try:
                day_min = datetime.combine(new_start_dt.date() - timedelta(days=1), dt_time(0, 0, 0), tzinfo=tz)
                day_max = datetime.combine(new_end_dt.date() + timedelta(days=1), dt_time(23, 59, 59), tzinfo=tz)
                list_resp = (
                    service.events()
                    .list(
                        calendarId=target_cal,
                        timeMin=day_min.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                        timeMax=day_max.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                        singleEvents=True,
                    )
                    .execute()
                )
                conflicts = detect_event_conflicts(
                    events=list_resp.get("items", []) or [],
                    start_dt=new_start_dt,
                    end_dt=new_end_dt,
                    account_email=resolved_account,
                    exclude_event_id=event_id.strip(),
                )
                if conflicts:
                    dur_mins = max(15, int((new_end_dt - new_start_dt).total_seconds() // 60))
                    suggestions = suggest_free_business_slots(
                        events=list_resp.get("items", []) or [],
                        desired_start=new_start_dt,
                        duration_minutes=dur_mins,
                        account_email=resolved_account,
                        exclude_event_id=event_id.strip(),
                        max_suggestions=3,
                    )
                    conflict_names = ", ".join(c["title"] for c in conflicts[:2])
                    sug_spoken = ", ".join(s["spoken"] for s in suggestions)
                    msg = f"Você já tem {conflict_names} no novo horário. Quer mover mesmo assim"
                    msg += f", ou prefere: {sug_spoken}?" if sug_spoken else ", ou prefere outro horário?"
                    return {
                        "status": "conflict_detected",
                        "conflicts": conflicts,
                        "suggested_slots": suggestions,
                        "message": msg,
                    }
            except Exception as exc:
                logger.debug("Conflict check on edit_event skipped: %s", exc)

    # High-impact confirmation gate for recurring events or events with attendees
    if (is_recurring or has_attendees) and not _confirmed:
        current_title = wrap_untrusted_event_field(existing.get("summary") or "compromisso", max_len=80, delimit=False)
        impact_notes = []
        if has_attendees:
            impact_notes.append("os convidados serão notificados")
        if is_recurring:
            scope_pt = {
                "this": "apenas esta ocorrência",
                "following": "esta e as próximas ocorrências",
                "all": "todas as ocorrências da série",
            }.get(scope_norm, "o evento recorrente")
            impact_notes.append(f"isso alterará {scope_pt}")
        impact_str = " e ".join(impact_notes)
        spoken_summary = f"Alterar {current_title} ({impact_str}). Você confirma?"

        proposal = get_calendar_confirmation_manager().create_proposal(
            action="edit_event",
            payload={
                "event_id": event_id,
                "calendar_id": target_cal,
                "title": title,
                "start": start,
                "end": end,
                "description": description,
                "location": location,
                "attendees": attendees,
                "reminders": reminders,
                "recurrence": recurrence,
                "add_meet_link": add_meet_link,
                "recurrence_scope": scope_norm or None,
                "force_conflict": True,
                "account": account,
            },
            summary_spoken=spoken_summary,
        )
        return {
            "status": "confirmation_required",
            "proposal_id": proposal.proposal_id,
            "expires_in_seconds": 60,
            "message": spoken_summary,
        }

    # Execute Adjustment #5: Recurrence "following" ("esta e as seguintes") split
    if is_recurring and scope_norm == "following":
        try:
            master_id = existing.get("recurringEventId") or existing["id"]
            master_event = (
                existing
                if master_id == existing.get("id")
                else service.events().get(calendarId=target_cal, eventId=master_id).execute()
            )
            orig_start_raw = (existing.get("start") or {}).get("dateTime") or (existing.get("start") or {}).get("date")
            if orig_start_raw:
                inst_start_dt = parse_datetime_flexible(orig_start_raw)
            else:
                inst_start_dt = new_start_dt or now

            # Step 1: Truncate original master series with UNTIL = instance_start - 1 second
            until_utc = inst_start_dt.astimezone(timezone.utc) - timedelta(seconds=1)
            master_recurrence = master_event.get("recurrence") or ["RRULE:FREQ=WEEKLY"]
            master_event["recurrence"] = update_rrule_with_until(master_recurrence, until_utc)
            service.events().patch(
                calendarId=target_cal,
                eventId=master_id,
                body={"recurrence": master_event["recurrence"]},
            ).execute()

            # Step 2: Create a new recurring series starting from the edited instance
            eff_start = new_start_dt or inst_start_dt
            eff_end = new_end_dt or (eff_start + timedelta(hours=1))
            new_series_rules = recurrence or strip_until_from_rrule(master_recurrence)
            new_body: Dict[str, Any] = {
                "summary": (title.strip() if title else existing.get("summary", "Compromisso")),
                "start": {"dateTime": eff_start.isoformat(), "timeZone": tz_name},
                "end": {"dateTime": eff_end.isoformat(), "timeZone": tz_name},
                "recurrence": new_series_rules,
            }
            if description is not None:
                new_body["description"] = description
            elif existing.get("description"):
                new_body["description"] = existing["description"]
            if location is not None:
                new_body["location"] = location
            elif existing.get("location"):
                new_body["location"] = existing["location"]

            created_split = service.events().insert(calendarId=target_cal, body=new_body).execute()
            spoken_new = format_spoken_datetime_pt(eff_start, reference_now=now)
            return {
                "status": "success",
                "split_recurring_series": True,
                "truncated_master_id": master_id,
                "new_series_event_id": created_split.get("id", ""),
                "message": f"Pronto, atualizei esta e as próximas ocorrências para {spoken_new}.",
            }
        except Exception as exc:
            logger.error("Failed to split recurring event series: %s", exc)
            return {
                "status": "error",
                "message": "Não consegui dividir e atualizar as próximas ocorrências desse evento.",
            }

    # Standard update ("this", "all", or non-recurring)
    target_update_id = (
        existing.get("recurringEventId")
        if (is_recurring and scope_norm == "all" and existing.get("recurringEventId"))
        else existing["id"]
    )

    patch_body: Dict[str, Any] = {}
    if title and title.strip():
        patch_body["summary"] = title.strip()
    if new_start_dt and new_end_dt:
        patch_body["start"] = {"dateTime": new_start_dt.isoformat(), "timeZone": tz_name}
        patch_body["end"] = {"dateTime": new_end_dt.isoformat(), "timeZone": tz_name}
    if description is not None:
        patch_body["description"] = description.strip()
    if location is not None:
        patch_body["location"] = location.strip()
    if attendees is not None:
        patch_body["attendees"] = [{"email": em.strip()} for em in attendees if "@" in em]
    if reminders is not None:
        patch_body["reminders"] = {
            "useDefault": False,
            "overrides": [{"method": "popup", "minutes": max(0, int(reminders))}],
        }
    if recurrence is not None:
        patch_body["recurrence"] = [r if r.upper().startswith("RRULE:") else f"RRULE:{r}" for r in recurrence]

    try:
        updated = (
            service.events()
            .patch(
                calendarId=target_cal,
                eventId=target_update_id,
                body=patch_body,
                sendUpdates="all" if has_attendees else "none",
            )
            .execute()
        )
        updated_title = updated.get("summary") or title or existing.get("summary") or "compromisso"
        if new_start_dt:
            spoken_t = format_spoken_datetime_pt(new_start_dt, reference_now=now)
            msg = f"Pronto, atualizei {updated_title} para {spoken_t}."
        else:
            msg = f"Pronto, atualizei os dados de {updated_title}."
        return {
            "status": "success",
            "event": {
                "id": updated.get("id", target_update_id),
                "title": updated_title,
            },
            "message": msg,
        }
    except Exception as exc:
        logger.error("Failed to edit Google Calendar event %s: %s", event_id, exc)
        return {"status": "error", "message": "Não consegui atualizar esse compromisso agora."}


def delete_event(
    event_id: str,
    calendar_id: str = "primary",
    recurrence_scope: Optional[str] = None,
    account: Optional[str] = None,
    _confirmed: bool = False,
) -> Dict[str, Any]:
    """
    Delete an event from Google Calendar.
    - Always requires explicit user confirmation via `confirm_action` (60s TTL, single-use).
    - For recurring events, asks whether to delete only this occurrence ('this'),
      this and following ('following' via UNTIL truncation), or the entire series ('all').
    """
    if not event_id or not event_id.strip():
        return {"status": "error", "message": "Qual compromisso você quer apagar?"}

    settings = get_settings()
    target_cal = (calendar_id or settings.google_calendar_id or "primary").strip()
    service = get_calendar_service(account=account)
    if not service:
        return {"status": "error", "message": "A conexão com o Google Agenda não está ativa."}

    now = get_now_in_user_tz()
    try:
        existing = service.events().get(calendarId=target_cal, eventId=event_id.strip()).execute()
    except Exception as exc:
        logger.error("Failed to fetch event %s before deletion: %s", event_id, exc)
        return {"status": "error", "message": "Não encontrei esse compromisso na sua agenda."}

    ev_title = wrap_untrusted_event_field(existing.get("summary") or "Compromisso sem título", max_len=90, delimit=False)
    start_raw = (existing.get("start") or {}).get("dateTime") or (existing.get("start") or {}).get("date") or ""
    is_all_day = "date" in (existing.get("start") or {}) and "dateTime" not in (existing.get("start") or {})
    spoken_when = start_raw
    if start_raw:
        try:
            dt_parsed = parse_datetime_flexible(start_raw)
            spoken_when = format_spoken_datetime_pt(dt_parsed, reference_now=now, all_day=is_all_day)
        except Exception:
            pass

    is_recurring = bool(existing.get("recurringEventId") or existing.get("recurrence"))
    scope_norm = (recurrence_scope or "").strip().lower()

    if is_recurring and scope_norm not in ("this", "following", "all"):
        return {
            "status": "recurrence_scope_required",
            "event_id": event_id,
            "title": ev_title,
            "spoken_time": spoken_when,
            "message": (
                f"O compromisso {ev_title} é recorrente. Você quer apagar só esta ocorrência, "
                "esta e as seguintes, ou todas?"
            ),
        }

    if not _confirmed:
        spoken_prompt = f"Você confirma a exclusão do compromisso {ev_title}, marcado para {spoken_when}?"
        proposal = get_calendar_confirmation_manager().create_proposal(
            action="delete_event",
            payload={
                "event_id": event_id.strip(),
                "calendar_id": target_cal,
                "recurrence_scope": scope_norm or None,
                "account": account,
            },
            summary_spoken=spoken_prompt,
        )
        return {
            "status": "confirmation_required",
            "proposal_id": proposal.proposal_id,
            "title": ev_title,
            "spoken_time": spoken_when,
            "expires_in_seconds": 60,
            "message": spoken_prompt,
        }

    try:
        if is_recurring and scope_norm == "following":
            master_id = existing.get("recurringEventId") or existing["id"]
            master_ev = (
                existing
                if master_id == existing.get("id")
                else service.events().get(calendarId=target_cal, eventId=master_id).execute()
            )
            inst_dt = parse_datetime_flexible(start_raw) if start_raw else now
            until_utc = inst_dt.astimezone(timezone.utc) - timedelta(seconds=1)
            new_rules = update_rrule_with_until(master_ev.get("recurrence") or ["RRULE:FREQ=WEEKLY"], until_utc)
            service.events().patch(
                calendarId=target_cal,
                eventId=master_id,
                body={"recurrence": new_rules},
            ).execute()
            return {
                "status": "success",
                "deleted_event_id": event_id.strip(),
                "recurrence_scope": "following",
                "message": f"Pronto, apaguei esta e as próximas ocorrências de {ev_title}.",
            }

        target_del_id = (
            existing.get("recurringEventId")
            if (is_recurring and scope_norm == "all" and existing.get("recurringEventId"))
            else existing["id"]
        )
        service.events().delete(calendarId=target_cal, eventId=target_del_id).execute()
        return {
            "status": "success",
            "deleted_event_id": target_del_id,
            "message": f"Pronto, apaguei o compromisso {ev_title} da sua agenda.",
        }
    except Exception as exc:
        logger.error("Failed to delete event %s: %s", event_id, exc)
        return {"status": "error", "message": f"Não consegui apagar o compromisso {ev_title}."}


# ==============================================================================
# 3. Calendar Management Tools (list_calendars, create_calendar, edit_calendar, delete_calendar)
# ==============================================================================


def list_calendars(account: Optional[str] = None) -> Dict[str, Any]:
    """List all calendars available in the user's Google Calendar account."""
    service = get_calendar_service(account=account)
    if not service:
        return {"status": "error", "message": "A conexão com o Google Agenda não está ativa."}

    try:
        resp = service.calendarList().list().execute()
        items = resp.get("items", []) or []
        calendars = []
        for cal in items:
            calendars.append(
                {
                    "id": cal.get("id", ""),
                    "name": wrap_untrusted_event_field(cal.get("summary") or "Sem nome", max_len=80, delimit=False),
                    "primary": bool(cal.get("primary", False)),
                    "access_role": cal.get("accessRole", ""),
                    "timezone": cal.get("timeZone", DEFAULT_TIMEZONE),
                }
            )
        names_spoken = ", ".join(c["name"] for c in calendars[:5])
        return {
            "status": "success",
            "count": len(calendars),
            "calendars": calendars,
            "message": f"Você tem {len(calendars)} agendas disponíveis: {names_spoken}.",
        }
    except Exception as exc:
        logger.error("Failed to list calendars: %s", exc)
        return {"status": "error", "message": "Não consegui listar as suas agendas agora."}


def create_calendar(
    name: str,
    description: Optional[str] = None,
    timezone_name: Optional[str] = None,
    account: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new secondary calendar in Google Calendar."""
    if not name or not name.strip():
        return {"status": "error", "message": "Qual nome você quer dar para a nova agenda?"}

    service = get_calendar_service(account=account)
    if not service:
        return {"status": "error", "message": "A conexão com o Google Agenda não está ativa."}

    settings = get_settings()
    tz_str = (timezone_name or getattr(settings, "google_calendar_timezone", DEFAULT_TIMEZONE) or DEFAULT_TIMEZONE).strip()
    body: Dict[str, Any] = {
        "summary": name.strip(),
        "timeZone": tz_str,
    }
    if description and description.strip():
        body["description"] = description.strip()

    try:
        created = service.calendars().insert(body=body).execute()
        return {
            "status": "success",
            "calendar": {
                "id": created.get("id", ""),
                "name": created.get("summary", name.strip()),
                "timezone": created.get("timeZone", tz_str),
            },
            "message": f"Pronto, criei a agenda {name.strip()}.",
        }
    except Exception as exc:
        logger.error("Failed to create calendar '%s': %s", name, exc)
        return {"status": "error", "message": f"Não consegui criar a agenda {name.strip()}."}


def edit_calendar(
    calendar_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    timezone_name: Optional[str] = None,
    account: Optional[str] = None,
) -> Dict[str, Any]:
    """Edit metadata (name, description, or timezone) of an existing calendar."""
    if not calendar_id or not calendar_id.strip():
        return {"status": "error", "message": "Qual agenda você quer editar?"}

    service = get_calendar_service(account=account)
    if not service:
        return {"status": "error", "message": "A conexão com o Google Agenda não está ativa."}

    patch_body: Dict[str, Any] = {}
    if name and name.strip():
        patch_body["summary"] = name.strip()
    if description is not None:
        patch_body["description"] = description.strip()
    if timezone_name and timezone_name.strip():
        patch_body["timeZone"] = timezone_name.strip()

    try:
        updated = service.calendars().patch(calendarId=calendar_id.strip(), body=patch_body).execute()
        new_name = updated.get("summary", name or calendar_id)
        return {
            "status": "success",
            "calendar": {
                "id": updated.get("id", calendar_id),
                "name": new_name,
            },
            "message": f"Pronto, atualizei a agenda {new_name}.",
        }
    except Exception as exc:
        logger.error("Failed to edit calendar %s: %s", calendar_id, exc)
        return {"status": "error", "message": "Não consegui atualizar os dados dessa agenda."}


def delete_calendar(
    calendar_id: str,
    account: Optional[str] = None,
    _confirmed: bool = False,
) -> Dict[str, Any]:
    """
    Delete a secondary calendar.
    - Adjustment #2: Strictly blocks deletion of the primary calendar ('primary').
    - Requires explicit confirmation via `confirm_action` where the user speaks
      the name of the secondary calendar (matched accent/case-insensitively).
    """
    conn_service = get_calendar_connection_service()
    resolved_account = conn_service.resolve_account(account)

    if is_primary_calendar(calendar_id, account_email=resolved_account):
        return {
            "status": "forbidden_primary_calendar",
            "message": "A sua agenda principal não pode ser apagada por segurança. Só agendas secundárias podem ser excluídas.",
        }

    service = get_calendar_service(account=account)
    if not service:
        return {"status": "error", "message": "A conexão com o Google Agenda não está ativa."}

    try:
        cal_meta = service.calendarList().get(calendarId=calendar_id.strip()).execute()
    except Exception:
        try:
            cal_meta = service.calendars().get(calendarId=calendar_id.strip()).execute()
        except Exception as exc:
            logger.error("Failed to inspect calendar %s before deletion: %s", calendar_id, exc)
            return {"status": "error", "message": "Não encontrei essa agenda secundária."}

    if is_primary_calendar(calendar_id, account_email=resolved_account, calendar_meta=cal_meta):
        return {
            "status": "forbidden_primary_calendar",
            "message": "A sua agenda principal não pode ser apagada por segurança.",
        }

    cal_name = str(cal_meta.get("summary") or calendar_id).strip()

    if not _confirmed:
        spoken_prompt = (
            f"Atenção: apagar a agenda {cal_name} removerá todos os eventos dela permanentemente. "
            f"Para confirmar, diga que confirma apagar a agenda {cal_name}."
        )
        proposal = get_calendar_confirmation_manager().create_proposal(
            action="delete_calendar",
            payload={
                "calendar_id": calendar_id.strip(),
                "account": account,
            },
            summary_spoken=spoken_prompt,
            required_calendar_name=cal_name,
        )
        return {
            "status": "confirmation_required",
            "proposal_id": proposal.proposal_id,
            "calendar_name": cal_name,
            "expires_in_seconds": 60,
            "message": spoken_prompt,
        }

    try:
        service.calendars().delete(calendarId=calendar_id.strip()).execute()
        return {
            "status": "success",
            "deleted_calendar_id": calendar_id.strip(),
            "calendar_name": cal_name,
            "message": f"Pronto, a agenda secundária {cal_name} foi apagada.",
        }
    except Exception as exc:
        logger.error("Failed to delete secondary calendar %s: %s", calendar_id, exc)
        return {"status": "error", "message": f"Não consegui apagar a agenda {cal_name}."}


# ==============================================================================
# 4. Legacy Compatibility Wrappers (Used by Daily Briefing & Existing Tests)
# ==============================================================================


def get_calendar_events(
    period: str = "today",
    max_results: int = 10,
    search_query: Optional[str] = None,
) -> Dict[str, Any]:
    """Legacy wrapper around list_events preserving full backward compatibility."""
    res = list_events(
        calendar_id="primary",
        time_min=period,
        query=search_query,
        max_results=max_results,
    )
    if res.get("status") == "success":
        res["period"] = period
        # Return all fetched events in 'events' for briefing and legacy callers
        if "all_events" in res:
            res["events"] = res["all_events"]
    return res


def create_calendar_event(
    summary: str,
    start_time: str,
    duration_minutes: int = 60,
    description: Optional[str] = None,
    location: Optional[str] = None,
) -> Dict[str, Any]:
    """Legacy wrapper around create_event preserving full backward compatibility."""
    start_dt = parse_datetime_flexible(start_time)
    end_dt = start_dt + timedelta(minutes=max(15, int(duration_minutes or 60)))
    res = create_event(
        title=summary,
        start=start_dt.isoformat(),
        end=end_dt.isoformat(),
        description=description,
        location=location,
        force_conflict=True,
    )
    if res.get("status") == "success" and "event" in res:
        res["event"]["summary"] = res["event"].get("title", summary)
    return res


# ==============================================================================
# 5. Gemini Live Tool Calling Declarations & Dispatcher
# ==============================================================================

GOOGLE_CALENDAR_FUNCTION_DECLARATIONS: List[Dict[str, Any]] = [
    {
        "name": "list_events",
        "description": (
            "Consulta compromissos no Google Agenda por período ou termo de busca. "
            "Nota: create_event e edit_event já verificam conflitos sozinhos; não chame list_events antes só para checar conflito."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "calendar_id": {
                    "type": "STRING",
                    "description": "Identificador da agenda (padrão: 'primary').",
                },
                "time_min": {
                    "type": "STRING",
                    "description": "Início do período em ISO 8601 com fuso horário, ou 'today', 'tomorrow', 'week'.",
                },
                "time_max": {
                    "type": "STRING",
                    "description": "Fim do período em ISO 8601 com fuso horário (opcional).",
                },
                "query": {
                    "type": "STRING",
                    "description": "Texto opcional para filtrar compromissos pelo título ou descrição.",
                },
                "max_results": {
                    "type": "INTEGER",
                    "description": "Quantidade máxima de eventos a buscar (padrão: 20).",
                },
                "page_offset": {
                    "type": "INTEGER",
                    "description": "Deslocamento para ler os próximos eventos quando houver mais de 3 (padrão: 0).",
                },
                "account": {
                    "type": "STRING",
                    "description": "Conta de e-mail opcional quando o usuário possuir múltiplas contas conectadas.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "create_event",
        "description": (
            "Cria um novo compromisso no Google Agenda. Já verifica conflitos automaticamente e aplica os padrões "
            "(duração de 1 hora, lembrete 10 minutos antes, agenda principal, ou dia inteiro se informado apenas a data)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "title": {
                    "type": "STRING",
                    "description": "Título do compromisso.",
                },
                "start": {
                    "type": "STRING",
                    "description": "Data e hora de início em ISO 8601 (ex: '2026-11-05T14:00:00-03:00') ou apenas data ('2026-11-05') para evento de dia inteiro.",
                },
                "end": {
                    "type": "STRING",
                    "description": "Data e hora de término em ISO 8601 (opcional; padrão: 1 hora após o início).",
                },
                "calendar_id": {
                    "type": "STRING",
                    "description": "Agenda onde criar (padrão: 'primary').",
                },
                "description": {
                    "type": "STRING",
                    "description": "Descrição ou pauta opcional.",
                },
                "location": {
                    "type": "STRING",
                    "description": "Local ou endereço opcional.",
                },
                "attendees": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": "Lista opcional de nomes ou e-mails de convidados.",
                },
                "reminders": {
                    "type": "INTEGER",
                    "description": "Minutos antes para o lembrete (padrão: 10).",
                },
                "recurrence": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": "Regras RRULE opcionais para evento recorrente (ex: ['RRULE:FREQ=WEEKLY;BYDAY=MO']).",
                },
                "add_meet_link": {
                    "type": "BOOLEAN",
                    "description": "Se verdadeiro, gera link do Google Meet automaticamente.",
                },
                "all_day": {
                    "type": "BOOLEAN",
                    "description": "Se verdadeiro, cria como evento de dia inteiro.",
                },
                "force_conflict": {
                    "type": "BOOLEAN",
                    "description": "Se verdadeiro, cria mesmo havendo outro compromisso no horário (use apenas após o usuário confirmar).",
                },
                "attendees_confirmed": {
                    "type": "BOOLEAN",
                    "description": "Se verdadeiro, confirma o envio de convite por e-mail aos convidados.",
                },
                "account": {
                    "type": "STRING",
                    "description": "Conta de e-mail opcional.",
                },
            },
            "required": ["title", "start"],
        },
    },
    {
        "name": "edit_event",
        "description": (
            "Edita ou move um compromisso existente no Google Agenda. Verifica conflitos sozinho ao mudar horário. "
            "Para eventos recorrentes, exige recurrence_scope ('this', 'following' ou 'all')."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "event_id": {
                    "type": "STRING",
                    "description": "Identificador do evento obtido via list_events.",
                },
                "calendar_id": {
                    "type": "STRING",
                    "description": "Identificador da agenda (padrão: 'primary').",
                },
                "title": {
                    "type": "STRING",
                    "description": "Novo título opcional.",
                },
                "start": {
                    "type": "STRING",
                    "description": "Nova data e hora de início em ISO 8601.",
                },
                "end": {
                    "type": "STRING",
                    "description": "Nova data e hora de término em ISO 8601.",
                },
                "description": {
                    "type": "STRING",
                    "description": "Nova descrição opcional.",
                },
                "location": {
                    "type": "STRING",
                    "description": "Novo local opcional.",
                },
                "attendees": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": "Lista atualizada de e-mails de convidados.",
                },
                "reminders": {
                    "type": "INTEGER",
                    "description": "Minutos antes para o lembrete.",
                },
                "recurrence": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": "Novas regras RRULE.",
                },
                "recurrence_scope": {
                    "type": "STRING",
                    "enum": ["this", "following", "all"],
                    "description": "Escopo para evento recorrente: 'this' (só esta), 'following' (esta e as seguintes), 'all' (todas).",
                },
                "force_conflict": {
                    "type": "BOOLEAN",
                    "description": "Se verdadeiro, move o evento mesmo havendo conflito de horário.",
                },
                "account": {
                    "type": "STRING",
                    "description": "Conta de e-mail opcional.",
                },
            },
            "required": ["event_id"],
        },
    },
    {
        "name": "delete_event",
        "description": (
            "Solicita a exclusão de um compromisso no Google Agenda. Gera uma proposta pendente que exige confirmação verbal "
            "do usuário seguida da chamada a confirm_action."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "event_id": {
                    "type": "STRING",
                    "description": "Identificador do evento obtido via list_events.",
                },
                "calendar_id": {
                    "type": "STRING",
                    "description": "Identificador da agenda (padrão: 'primary').",
                },
                "recurrence_scope": {
                    "type": "STRING",
                    "enum": ["this", "following", "all"],
                    "description": "Escopo para evento recorrente: 'this' (só esta), 'following' (esta e as seguintes), 'all' (todas).",
                },
                "account": {
                    "type": "STRING",
                    "description": "Conta de e-mail opcional.",
                },
            },
            "required": ["event_id"],
        },
    },
    {
        "name": "list_calendars",
        "description": "Lista todas as agendas disponíveis na conta do usuário (principal e secundárias).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "account": {
                    "type": "STRING",
                    "description": "Conta de e-mail opcional.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "create_calendar",
        "description": "Cria uma nova agenda secundária no Google Agenda.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "name": {
                    "type": "STRING",
                    "description": "Nome da nova agenda secundária.",
                },
                "description": {
                    "type": "STRING",
                    "description": "Descrição opcional da agenda.",
                },
                "timezone_name": {
                    "type": "STRING",
                    "description": "Fuso horário (padrão: 'America/Fortaleza').",
                },
                "account": {
                    "type": "STRING",
                    "description": "Conta de e-mail opcional.",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "edit_calendar",
        "description": "Renomeia ou altera a descrição/fuso horário de uma agenda existente.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "calendar_id": {
                    "type": "STRING",
                    "description": "Identificador da agenda.",
                },
                "name": {
                    "type": "STRING",
                    "description": "Novo nome para a agenda.",
                },
                "description": {
                    "type": "STRING",
                    "description": "Nova descrição opcional.",
                },
                "timezone_name": {
                    "type": "STRING",
                    "description": "Novo fuso horário opcional.",
                },
                "account": {
                    "type": "STRING",
                    "description": "Conta de e-mail opcional.",
                },
            },
            "required": ["calendar_id"],
        },
    },
    {
        "name": "delete_calendar",
        "description": (
            "Solicita a exclusão de uma agenda secundária. A agenda principal ('primary') é bloqueada e nunca pode ser apagada. "
            "Exige confirmação dizendo o nome da agenda via confirm_action."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "calendar_id": {
                    "type": "STRING",
                    "description": "Identificador da agenda secundária.",
                },
                "account": {
                    "type": "STRING",
                    "description": "Conta de e-mail opcional.",
                },
            },
            "required": ["calendar_id"],
        },
    },
    {
        "name": "get_current_time",
        "description": (
            "Retorna a data e hora exatas atuais no fuso horário do usuário (America/Fortaleza), o dia da semana calculado "
            "em código e a tabela dos próximos 7 dias. Chame sempre que precisar confirmar o dia da semana ou se a conversa passar da meia-noite."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "timezone_name": {
                    "type": "STRING",
                    "description": "Fuso horário opcional (padrão: 'America/Fortaleza').",
                },
            },
            "required": [],
        },
    },
    {
        "name": "confirm_action",
        "description": (
            "Confirma e executa uma ação destrutiva ou de alto impacto pendente (proposal_id) após o usuário confirmar verbalmente. "
            "Propostas expiram em 60 segundos e são de uso único."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "proposal_id": {
                    "type": "STRING",
                    "description": "Código da proposta pendente retornado por delete_event, edit_event ou delete_calendar.",
                },
                "confirmed_name": {
                    "type": "STRING",
                    "description": "Nome da agenda falado pelo usuário (obrigatório apenas ao excluir uma agenda secundária).",
                },
            },
            "required": ["proposal_id"],
        },
    },
    {
        "name": "check_calendar_connection",
        "description": "Verifica se a autenticação com o Google Agenda está ativa e saudável.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "account": {
                    "type": "STRING",
                    "description": "Conta de e-mail opcional.",
                },
            },
            "required": [],
        },
    },
    # Legacy aliases preserved for backward compatibility with Daily Briefing & existing tests
    {
        "name": "get_calendar_events",
        "description": "Alias legado para consulta rápida de eventos da agenda ('today', 'tomorrow', 'week').",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "period": {
                    "type": "STRING",
                    "enum": ["today", "tomorrow", "week"],
                    "description": "Período de consulta ('today', 'tomorrow' ou 'week').",
                },
                "max_results": {
                    "type": "INTEGER",
                    "description": "Número máximo de compromissos.",
                },
                "search_query": {
                    "type": "STRING",
                    "description": "Termo opcional para filtrar.",
                },
            },
            "required": ["period"],
        },
    },
    {
        "name": "create_calendar_event",
        "description": "Alias legado para criação rápida de evento no Google Agenda.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "summary": {"type": "STRING", "description": "Título do evento."},
                "start_time": {"type": "STRING", "description": "Data/hora de início."},
                "duration_minutes": {"type": "INTEGER", "description": "Duração em minutos."},
                "description": {"type": "STRING", "description": "Descrição opcional."},
                "location": {"type": "STRING", "description": "Local opcional."},
            },
            "required": ["summary", "start_time"],
        },
    },
]

CALENDAR_TOOL_NAMES = {decl["name"] for decl in GOOGLE_CALENDAR_FUNCTION_DECLARATIONS}


def dispatch_calendar_tool(tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatch any Google Calendar tool call safely."""
    args = dict(tool_args or {})
    if tool_name == "list_events":
        return list_events(
            calendar_id=args.get("calendar_id", "primary"),
            time_min=args.get("time_min"),
            time_max=args.get("time_max"),
            query=args.get("query"),
            max_results=int(args.get("max_results", 20)),
            page_offset=int(args.get("page_offset", 0)),
            account=args.get("account"),
        )
    if tool_name == "create_event":
        return create_event(
            title=args.get("title", ""),
            start=args.get("start", ""),
            end=args.get("end"),
            calendar_id=args.get("calendar_id", "primary"),
            description=args.get("description"),
            location=args.get("location"),
            attendees=args.get("attendees"),
            reminders=args.get("reminders", 10),
            recurrence=args.get("recurrence"),
            add_meet_link=bool(args.get("add_meet_link", False)),
            all_day=bool(args.get("all_day", False)),
            force_conflict=bool(args.get("force_conflict", False)),
            attendees_confirmed=bool(args.get("attendees_confirmed", False)),
            account=args.get("account"),
        )
    if tool_name == "edit_event":
        return edit_event(
            event_id=args.get("event_id", ""),
            calendar_id=args.get("calendar_id", "primary"),
            title=args.get("title"),
            start=args.get("start"),
            end=args.get("end"),
            description=args.get("description"),
            location=args.get("location"),
            attendees=args.get("attendees"),
            reminders=args.get("reminders"),
            recurrence=args.get("recurrence"),
            add_meet_link=args.get("add_meet_link"),
            recurrence_scope=args.get("recurrence_scope"),
            force_conflict=bool(args.get("force_conflict", False)),
            account=args.get("account"),
        )
    if tool_name == "delete_event":
        return delete_event(
            event_id=args.get("event_id", ""),
            calendar_id=args.get("calendar_id", "primary"),
            recurrence_scope=args.get("recurrence_scope"),
            account=args.get("account"),
        )
    if tool_name == "list_calendars":
        return list_calendars(account=args.get("account"))
    if tool_name == "create_calendar":
        return create_calendar(
            name=args.get("name", ""),
            description=args.get("description"),
            timezone_name=args.get("timezone_name"),
            account=args.get("account"),
        )
    if tool_name == "edit_calendar":
        return edit_calendar(
            calendar_id=args.get("calendar_id", ""),
            name=args.get("name"),
            description=args.get("description"),
            timezone_name=args.get("timezone_name"),
            account=args.get("account"),
        )
    if tool_name == "delete_calendar":
        return delete_calendar(
            calendar_id=args.get("calendar_id", ""),
            account=args.get("account"),
        )
    if tool_name == "get_current_time":
        return get_current_time(timezone_name=args.get("timezone_name"))
    if tool_name == "confirm_action":
        return confirm_action(
            proposal_id=args.get("proposal_id", ""),
            confirmed_name=args.get("confirmed_name"),
            session_id=args.get("session_id"),
        )
    if tool_name == "check_calendar_connection":
        return check_calendar_connection(account=args.get("account"))
    if tool_name == "get_calendar_events":
        return get_calendar_events(
            period=args.get("period", "today"),
            max_results=int(args.get("max_results", 10)),
            search_query=args.get("search_query"),
        )
    if tool_name == "create_calendar_event":
        return create_calendar_event(
            summary=args.get("summary", ""),
            start_time=args.get("start_time", ""),
            duration_minutes=int(args.get("duration_minutes", 60)),
            description=args.get("description"),
            location=args.get("location"),
        )
    return {"status": "error", "message": f"Ferramenta de agenda desconhecida: {tool_name}"}
