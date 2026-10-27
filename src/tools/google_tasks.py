"""Google Tasks integration tools for Aton (Phase 4)."""

from datetime import datetime, timezone
import json
import logging
import os
from typing import Any, Dict, List, Optional
import urllib.parse
import urllib.request
import urllib.error

from src.config import settings
from src.tools.google_calendar import parse_datetime_flexible

logger = logging.getLogger(__name__)

TASKS_SCOPES = [
    "https://www.googleapis.com/auth/tasks",
]


def _get_credentials():
    """Load or refresh Google OAuth2 credentials for Tasks access."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
    except ImportError:
        logger.warning("google-auth not installed.")
        return None

    creds = None
    token_path = settings.google_tasks_token_path
    if not os.path.exists(token_path) and os.path.exists(settings.google_calendar_token_path):
        token_path = settings.google_calendar_token_path

    if os.path.exists(token_path):
        try:
            creds = Credentials.from_authorized_user_file(token_path, TASKS_SCOPES)
        except Exception as exc:
            logger.warning(f"Error loading {token_path}: {exc}")

    # If expired, refresh token
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open(token_path, "w", encoding="utf-8") as f:
                f.write(creds.to_json())
            logger.info("Google Tasks OAuth2 credentials refreshed.")
        except Exception as exc:
            logger.error(f"Error refreshing Google Tasks token: {exc}")
            creds = None

    return creds


def list_tasks(
    show_completed: bool = False,
    task_list_id: Optional[str] = None,
    max_results: int = 10,
) -> Dict[str, Any]:
    """List pending or completed tasks from the user's Google Tasks.

    Args:
        show_completed: Whether to include completed tasks (default False).
        task_list_id: Task list ID (defaults to '@default').
        max_results: Maximum tasks to retrieve (default 10).
    """
    creds = _get_credentials()
    if not creds or not creds.valid:
        return {
            "status": "not_authenticated",
            "message": (
                "O Google Tarefas ainda não está autenticado. Para gerenciar suas tarefas com o Aton, "
                "coloque seu arquivo credentials.json baixado do Google Cloud Console na raiz do projeto. "
                "Consulte o passo a passo em docs/google_tasks.md."
            ),
            "tasks": [],
        }

    list_id = urllib.parse.quote(task_list_id or settings.google_tasks_default_list or "@default")
    url = (
        f"https://tasks.googleapis.com/tasks/v1/lists/{list_id}/tasks?"
        f"showCompleted={str(show_completed).lower()}&showHidden=false&maxResults={max_results}"
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
        logger.error(f"Google Tasks API HTTP error: {err.code} {err.reason}")
        return {
            "status": "error",
            "message": f"Erro ao consultar o Google Tarefas: código HTTP {err.code}.",
            "tasks": [],
        }
    except Exception as exc:
        logger.error(f"Error querying Google Tasks API: {exc}")
        return {
            "status": "error",
            "message": f"Não foi possível acessar suas tarefas no momento: {exc}",
            "tasks": [],
        }

    items = data.get("items", [])
    tasks_summary: List[Dict[str, Any]] = []

    for item in items:
        # Filter out completed if show_completed is False
        if not show_completed and item.get("status") == "completed":
            continue

        tasks_summary.append({
            "id": item.get("id"),
            "title": item.get("title", "Sem título"),
            "notes": item.get("notes", ""),
            "status": item.get("status", "needsAction"),
            "due": item.get("due", ""),
            "updated": item.get("updated", ""),
        })

    # Synthesize spoken natural language response
    if not tasks_summary:
        msg = "Você não tem nenhuma tarefa pendente na sua lista, senhor."
    elif len(tasks_summary) == 1:
        msg = f"Você tem 1 tarefa pendente: '{tasks_summary[0]['title']}'."
    else:
        task_titles = "; ".join(f"'{t['title']}'" for t in tasks_summary[:3])
        if len(tasks_summary) > 3:
            task_titles += f" e mais {len(tasks_summary) - 3} outras"
        msg = f"Você tem {len(tasks_summary)} tarefas pendentes: {task_titles}."

    return {
        "status": "success",
        "message": msg,
        "count": len(tasks_summary),
        "tasks": tasks_summary,
    }


def create_task(
    title: str,
    notes: str = "",
    due_date: Optional[str] = None,
    task_list_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new to-do task or reminder in Google Tasks.

    Args:
        title: Task title or description (e.g. 'Comprar café', 'Enviar relatório').
        notes: Additional notes or details.
        due_date: Optional due date (e.g. 'hoje', 'amanhã', '2026-10-28').
        task_list_id: Task list ID (defaults to '@default').
    """
    creds = _get_credentials()
    if not creds or not creds.valid:
        return {
            "status": "not_authenticated",
            "message": (
                "O Google Tarefas ainda não está autenticado. Para adicionar tarefas, "
                "coloque seu arquivo credentials.json na raiz do projeto."
            ),
        }

    payload: Dict[str, Any] = {
        "title": title,
        "notes": notes,
    }

    if due_date:
        parsed_due = parse_datetime_flexible(due_date)
        # RFC3339 timestamp with Z
        payload["due"] = parsed_due.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    list_id = urllib.parse.quote(task_list_id or settings.google_tasks_default_list or "@default")
    url = f"https://tasks.googleapis.com/tasks/v1/lists/{list_id}/tasks"
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
        logger.error(f"Google Tasks API create task HTTP error: {err.code} {err.reason}")
        return {
            "status": "error",
            "message": f"Erro ao criar tarefa no Google Tarefas: código HTTP {err.code}.",
        }
    except Exception as exc:
        logger.error(f"Error creating task in Google Tasks API: {exc}")
        return {
            "status": "error",
            "message": f"Não foi possível salvar a tarefa: {exc}",
        }

    return {
        "status": "success",
        "message": f"Tarefa '{title}' adicionada com sucesso à sua lista, senhor.",
        "task_id": data.get("id"),
        "title": data.get("title", title),
        "due": data.get("due"),
    }


def complete_task(
    task_id_or_title: str,
    task_list_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Mark a task as completed in Google Tasks by its ID or by title matching.

    Args:
        task_id_or_title: Unique task ID or title keywords (e.g. 'comprar café').
        task_list_id: Task list ID (defaults to '@default').
    """
    creds = _get_credentials()
    if not creds or not creds.valid:
        return {
            "status": "not_authenticated",
            "message": (
                "O Google Tarefas ainda não está autenticado. Para concluir tarefas, "
                "coloque seu arquivo credentials.json na raiz do projeto."
            ),
        }

    list_id = urllib.parse.quote(task_list_id or settings.google_tasks_default_list or "@default")
    actual_task_id = task_id_or_title.strip()
    matched_title = task_id_or_title

    # If task_id_or_title is likely a title (has spaces, common words), find task by title
    is_plain_id = len(actual_task_id) > 15 and " " not in actual_task_id

    if not is_plain_id:
        # Search active tasks for match
        list_res = list_tasks(show_completed=False, task_list_id=task_list_id)
        if list_res.get("status") == "success":
            query_lower = actual_task_id.lower()
            for t in list_res.get("tasks", []):
                t_title = t.get("title", "")
                if query_lower in t_title.lower() or t_title.lower() in query_lower:
                    actual_task_id = t["id"]
                    matched_title = t_title
                    break

    url = f"https://tasks.googleapis.com/tasks/v1/lists/{list_id}/tasks/{urllib.parse.quote(actual_task_id)}"
    patch_payload = {"id": actual_task_id, "status": "completed"}
    body_data = json.dumps(patch_payload).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body_data,
        headers={
            "Authorization": f"Bearer {creds.token}",
            "Content-Type": "application/json",
        },
        method="PATCH",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        logger.error(f"Google Tasks complete task HTTP error: {err.code} {err.reason}")
        return {
            "status": "error",
            "message": f"Erro ao concluir tarefa: código HTTP {err.code}.",
        }
    except Exception as exc:
        logger.error(f"Error completing task: {exc}")
        return {
            "status": "error",
            "message": f"Não foi possível concluir a tarefa: {exc}",
        }

    title_display = data.get("title") or matched_title
    return {
        "status": "success",
        "message": f"Tarefa '{title_display}' marcada como concluída com sucesso, senhor.",
        "task_id": actual_task_id,
        "title": title_display,
        "status_val": "completed",
    }


def dispatch_tasks_tool(tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatch Google Tasks tool requests."""
    if tool_name == "list_tasks":
        return list_tasks(
            show_completed=tool_args.get("show_completed", False),
            task_list_id=tool_args.get("task_list_id"),
            max_results=tool_args.get("max_results", 10),
        )
    elif tool_name == "create_task":
        return create_task(
            title=tool_args.get("title", "Nova Tarefa"),
            notes=tool_args.get("notes", ""),
            due_date=tool_args.get("due_date"),
            task_list_id=tool_args.get("task_list_id"),
        )
    elif tool_name == "complete_task":
        task_id_or_title = tool_args.get("task_id_or_title") or tool_args.get("task_id") or ""
        if not task_id_or_title:
            return {"status": "error", "message": "O título ou ID da tarefa a ser concluída é obrigatório."}
        return complete_task(
            task_id_or_title=task_id_or_title,
            task_list_id=tool_args.get("task_list_id"),
        )
    else:
        return {
            "status": "error",
            "message": f"Ferramenta do Google Tarefas desconhecida '{tool_name}'.",
        }


# Gemini Live Function Declarations for Google Tasks
GOOGLE_TASKS_FUNCTION_DECLARATIONS = [
    {
        "name": "list_tasks",
        "description": "Lista as tarefas, pendências e itens a fazer (to-dos) da lista do Google Tarefas.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "show_completed": {
                    "type": "BOOLEAN",
                    "description": "Se verdadeiro, inclui tarefas que já foram concluídas (padrão: falso, somente pendentes).",
                },
                "max_results": {
                    "type": "INTEGER",
                    "description": "Número máximo de tarefas a retornar (padrão: 10).",
                },
            },
            "required": [],
        },
    },
    {
        "name": "create_task",
        "description": "Cria e adiciona uma nova tarefa ou lembrete na lista do Google Tarefas.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "title": {
                    "type": "STRING",
                    "description": "Título ou descrição da tarefa (ex: 'Comprar café', 'Enviar relatório semanal').",
                },
                "notes": {
                    "type": "STRING",
                    "description": "Anotações adicionais ou detalhes da tarefa.",
                },
                "due_date": {
                    "type": "STRING",
                    "description": "Data de vencimento opcional (ex: 'hoje', 'amanhã', '2026-10-30').",
                },
            },
            "required": ["title"],
        },
    },
    {
        "name": "complete_task",
        "description": "Marca uma tarefa como concluída na lista do Google Tarefas pelo seu ID ou pelo nome/título da tarefa.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "task_id_or_title": {
                    "type": "STRING",
                    "description": "O ID ou o nome/título da tarefa que o usuário deseja marcar como feita (ex: 'comprar café').",
                },
            },
            "required": ["task_id_or_title"],
        },
    },
]
