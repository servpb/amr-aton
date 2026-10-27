"""Google Gmail integration tools for Aton (Phase 4 - Read-Only)."""

import base64
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional
import urllib.parse
import urllib.request
import urllib.error

from src.config import settings

logger = logging.getLogger(__name__)

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
]


def _get_credentials():
    """Load or refresh Google OAuth2 credentials for Gmail Read-Only access."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
    except ImportError:
        logger.warning("google-auth not installed.")
        return None

    creds = None
    token_path = settings.gmail_token_path
    if not os.path.exists(token_path) and os.path.exists(settings.google_calendar_token_path):
        token_path = settings.google_calendar_token_path

    if os.path.exists(token_path):
        try:
            creds = Credentials.from_authorized_user_file(token_path, GMAIL_SCOPES)
        except Exception as exc:
            logger.warning(f"Error loading {token_path}: {exc}")

    # If expired, refresh token
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open(token_path, "w", encoding="utf-8") as f:
                f.write(creds.to_json())
            logger.info("Gmail OAuth2 credentials refreshed.")
        except Exception as exc:
            logger.error(f"Error refreshing Gmail token: {exc}")
            creds = None

    return creds


def _decode_base64_data(data_str: str) -> str:
    """Decode base64url-encoded string from Gmail API."""
    if not data_str:
        return ""
    try:
        padded = data_str.replace("-", "+").replace("_", "/")
        padding_needed = len(padded) % 4
        if padding_needed:
            padded += "=" * (4 - padding_needed)
        raw_bytes = base64.b64decode(padded)
        return raw_bytes.decode("utf-8", errors="ignore")
    except Exception as exc:
        logger.warning(f"Error decoding base64 content: {exc}")
        return ""


def _extract_plain_text(payload: Dict[str, Any]) -> str:
    """Recursively extract plain text body from message payload."""
    if not payload:
        return ""

    # Check direct body
    body_data = payload.get("body", {}).get("data", "")
    if body_data:
        text = _decode_base64_data(body_data)
        if payload.get("mimeType") == "text/html":
            text = re.sub(r"<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    # Check multipart parts
    parts = payload.get("parts", [])
    # First search for text/plain
    for part in parts:
        if part.get("mimeType") == "text/plain":
            data = part.get("body", {}).get("data", "")
            if data:
                return re.sub(r"\s+", " ", _decode_base64_data(data)).strip()

    # Fallback to text/html
    for part in parts:
        if part.get("mimeType") == "text/html":
            data = part.get("body", {}).get("data", "")
            if data:
                raw_html = _decode_base64_data(data)
                clean_text = re.sub(r"<[^>]+>", " ", raw_html)
                return re.sub(r"\s+", " ", clean_text).strip()

    # Recurse sub-parts
    for part in parts:
        nested = _extract_plain_text(part)
        if nested:
            return nested

    return ""


def list_unread_emails(
    max_results: int = 5,
    query: str = "is:unread label:INBOX",
) -> Dict[str, Any]:
    """Retrieve and summarize unread emails from the user's Gmail inbox.

    Args:
        max_results: Maximum emails to return (default 5).
        query: Gmail search query filter (default 'is:unread label:INBOX').
    """
    creds = _get_credentials()
    if not creds or not creds.valid:
        return {
            "status": "not_authenticated",
            "message": (
                "O Gmail ainda não está autenticado. Para que o Aton possa ler seus e-mails, "
                "coloque seu arquivo credentials.json baixado do Google Cloud Console na raiz do projeto. "
                "Consulte o passo a passo em docs/gmail.md."
            ),
            "emails": [],
        }

    encoded_query = urllib.parse.quote(query)
    list_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages?q={encoded_query}&maxResults={max_results}"

    req = urllib.request.Request(
        list_url,
        headers={"Authorization": f"Bearer {creds.token}"},
        method="GET",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            list_data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        logger.error(f"Gmail API HTTP error: {err.code} {err.reason}")
        return {
            "status": "error",
            "message": f"Erro ao consultar o Gmail: código HTTP {err.code}.",
            "emails": [],
        }
    except Exception as exc:
        logger.error(f"Error querying Gmail messages list: {exc}")
        return {
            "status": "error",
            "message": f"Não foi possível acessar seus e-mails no momento: {exc}",
            "emails": [],
        }

    messages = list_data.get("messages", [])
    if not messages:
        return {
            "status": "success",
            "message": "Você não tem nenhum novo e-mail não lido na sua caixa de entrada, senhor.",
            "count": 0,
            "emails": [],
        }

    emails_summary: List[Dict[str, Any]] = []

    for msg_meta in messages[:max_results]:
        msg_id = msg_meta.get("id")
        if not msg_id:
            continue

        detail_url = (
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}?"
            f"format=metadata&metadataHeaders=From&metadataHeaders=Subject&metadataHeaders=Date"
        )
        detail_req = urllib.request.Request(
            detail_url,
            headers={"Authorization": f"Bearer {creds.token}"},
            method="GET",
        )

        try:
            with urllib.request.urlopen(detail_req, timeout=10) as d_resp:
                detail_data = json.loads(d_resp.read().decode("utf-8"))

            headers = {
                h.get("name", "").lower(): h.get("value", "")
                for h in detail_data.get("payload", {}).get("headers", [])
            }

            from_val = headers.get("from", "Desconhecido")
            # Extract friendly sender name (e.g. 'Google Security <no-reply@...>' -> 'Google Security')
            sender_name = re.sub(r"<[^>]+>", "", from_val).strip() or from_val
            subject_val = headers.get("subject", "Sem assunto")
            date_val = headers.get("date", "")
            snippet = detail_data.get("snippet", "")

            emails_summary.append({
                "id": msg_id,
                "from": sender_name,
                "full_from": from_val,
                "subject": subject_val,
                "date": date_val,
                "snippet": snippet,
            })
        except Exception as exc:
            logger.warning(f"Could not load details for email {msg_id}: {exc}")

    # Synthesize spoken natural response in Portuguese
    if not emails_summary:
        msg = "Você não tem novos e-mails não lidos no momento, senhor."
    elif len(emails_summary) == 1:
        e = emails_summary[0]
        msg = f"Você tem 1 novo e-mail de {e['from']} com o assunto '{e['subject']}'."
    else:
        list_str = "; ".join(f"de {e['from']} sobre '{e['subject']}'" for e in emails_summary[:3])
        if len(emails_summary) > 3:
            list_str += f" e mais {len(emails_summary) - 3} outros"
        msg = f"Você tem {len(emails_summary)} novos e-mails não lidos: {list_str}."

    return {
        "status": "success",
        "message": msg,
        "count": len(emails_summary),
        "emails": emails_summary,
    }


def get_email_content(email_id: str) -> Dict[str, Any]:
    """Retrieve and read full content/summary of a specific email by ID.

    Args:
        email_id: Gmail message ID (obtained from list_unread_emails).
    """
    creds = _get_credentials()
    if not creds or not creds.valid:
        return {
            "status": "not_authenticated",
            "message": (
                "O Gmail ainda não está autenticado. Para que o Aton possa ler seus e-mails, "
                "coloque seu arquivo credentials.json na raiz do projeto."
            ),
        }

    url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{email_id}?format=full"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {creds.token}"},
        method="GET",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        logger.error(f"Gmail API HTTP error reading email {email_id}: {err.code} {err.reason}")
        return {
            "status": "error",
            "message": f"Erro ao acessar o e-mail: código HTTP {err.code}.",
        }
    except Exception as exc:
        logger.error(f"Error fetching email {email_id}: {exc}")
        return {
            "status": "error",
            "message": f"Não foi possível ler o e-mail: {exc}",
        }

    payload = data.get("payload", {})
    headers = {
        h.get("name", "").lower(): h.get("value", "")
        for h in payload.get("headers", [])
    }

    sender = headers.get("from", "Remetente desconhecido")
    friendly_sender = re.sub(r"<[^>]+>", "", sender).strip() or sender
    subject = headers.get("subject", "Sem assunto")
    date = headers.get("date", "")

    body_text = _extract_plain_text(payload)
    if not body_text:
        body_text = data.get("snippet", "Conteúdo vazio.")

    # Limit body preview for voice response to avoid endless speech
    spoken_preview = body_text[:400] + ("..." if len(body_text) > 400 else "")

    return {
        "status": "success",
        "message": f"E-mail de {friendly_sender} sobre '{subject}': {spoken_preview}",
        "email_id": email_id,
        "from": friendly_sender,
        "subject": subject,
        "date": date,
        "body": body_text,
    }


def dispatch_gmail_tool(tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatch Gmail tool requests."""
    if tool_name == "list_unread_emails":
        return list_unread_emails(
            max_results=tool_args.get("max_results", 5),
            query=tool_args.get("query", "is:unread label:INBOX"),
        )
    elif tool_name == "get_email_content":
        email_id = tool_args.get("email_id", "")
        if not email_id:
            return {"status": "error", "message": "O ID do e-mail é obrigatório."}
        return get_email_content(email_id=email_id)
    else:
        return {
            "status": "error",
            "message": f"Ferramenta do Gmail desconhecida '{tool_name}'.",
        }


# Gemini Live Function Declarations for Gmail (Read-Only)
GMAIL_FUNCTION_DECLARATIONS = [
    {
        "name": "list_unread_emails",
        "description": "Lista e resume os e-mails mais recentes e não lidos da caixa de entrada do Gmail.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "max_results": {
                    "type": "INTEGER",
                    "description": "Número máximo de e-mails a retornar (padrão: 5).",
                },
                "query": {
                    "type": "STRING",
                    "description": "Filtro de busca do Gmail (ex: 'is:unread label:INBOX' ou 'from:chefe').",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_email_content",
        "description": "Lê o conteúdo completo ou o resumo de um e-mail específico pelo seu ID retornado por list_unread_emails.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "email_id": {
                    "type": "STRING",
                    "description": "O identificador único do e-mail a ser lido.",
                },
            },
            "required": ["email_id"],
        },
    },
]
