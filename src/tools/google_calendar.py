"""Google Calendar and Workspace integration tools for Aton (Phase 4)."""

from datetime import datetime, timedelta, timezone
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple
import urllib.parse
import urllib.request
import urllib.error

from src.config import settings

logger = logging.getLogger(__name__)

CALENDAR_SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly",
]


def _get_credentials():
    """Load or refresh Google OAuth2 credentials for Calendar access."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
    except ImportError:
        logger.warning("google-auth not installed.")
        return None

    creds = None
    token_path = settings.google_calendar_token_path

    if os.path.exists(token_path):
        try:
            creds = Credentials.from_authorized_user_file(token_path, CALENDAR_SCOPES)
        except Exception as exc:
            logger.warning(f"Error loading {token_path}: {exc}")

    # If expired, refresh token
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open(token_path, "w", encoding="utf-8") as f:
                f.write(creds.to_json())
            logger.info("Google Calendar OAuth2 credentials refreshed.")
        except Exception as exc:
            logger.error(f"Error refreshing Google Calendar token: {exc}")
            creds = None

    return creds


def parse_datetime_flexible(dt_str: Optional[str], is_end_time: bool = False, base_start: Optional[datetime] = None) -> datetime:
    """Parse flexible natural language or ISO date/time into a timezone-aware datetime.
    
    Supports:
    - ISO strings (e.g. '2026-10-28T14:00:00', '2026-10-28T14:00:00Z', '2026-10-28')
    - Natural keywords: 'hoje', 'amanhã', 'today', 'tomorrow'
    - Relative hours: 'hoje às 15:00', 'amanhã às 10h', '14:30'
    """
    now = datetime.now().astimezone()

    if not dt_str:
        if is_end_time and base_start:
            return base_start + timedelta(hours=1)
        return now

    # 1. Try standard ISO parsing first
    clean_iso = dt_str.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(clean_iso)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=now.tzinfo)
        return parsed
    except ValueError:
        pass

    text = dt_str.strip().lower()

    # 2. Check for natural keywords ('hoje', 'amanhã', etc.)
    target_date = now.date()
    if "amanhã" in text or "amanha" in text or "tomorrow" in text:
        target_date = now.date() + timedelta(days=1)
    elif "hoje" in text or "today" in text:
        target_date = now.date()

    # Look for hour/minute pattern like '14:30', '15h', 'às 15:00', '9h30'
    time_match = re.search(r"(?:às\s*|as\s*)?(\d{1,2})(?:[:hH](\d{2})|h|H)?", text)
    if time_match and ("às" in text or "as" in text or ":" in text or "h" in text):
        hour = int(time_match.group(1))
        minute = int(time_match.group(2)) if time_match.group(2) else 0
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return datetime(
                year=target_date.year,
                month=target_date.month,
                day=target_date.day,
                hour=hour,
                minute=minute,
                second=0,
                tzinfo=now.tzinfo,
            )

    # Fallback to now or base_start + 1h
    if is_end_time and base_start:
        return base_start + timedelta(hours=1)
    return now


def get_calendar_events(
    time_min: Optional[str] = None,
    time_max: Optional[str] = None,
    max_results: int = 10,
    calendar_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Retrieve upcoming events from Google Calendar.

    Args:
        time_min: Start timestamp/date filter (ISO or 'hoje', 'amanhã'). Defaults to now.
        time_max: End timestamp/date filter. Defaults to 24 hours after time_min.
        max_results: Maximum events to return (default 10).
        calendar_id: Calendar ID (defaults to 'primary').
    """
    cal_id = calendar_id or settings.google_calendar_id or "primary"
    creds = _get_credentials()

    if not creds or not creds.valid:
        return {
            "status": "not_authenticated",
            "message": (
                "O Google Agenda ainda não está autenticado. Para sincronizar sua agenda com o Aton, "
                "coloque seu arquivo credentials.json baixado do Google Cloud Console na raiz do projeto. "
                "Consulte o passo a passo em docs/google_calendar.md."
            ),
            "events": [],
        }

    start_dt = parse_datetime_flexible(time_min)
    if time_max:
        end_dt = parse_datetime_flexible(time_max)
    else:
        # Default to end of next 24 hours
        end_dt = start_dt + timedelta(days=1)

    url = (
        f"https://www.googleapis.com/calendar/v3/calendars/{urllib.parse.quote(cal_id)}/events?"
        f"timeMin={urllib.parse.quote(start_dt.isoformat())}&"
        f"timeMax={urllib.parse.quote(end_dt.isoformat())}&"
        f"singleEvents=true&orderBy=startTime&maxResults={max_results}"
    )

    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {creds.token}"},
        method="GET",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        logger.error(f"Google Calendar API HTTP error: {err.code} {err.reason}")
        return {
            "status": "error",
            "message": f"Erro ao consultar o Google Agenda: código HTTP {err.code}.",
            "events": [],
        }
    except Exception as exc:
        logger.error(f"Error querying Google Calendar API: {exc}")
        return {
            "status": "error",
            "message": f"Não foi possível acessar seus compromissos no momento: {exc}",
            "events": [],
        }

    items = data.get("items", [])
    events_summary: List[Dict[str, Any]] = []

    for item in items:
        start_info = item.get("start", {})
        start_val = start_info.get("dateTime") or start_info.get("date") or ""
        end_info = item.get("end", {})
        end_val = end_info.get("dateTime") or end_info.get("date") or ""

        # Friendly hour formatting
        time_display = start_val
        try:
            dt = datetime.fromisoformat(start_val.replace("Z", "+00:00"))
            time_display = dt.strftime("%d/%m às %H:%M")
        except Exception:
            pass

        events_summary.append({
            "id": item.get("id"),
            "summary": item.get("summary", "Sem título"),
            "start": start_val,
            "end": end_val,
            "display_time": time_display,
            "location": item.get("location", ""),
            "description": item.get("description", ""),
        })

    # Generate spoken natural response
    if not events_summary:
        msg = "Você não tem nenhum compromisso agendado para este período, senhor."
    elif len(events_summary) == 1:
        ev = events_summary[0]
        msg = f"Você tem 1 compromisso na agenda: {ev['summary']} em {ev['display_time']}."
    else:
        ev_list_str = "; ".join(f"{e['summary']} em {e['display_time']}" for e in events_summary[:3])
        if len(events_summary) > 3:
            ev_list_str += f" e mais {len(events_summary) - 3} outros compromissos"
        msg = f"Você tem {len(events_summary)} compromissos encontrados: {ev_list_str}."

    return {
        "status": "success",
        "message": msg,
        "count": len(events_summary),
        "events": events_summary,
    }


def create_calendar_event(
    summary: str,
    start_time: str,
    end_time: Optional[str] = None,
    description: str = "",
    location: str = "",
    calendar_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new event in Google Calendar.

    Args:
        summary: Event title / summary (e.g. 'Reunião de Alinhamento', 'Dentista').
        start_time: Start date and time (ISO or relative 'hoje às 15:00', 'amanhã às 10h').
        end_time: End date and time (optional, defaults to 1 hour after start_time).
        description: Event description or agenda.
        location: Event physical location or video call link.
        calendar_id: Calendar ID (defaults to 'primary').
    """
    cal_id = calendar_id or settings.google_calendar_id or "primary"
    creds = _get_credentials()

    if not creds or not creds.valid:
        return {
            "status": "not_authenticated",
            "message": (
                "O Google Agenda ainda não está autenticado. Para agendar compromissos com o Aton, "
                "coloque seu arquivo credentials.json baixado do Google Cloud Console na raiz do projeto. "
                "Consulte o passo a passo em docs/google_calendar.md."
            ),
        }

    start_dt = parse_datetime_flexible(start_time)
    end_dt = parse_datetime_flexible(end_time, is_end_time=True, base_start=start_dt)

    # Ensure end time is strictly after start time
    if end_dt <= start_dt:
        end_dt = start_dt + timedelta(hours=1)

    payload = {
        "summary": summary,
        "description": description,
        "location": location,
        "start": {
            "dateTime": start_dt.isoformat(),
        },
        "end": {
            "dateTime": end_dt.isoformat(),
        },
    }

    url = f"https://www.googleapis.com/calendar/v3/calendars/{urllib.parse.quote(cal_id)}/events"
    body_data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body_data,
        headers={
            "Authorization": f"Bearer {creds.token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        logger.error(f"Google Calendar API create event HTTP error: {err.code} {err.reason}")
        return {
            "status": "error",
            "message": f"Erro ao criar evento no Google Agenda: código HTTP {err.code}.",
        }
    except Exception as exc:
        logger.error(f"Error creating event in Google Calendar API: {exc}")
        return {
            "status": "error",
            "message": f"Não foi possível salvar o compromisso na agenda: {exc}",
        }

    formatted_time = start_dt.strftime("%d/%m às %H:%M")
    return {
        "status": "success",
        "message": f"Compromisso '{summary}' agendado com sucesso para {formatted_time}, senhor.",
        "event_id": data.get("id"),
        "html_link": data.get("htmlLink"),
        "start": start_dt.isoformat(),
        "end": end_dt.isoformat(),
    }


def dispatch_calendar_tool(tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatch Google Calendar tool requests."""
    if tool_name == "get_calendar_events":
        return get_calendar_events(
            time_min=tool_args.get("time_min"),
            time_max=tool_args.get("time_max"),
            max_results=tool_args.get("max_results", 10),
            calendar_id=tool_args.get("calendar_id"),
        )
    elif tool_name == "create_calendar_event":
        return create_calendar_event(
            summary=tool_args.get("summary", "Novo Evento"),
            start_time=tool_args.get("start_time", "hoje"),
            end_time=tool_args.get("end_time"),
            description=tool_args.get("description", ""),
            location=tool_args.get("location", ""),
            calendar_id=tool_args.get("calendar_id"),
        )
    else:
        return {
            "status": "error",
            "message": f"Ferramenta do Google Agenda desconhecida '{tool_name}'.",
        }


# Gemini Live Function Declarations for Google Calendar
GOOGLE_CALENDAR_FUNCTION_DECLARATIONS = [
    {
        "name": "get_calendar_events",
        "description": "Obtém a lista de compromissos e reuniões agendadas no Google Agenda (Google Calendar) para hoje ou um período informado.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "time_min": {
                    "type": "STRING",
                    "description": "Filtro inicial de data/hora (ex: 'hoje', 'amanhã' ou formato ISO '2026-10-28T09:00:00'). Omissão assume o momento atual.",
                },
                "time_max": {
                    "type": "STRING",
                    "description": "Filtro final de data/hora opcional (ex: 'hoje às 23:59' ou formato ISO). Omissão assume 24 horas à frente.",
                },
                "max_results": {
                    "type": "INTEGER",
                    "description": "Número máximo de compromissos a retornar (padrão 10).",
                },
            },
            "required": [],
        },
    },
    {
        "name": "create_calendar_event",
        "description": "Cria e agenda um novo compromisso ou reunião no Google Agenda (Google Calendar).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "summary": {
                    "type": "STRING",
                    "description": "Título ou nome do compromisso (ex: 'Reunião com Diretoria', 'Consulta Odontológica', 'Almoço de Negócios').",
                },
                "start_time": {
                    "type": "STRING",
                    "description": "Data e hora de início (ex: 'hoje às 15:00', 'amanhã às 10h' ou formato ISO '2026-10-28T14:00:00').",
                },
                "end_time": {
                    "type": "STRING",
                    "description": "Data e hora de término opcional (se omitido, o evento terá duração de 1 hora).",
                },
                "description": {
                    "type": "STRING",
                    "description": "Pauta, detalhes ou anotações do compromisso.",
                },
                "location": {
                    "type": "STRING",
                    "description": "Local físico do evento ou link de videoconferência.",
                },
            },
            "required": ["summary", "start_time"],
        },
    },
]
