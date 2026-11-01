"""Google Gmail integration tools for Aton (Phase 4 - Read-Only OAuth 2.0 Desktop, Multi-Account)."""

import base64
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
import urllib.error
import urllib.parse
import urllib.request

from src.integrations.gmail_service import (
    GMAIL_READONLY_SCOPES,
    classify_gmail_http_error,
    get_gmail_service,
)

logger = logging.getLogger(__name__)

GMAIL_SCOPES = list(GMAIL_READONLY_SCOPES)


def _get_credentials(account: Optional[str] = None):
    """Load or silently refresh Google OAuth2 credentials for Gmail Read-Only access.

    Passively checks existing local token without opening a browser.
    """
    service = get_gmail_service()
    creds, _status_code, _msg = service.get_valid_credentials(account=account)
    return creds


def authenticate_gmail(expected_email: Optional[str] = None) -> Dict[str, Any]:
    """Explicitly start the interactive OAuth 2.0 Desktop browser authentication flow for Gmail."""
    service = get_gmail_service()
    return service.authenticate_interactive(open_browser=True, expected_email=expected_email)


def check_gmail_connection(account: Optional[str] = None) -> Dict[str, Any]:
    """Passively verify whether Gmail is authenticated and the Gmail API is reachable (never opens browser)."""
    service = get_gmail_service()
    return service.check_connection(account=account)


def remove_gmail_account(account: str, revoke_remote: bool = False) -> Dict[str, Any]:
    """Disconnect and remove a specific Gmail account's local token from Aton."""
    service = get_gmail_service()
    return service.remove_account(account=account, revoke_remote=revoke_remote)


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


def _fetch_messages_for_credential(
    creds: Any,
    max_results: int,
    query: str,
    account_label: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], str, str]:
    """Fetch unread message summaries for a single credential object."""
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
        err_slug, err_msg, should_invalidate = classify_gmail_http_error(err)
        logger.error(f"Gmail API HTTP error: {err.code} ({err_slug})")
        if should_invalidate:
            get_gmail_service().invalidate_local_token(account=account_label)
        return [], err_slug, err_msg
    except Exception as exc:
        logger.error(f"Error querying Gmail messages list: {exc}")
        return [], "error", f"Não foi possível acessar seus e-mails no momento: {exc}"

    messages = list_data.get("messages", [])
    if not messages:
        return [], "success", ""

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
            sender_name = re.sub(r"<[^>]+>", "", from_val).strip() or from_val
            subject_val = headers.get("subject", "Sem assunto")
            date_val = headers.get("date", "")
            snippet = detail_data.get("snippet", "")
            raw_internal_date = detail_data.get("internalDate", 0)
            try:
                internal_date = int(raw_internal_date)
            except (TypeError, ValueError):
                internal_date = 0

            item: Dict[str, Any] = {
                "id": msg_id,
                "from": sender_name,
                "full_from": from_val,
                "subject": subject_val,
                "date": date_val,
                "snippet": snippet,
                "internal_date": internal_date,
            }
            if account_label:
                item["account"] = account_label
            emails_summary.append(item)
        except Exception as exc:
            logger.warning(f"Could not load details for email {msg_id}: {exc}")

    return emails_summary, "success", ""


def list_unread_emails(
    max_results: int = 5,
    query: str = "is:unread label:INBOX",
    account: Optional[str] = None,
) -> Dict[str, Any]:
    """Retrieve and summarize unread emails from one or all connected Gmail accounts.

    When account is None and multiple accounts are connected:
    - Queries each connected account with fault isolation (failures in one account do not discard results from others).
    - Includes the source account ('account') on every returned message.
    - Sorts combined messages by recency (internalDate descending) and enforces max_results as the TOTAL combined cap.
    """
    service = get_gmail_service()
    configured_accounts = service.get_all_configured_accounts()

    # Multi-account unified query when account is omitted and >1 accounts are registered
    if account is None and len(configured_accounts) > 1:
        combined_emails: List[Dict[str, Any]] = []
        failed_accounts: List[Dict[str, str]] = []
        active_accounts_checked: List[str] = []

        for acct_email in configured_accounts:
            creds = _get_credentials(account=acct_email)
            if not creds or not creds.valid:
                failed_accounts.append({
                    "account": acct_email,
                    "status": "not_authenticated",
                    "message": f"A conta '{acct_email}' precisa ser reconectada.",
                })
                continue

            acct_emails, status_code, err_msg = _fetch_messages_for_credential(
                creds=creds,
                max_results=max_results,
                query=query,
                account_label=acct_email,
            )
            if status_code != "success":
                failed_accounts.append({
                    "account": acct_email,
                    "status": status_code,
                    "message": err_msg,
                })
            else:
                active_accounts_checked.append(acct_email)
                combined_emails.extend(acct_emails)

        if not active_accounts_checked and failed_accounts:
            failed_str = "; ".join(f"{f['account']} ({f['status']})" for f in failed_accounts)
            return {
                "status": "not_authenticated",
                "message": (
                    f"Não foi possível consultar nenhuma das contas configuradas ({failed_str}). "
                    "Execute 'run.bat gmail-auth <email>' para reconectar."
                ),
                "failed_accounts": failed_accounts,
                "emails": [],
            }

        # Sort by internal_date descending (most recent first) and cap total results to max_results
        combined_emails.sort(key=lambda e: int(e.get("internal_date", 0) or 0), reverse=True)
        capped_emails = combined_emails[:max_results]

        warning_suffix = ""
        if failed_accounts:
            failed_names = ", ".join(f["account"] for f in failed_accounts)
            warning_suffix = f" (Atenção: não foi possível consultar: {failed_names})."

        if not capped_emails:
            msg = (
                f"Você não tem nenhum novo e-mail não lido nas {len(active_accounts_checked)} contas "
                f"conectadas ({', '.join(active_accounts_checked)}), senhor.{warning_suffix}"
            )
        elif len(capped_emails) == 1:
            e = capped_emails[0]
            msg = (
                f"Você tem 1 novo e-mail na conta {e.get('account', '')}: "
                f"de {e['from']} com o assunto '{e['subject']}'.{warning_suffix}"
            )
        else:
            list_str = "; ".join(
                f"[{e.get('account', '')}] de {e['from']} sobre '{e['subject']}'"
                for e in capped_emails[:3]
            )
            if len(capped_emails) > 3:
                list_str += f" e mais {len(capped_emails) - 3} outros"
            msg = f"Você tem {len(capped_emails)} novos e-mails não lidos: {list_str}.{warning_suffix}"

        return {
            "status": "success",
            "message": msg,
            "count": len(capped_emails),
            "accounts_checked": active_accounts_checked,
            "failed_accounts": failed_accounts,
            "emails": capped_emails,
        }

    # Single-account query (either specific account requested, or 0/1 account configured)
    creds = _get_credentials(account=account) if account is not None else _get_credentials()
    if not creds or not creds.valid:
        if account:
            _, status_code, err_msg = service.get_valid_credentials(account=account)
            return {
                "status": status_code,
                "message": err_msg,
                "emails": [],
            }
        return {
            "status": "not_authenticated",
            "message": (
                "O Gmail ainda não está autenticado. Para que o Aton possa ler seus e-mails, "
                "coloque seu arquivo credentials.json baixado do Google Cloud Console na raiz do projeto. "
                "Consulte o passo a passo em docs/gmail.md."
            ),
            "emails": [],
        }

    resolved_account = (
        service._match_account_email(account) if account else (configured_accounts[0] if len(configured_accounts) == 1 else None)
    )
    emails_summary, status_code, err_msg = _fetch_messages_for_credential(
        creds=creds,
        max_results=max_results,
        query=query,
        account_label=resolved_account,
    )

    if status_code != "success":
        return {
            "status": status_code,
            "message": err_msg,
            "emails": [],
        }

    if not emails_summary:
        acct_info = f" na conta {resolved_account}" if resolved_account else ""
        return {
            "status": "success",
            "message": f"Você não tem nenhum novo e-mail não lido na sua caixa de entrada{acct_info}, senhor.",
            "count": 0,
            "emails": [],
        }

    acct_prefix = f" na conta {resolved_account}" if resolved_account else ""
    if len(emails_summary) == 1:
        e = emails_summary[0]
        msg = f"Você tem 1 novo e-mail{acct_prefix} de {e['from']} com o assunto '{e['subject']}'."
    else:
        list_str = "; ".join(f"de {e['from']} sobre '{e['subject']}'" for e in emails_summary[:3])
        if len(emails_summary) > 3:
            list_str += f" e mais {len(emails_summary) - 3} outros"
        msg = f"Você tem {len(emails_summary)} novos e-mails não lidos{acct_prefix}: {list_str}."

    result: Dict[str, Any] = {
        "status": "success",
        "message": msg,
        "count": len(emails_summary),
        "emails": emails_summary,
    }
    if resolved_account:
        result["account"] = resolved_account
    return result


def _format_email_detail_response(
    email_id: str,
    data: Dict[str, Any],
    account_label: Optional[str] = None,
) -> Dict[str, Any]:
    """Parse full Gmail message payload into a structured dictionary for Aton."""
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

    spoken_preview = body_text[:400] + ("..." if len(body_text) > 400 else "")
    acct_info = f" (conta {account_label})" if account_label else ""

    res: Dict[str, Any] = {
        "status": "success",
        "message": f"E-mail de {friendly_sender} sobre '{subject}'{acct_info}: {spoken_preview}",
        "email_id": email_id,
        "from": friendly_sender,
        "subject": subject,
        "date": date,
        "body": body_text,
    }
    if account_label:
        res["account"] = account_label
    return res


def get_email_content(email_id: str, account: Optional[str] = None) -> Dict[str, Any]:
    """Retrieve and read full content/summary of a specific email by ID.

    Since Gmail message IDs are only guaranteed unique within a single mailbox:
    - If account is specified (or <=1 account is connected), queries that mailbox directly.
    - If account is None and multiple accounts are connected, searches across connected mailboxes:
      - If found in exactly 1 mailbox, returns its content with 'account'.
      - If found in >1 mailboxes, returns 'ambiguous_account' listing matching accounts and asking to specify 'account'.
    """
    service = get_gmail_service()
    configured_accounts = service.get_all_configured_accounts()

    # Cross-account search when account is omitted and multiple accounts exist
    if account is None and len(configured_accounts) > 1:
        matches: List[Tuple[str, Dict[str, Any]]] = []
        last_error: Optional[Tuple[str, str]] = None

        for acct_email in configured_accounts:
            creds = _get_credentials(account=acct_email)
            if not creds or not creds.valid:
                continue

            url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{email_id}?format=full"
            req = urllib.request.Request(
                url,
                headers={"Authorization": f"Bearer {creds.token}"},
                method="GET",
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    matches.append((acct_email, data))
            except urllib.error.HTTPError as err:
                if getattr(err, "code", 0) == 404:
                    continue
                err_slug, err_msg, should_invalidate = classify_gmail_http_error(err)
                if should_invalidate:
                    service.invalidate_local_token(account=acct_email)
                last_error = (err_slug, err_msg)
            except Exception as exc:
                last_error = ("error", f"Não foi possível ler o e-mail: {exc}")

        if len(matches) == 1:
            matched_acct, matched_data = matches[0]
            return _format_email_detail_response(email_id, matched_data, account_label=matched_acct)

        if len(matches) > 1:
            matching_accounts = [m[0] for m in matches]
            return {
                "status": "ambiguous_account",
                "email_id": email_id,
                "matching_accounts": matching_accounts,
                "message": (
                    f"O identificador de mensagem '{email_id}' foi encontrado em mais de uma conta "
                    f"({', '.join(matching_accounts)}). Por favor, informe de qual conta deseja ler o e-mail."
                ),
            }

        if last_error:
            return {
                "status": last_error[0],
                "message": last_error[1],
            }

        return {
            "status": "not_found",
            "message": f"O e-mail '{email_id}' não foi encontrado em nenhuma das contas conectadas ({', '.join(configured_accounts)}).",
        }

    # Single-account lookup
    creds = _get_credentials(account=account) if account is not None else _get_credentials()
    if not creds or not creds.valid:
        if account:
            _, status_code, err_msg = service.get_valid_credentials(account=account)
            return {
                "status": status_code,
                "message": err_msg,
            }
        return {
            "status": "not_authenticated",
            "message": (
                "O Gmail ainda não está autenticado. Para que o Aton possa ler seus e-mails, "
                "coloque seu arquivo credentials.json na raiz do projeto."
            ),
        }

    resolved_account = (
        service._match_account_email(account) if account else (configured_accounts[0] if len(configured_accounts) == 1 else None)
    )
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
        err_slug, err_msg, should_invalidate = classify_gmail_http_error(err)
        logger.error(f"Gmail API HTTP error reading email {email_id}: {err.code} ({err_slug})")
        if should_invalidate:
            service.invalidate_local_token(account=resolved_account)
        return {
            "status": err_slug,
            "message": err_msg,
        }
    except Exception as exc:
        logger.error(f"Error fetching email {email_id}: {exc}")
        return {
            "status": "error",
            "message": f"Não foi possível ler o e-mail: {exc}",
        }

    return _format_email_detail_response(email_id, data, account_label=resolved_account)


def dispatch_gmail_tool(tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatch Gmail tool requests."""
    if tool_name == "list_unread_emails":
        return list_unread_emails(
            max_results=tool_args.get("max_results", 5),
            query=tool_args.get("query", "is:unread label:INBOX"),
            account=tool_args.get("account"),
        )
    elif tool_name == "get_email_content":
        email_id = tool_args.get("email_id", "")
        if not email_id:
            return {"status": "error", "message": "O ID do e-mail é obrigatório."}
        if tool_args.get("account") is not None:
            return get_email_content(email_id=email_id, account=tool_args.get("account"))
        return get_email_content(email_id=email_id)
    elif tool_name == "authenticate_gmail":
        return authenticate_gmail(expected_email=tool_args.get("expected_email"))
    elif tool_name == "check_gmail_connection":
        return check_gmail_connection(account=tool_args.get("account"))
    elif tool_name == "remove_gmail_account":
        account = tool_args.get("account", "")
        if not account:
            return {"status": "error", "message": "O endereço de e-mail da conta é obrigatório para desconectar."}
        return remove_gmail_account(
            account=account,
            revoke_remote=bool(tool_args.get("revoke_remote", False)),
        )
    else:
        return {
            "status": "error",
            "message": f"Ferramenta do Gmail desconhecida '{tool_name}'.",
        }


# Gemini Live Function Declarations for Gmail (Read-Only, Multi-Account)
GMAIL_FUNCTION_DECLARATIONS = [
    {
        "name": "list_unread_emails",
        "description": (
            "Lista e resume os e-mails mais recentes e não lidos da caixa de entrada do Gmail. "
            "Pode consultar uma conta específica ou todas as contas conectadas simultaneamente."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "max_results": {
                    "type": "INTEGER",
                    "description": "Limite máximo total de e-mails a retornar (padrão: 5).",
                },
                "query": {
                    "type": "STRING",
                    "description": "Filtro de busca do Gmail (ex: 'is:unread label:INBOX' ou 'from:chefe').",
                },
                "account": {
                    "type": "STRING",
                    "description": "Opcional. Endereço de e-mail ou prefixo da conta específica a consultar (ex: 'cursopb@gmail.com'). Se omitido, consulta todas as contas conectadas.",
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
                    "description": "O identificador da mensagem no Gmail.",
                },
                "account": {
                    "type": "STRING",
                    "description": "Opcional. Endereço de e-mail da conta de origem da mensagem (recomendado quando há múltiplas contas conectadas).",
                },
            },
            "required": ["email_id"],
        },
    },
    {
        "name": "authenticate_gmail",
        "description": "Inicia a autenticação interativa do Gmail pelo navegador (OAuth 2.0 Desktop) apenas quando o usuário solicitar explicitamente conectar ou reconectar uma conta do Gmail.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "expected_email": {
                    "type": "STRING",
                    "description": "Opcional. O endereço de e-mail que o usuário espera autorizar (ex: 'cursopb@gmail.com'). O Aton verificará se a conta escolhida no navegador corresponde a este endereço antes de salvar.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "check_gmail_connection",
        "description": "Verifica passivamente o status atual da conexão e lista as contas do Gmail conectadas ao Aton sem abrir o navegador.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "account": {
                    "type": "STRING",
                    "description": "Opcional. Endereço de e-mail de uma conta específica para verificar.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "remove_gmail_account",
        "description": "Desconecta e remove o token local de uma conta específica do Gmail no Aton (com opção de revogar também a autorização nos servidores do Google).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "account": {
                    "type": "STRING",
                    "description": "Endereço de e-mail da conta a ser desconectada/removida do Aton.",
                },
                "revoke_remote": {
                    "type": "BOOLEAN",
                    "description": "Opcional (padrão: false). Se true, além de apagar o token local no Aton, revoga o acesso remotamente na Conta Google.",
                },
            },
            "required": ["account"],
        },
    },
]
