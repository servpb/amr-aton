"""Long-Term Semantic Memory and Daily Executive Briefing for Aton (Phase 5)."""

from datetime import datetime, timezone
import json
import logging
import os
import sqlite3
from typing import Any, Dict, List, Optional

from src.config import settings

logger = logging.getLogger(__name__)


def _get_db_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Create or return an SQLite connection with the memories table initialized."""
    path = db_path or settings.memory_db_path or "amr_memory.db"
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row

    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                key TEXT NOT NULL UNIQUE,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_memories_key ON memories(key);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);"
        )

    return conn


def remember_fact(
    category: str,
    key: str,
    content: str,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Store or update a persistent user preference, fact, or instruction.

    Args:
        category: Context category ('preferência', 'trabalho', 'pessoal', 'rotina').
        key: Unique identifier key (e.g. 'resolucao_video', 'aniversario').
        content: Detailed fact or statement to remember.
        db_path: Optional custom SQLite path for testing.
    """
    clean_key = key.strip().lower().replace(" ", "_")
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        conn = _get_db_connection(db_path)
        with conn:
            conn.execute(
                """
                INSERT INTO memories (category, key, content, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    category = excluded.category,
                    content = excluded.content,
                    updated_at = excluded.updated_at;
                """,
                (category.strip().lower(), clean_key, content.strip(), now_iso, now_iso),
            )
        conn.close()

        logger.info(f"🧠 Memória gravada [{category}]: {clean_key} -> '{content}'")
        return {
            "status": "success",
            "message": f"Com certeza, senhor. Registrei em minha memória de longo prazo que: {content}.",
            "key": clean_key,
            "category": category,
            "content": content,
        }
    except Exception as exc:
        logger.error(f"Erro ao salvar memória '{key}': {exc}")
        return {
            "status": "error",
            "message": f"Não foi possível gravar a informação na memória: {exc}",
        }


import unicodedata
import re

def _normalize_text(s: str) -> str:
    """Normalize text by stripping accents, punctuation, and lowering."""
    if not s:
        return ""
    normalized = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("utf-8")
    clean = re.sub(r"[^\w\s]", " ", normalized.lower())
    return re.sub(r"\s+", " ", clean).strip()


def recall_memory(
    query: str,
    category: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Query persistent memories matching query keywords or category.

    Args:
        query: Search term or question keywords.
        category: Optional category filter.
        db_path: Optional custom SQLite path for testing.
    """
    q_norm = _normalize_text(query)
    tokens = [t for t in q_norm.split() if len(t) > 2]
    conn = _get_db_connection(db_path)

    try:
        cursor = conn.cursor()
        if category:
            cursor.execute(
                "SELECT category, key, content, updated_at FROM memories WHERE category = ? ORDER BY updated_at DESC",
                (category.strip().lower(),),
            )
        else:
            cursor.execute(
                "SELECT category, key, content, updated_at FROM memories ORDER BY updated_at DESC"
            )

        rows = cursor.fetchall()
        conn.close()

        matches = []

        for r in rows:
            content_norm = _normalize_text(r["content"])
            key_norm = _normalize_text(r["key"])

            # Direct match
            if q_norm and (q_norm in content_norm or q_norm in key_norm or key_norm in q_norm):
                matches.append(dict(r))
                continue

            # Token overlap match
            token_matches = sum(1 for t in tokens if t in content_norm or t in key_norm)
            if token_matches > 0:
                matches.append(dict(r))

        if not matches:
            return {
                "status": "not_found",
                "message": f"Não encontrei nenhuma lembrança ou anotação registrada sobre '{query}', senhor.",
                "memories": [],
            }

        # Format natural spoken response
        mem_descriptions = "; ".join(f"'{m['content']}'" for m in matches[:3])
        if len(matches) > 3:
            mem_descriptions += f" e mais {len(matches) - 3} outros registros"

        return {
            "status": "success",
            "message": f"Consultando minhas memórias sobre '{query}', recordo-me de que: {mem_descriptions}.",
            "count": len(matches),
            "memories": matches,
        }
    except Exception as exc:
        logger.error(f"Erro ao consultar memória para '{query}': {exc}")
        return {
            "status": "error",
            "message": f"Erro ao acessar as memórias: {exc}",
            "memories": [],
        }


def forget_memory(
    key: str,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Delete a memory entry by its key.

    Args:
        key: Identifier key or keyword of the memory to remove.
        db_path: Optional custom SQLite path for testing.
    """
    clean_key = key.strip().lower().replace(" ", "_")
    conn = _get_db_connection(db_path)

    try:
        with conn:
            cursor = conn.execute(
                "DELETE FROM memories WHERE key = ? OR key LIKE ?",
                (clean_key, f"%{clean_key}%"),
            )
            deleted_count = cursor.rowcount
        conn.close()

        if deleted_count > 0:
            return {
                "status": "success",
                "message": f"Anotação sobre '{key}' apagada da memória com sucesso, senhor.",
                "deleted": deleted_count,
            }
        else:
            return {
                "status": "not_found",
                "message": f"Nenhuma memória correspondente a '{key}' foi encontrada para remoção.",
                "deleted": 0,
            }
    except Exception as exc:
        logger.error(f"Erro ao esquecer memória '{key}': {exc}")
        return {
            "status": "error",
            "message": f"Erro ao remover memória: {exc}",
        }


def get_daily_briefing() -> Dict[str, Any]:
    """Aggregate Calendar, Tasks, Gmail, and preferences into a morning executive briefing."""
    from src.tools.google_calendar import get_calendar_events
    from src.tools.google_tasks import list_tasks
    from src.tools.gmail import list_unread_emails

    briefing_parts = []
    briefing_data: Dict[str, Any] = {}

    # 1. Greeting
    hour = datetime.now().hour
    if hour < 12:
        greeting = "Bom dia, senhor!"
    elif hour < 18:
        greeting = "Boa tarde, senhor!"
    else:
        greeting = "Boa noite, senhor!"

    briefing_parts.append(f"{greeting} Aqui está o seu resumo executivo de hoje.")

    # 2. Calendar section
    try:
        cal_res = get_calendar_events(time_min="hoje")
        briefing_data["calendar"] = cal_res
        if cal_res.get("status") == "success":
            events = cal_res.get("events", [])
            if events:
                evt_str = "; ".join(f"{e['summary']} às {e.get('display_time', '')}" for e in events[:3])
                briefing_parts.append(f"Na sua agenda, você tem {len(events)} compromisso(s): {evt_str}.")
            else:
                briefing_parts.append("Na sua agenda, não há nenhum compromisso agendado para hoje.")
        else:
            briefing_parts.append("A sincronização do Google Agenda não está configurada no momento.")
    except Exception as exc:
        logger.warning(f"Briefing calendar error: {exc}")

    # 3. Tasks section
    try:
        task_res = list_tasks(show_completed=False)
        briefing_data["tasks"] = task_res
        if task_res.get("status") == "success":
            tasks = task_res.get("tasks", [])
            if tasks:
                t_str = "; ".join(f"'{t['title']}'" for t in tasks[:3])
                briefing_parts.append(f"Nas tarefas pendentes, você possui {len(tasks)} item(ns): {t_str}.")
            else:
                briefing_parts.append("Você não tem nenhuma tarefa pendente na sua lista.")
        else:
            briefing_parts.append("O Google Tarefas aguarda autenticação.")
    except Exception as exc:
        logger.warning(f"Briefing tasks error: {exc}")

    # 4. Gmail section
    try:
        mail_res = list_unread_emails(max_results=3)
        briefing_data["gmail"] = mail_res
        if mail_res.get("status") == "success":
            emails = mail_res.get("emails", [])
            if emails:
                mail_str = "; ".join(f"de {m['from']} sobre '{m['subject']}'" for m in emails[:2])
                briefing_parts.append(f"No Gmail, há {len(emails)} novo(s) e-mail(s) não lido(s): {mail_str}.")
            else:
                briefing_parts.append("Sua caixa de entrada de e-mails está em dia, sem pendências não lidas.")
        else:
            briefing_parts.append("O Gmail aguarda autenticação.")
    except Exception as exc:
        logger.warning(f"Briefing gmail error: {exc}")

    briefing_parts.append("Estou à disposição para o que precisar. Desejo um excelente e produtivo dia!")
    spoken_briefing = " ".join(briefing_parts)

    return {
        "status": "success",
        "message": spoken_briefing,
        "briefing_details": briefing_data,
    }


def dispatch_memory_tool(tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatch Long-Term Semantic Memory and Executive Briefing tools."""
    if tool_name == "remember_fact":
        category = tool_args.get("category", "preferência")
        key = tool_args.get("key", "")
        content = tool_args.get("content", "")
        if not key or not content:
            return {"status": "error", "message": "Chave e conteúdo são obrigatórios para gravar memória."}
        return remember_fact(category=category, key=key, content=content)

    elif tool_name == "recall_memory":
        query = tool_args.get("query", "")
        if not query:
            return {"status": "error", "message": "Termo de busca é obrigatório para consultar memória."}
        return recall_memory(query=query, category=tool_args.get("category"))

    elif tool_name == "forget_memory":
        key = tool_args.get("key", "")
        if not key:
            return {"status": "error", "message": "Identificador da memória é obrigatório para remoção."}
        return forget_memory(key=key)

    elif tool_name == "get_daily_briefing":
        return get_daily_briefing()

    else:
        return {
            "status": "error",
            "message": f"Ferramenta de memória desconhecida '{tool_name}'.",
        }


# Gemini Live Function Declarations for Semantic Memory
MEMORY_FUNCTION_DECLARATIONS = [
    {
        "name": "remember_fact",
        "description": "Armazena uma preferência, fato pessoal, regra de trabalho ou instrução permanente na memória de longo prazo do Aton.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "key": {
                    "type": "STRING",
                    "description": "Identificador curto do fato (ex: 'resolucao_video', 'aniversario', 'cafe_favorito').",
                },
                "content": {
                    "type": "STRING",
                    "description": "O fato ou detalhe completo a ser lembrado (ex: 'O usuário prefere exportar vídeos em 4K 60fps').",
                },
                "category": {
                    "type": "STRING",
                    "description": "Categoria da memória: 'preferência', 'trabalho', 'pessoal' ou 'rotina' (padrão: 'preferência').",
                },
            },
            "required": ["key", "content"],
        },
    },
    {
        "name": "recall_memory",
        "description": "Consulta memórias, preferências e fatos permanentes guardados anteriormente pelo usuário.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": "Termo, pergunta ou assunto a ser buscado na memória (ex: 'qual resolução de vídeo?', 'aniversário').",
                },
                "category": {
                    "type": "STRING",
                    "description": "Filtro opcional de categoria ('preferência', 'trabalho', 'pessoal', 'rotina').",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "forget_memory",
        "description": "Apaga uma informação ou preferência registrada da memória de longo prazo.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "key": {
                    "type": "STRING",
                    "description": "A chave ou termo da memória a ser excluída.",
                },
            },
            "required": ["key"],
        },
    },
    {
        "name": "get_daily_briefing",
        "description": "Gera o resumo executivo matinal completo (Briefing do Dia), agregando compromissos da agenda, tarefas pendentes, novos e-mails e memórias do dia.",
        "parameters": {
            "type": "OBJECT",
            "properties": {},
            "required": [],
        },
    },
]
