"""Documentation Ingestion and Synchronization for Aton Second Brain.

Reads all system documentation files (GEMINI.md, docs/*.md), generates 768d vector
embeddings, and synchronizes them into Supabase 'base_conhecimento' and 'memoria_longo_prazo',
with local SQLite caching (amr_memory.db) and JSON backup for offline resilience.
"""

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any, Dict, List, Optional
import urllib.parse
import urllib.request

# Ensure UTF-8 output on Windows terminal
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure workspace root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.config import settings
from src.core.second_brain import SecondBrainClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def extract_doc_metadata(file_path: Path) -> Dict[str, Any]:
    """Parse title, summary, and tags from a markdown document."""
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"Error reading {file_path}: {e}")
        return {}

    lines = [line.strip() for line in content.splitlines()]
    title = file_path.stem.replace("_", " ").title()
    summary = ""
    tags = ["documentacao", "aton", file_path.stem.lower()]

    # Extract first H1 as title
    for line in lines:
        if line.startswith("# ") and len(line) > 2:
            title = line[2:].strip()
            break

    # Extract first non-empty descriptive paragraph
    for line in lines:
        if line and not line.startswith(("#", ">", "-", "*", "|", "`", "```")):
            summary = line[:250].strip()
            break

    if not summary:
        summary = f"Documentação técnica e guia do módulo {title} do Aton."

    # Extract tags from title keywords
    keywords = ["audio", "camera", "visao", "tela", "tv", "luz", "iot", "gps", "maps",
                "email", "gmail", "tarefa", "agenda", "memoria", "cerebro", "banco",
                "windows", "processo", "atalho", "digita", "volume", "telemetria"]
    for kw in keywords:
        if kw in content.lower():
            tags.append(kw)

    return {
        "file_name": file_path.name,
        "file_path": str(file_path.as_posix()),
        "title": title,
        "summary": summary,
        "content": content,
        "tags": list(set(tags)),
    }


def sync_documentation():
    """Main execution: ingest docs into Supabase and local SQLite."""
    logger.info("Initializing SecondBrainClient...")
    client = SecondBrainClient()

    root_dir = Path(__file__).resolve().parent.parent
    docs_dir = root_dir / "docs"
    gemini_file = root_dir / "GEMINI.md"

    files_to_sync: List[Path] = []
    if gemini_file.exists():
        files_to_sync.append(gemini_file)

    if docs_dir.exists():
        for f in sorted(docs_dir.glob("*.md")):
            files_to_sync.append(f)

    logger.info(f"Discovered {len(files_to_sync)} markdown documents to index into Second Brain.")

    # Local SQLite Setup
    db_path = settings.memory_db_path or "amr_memory.db"
    conn = sqlite3.connect(db_path)
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

    cached_records = []
    synced_supabase = 0
    synced_sqlite = 0

    for idx, f in enumerate(files_to_sync, start=1):
        meta = extract_doc_metadata(f)
        if not meta:
            continue

        title = meta["title"]
        content = meta["content"]
        summary = meta["summary"]
        tags = meta["tags"]
        file_name = meta["file_name"]

        logger.info(f"[{idx}/{len(files_to_sync)}] Processing '{title}' ({file_name})...")

        # 1. Generate 768d Vector Embedding
        text_for_embedding = f"{title}\n{summary}\n\n{content[:2000]}"
        embedding = client.get_embedding(text_for_embedding)
        has_embedding = bool(embedding and len(embedding) == 768)

        # 2. Sync to Supabase base_conhecimento
        if client.is_configured:
            try:
                # Check existing in base_conhecimento
                safe_title = urllib.parse.quote(title)
                existing_bc = client._supabase_request(f"base_conhecimento?titulo=eq.{safe_title}&select=id", method="GET")

                bc_payload = {
                    "categoria": "documentacao_modulo",
                    "titulo": title,
                    "conteudo": content,
                    "resumo": summary,
                    "tags": tags,
                    "links_referencia": [f"file:///{f.as_posix()}"],
                    "metadados": {
                        "arquivo": file_name,
                        "modulo_aton": True,
                        "versao_sistema": "0.8.0",
                        "atualizado_em": datetime.now(timezone.utc).isoformat(),
                    },
                }

                if existing_bc and isinstance(existing_bc, list) and len(existing_bc) > 0:
                    bc_id = existing_bc[0]["id"]
                    client._supabase_request(f"base_conhecimento?id=eq.{bc_id}", payload=bc_payload, method="PATCH")
                else:
                    client._supabase_request("base_conhecimento", payload=bc_payload, method="POST")

                # 3. Sync to Supabase memoria_longo_prazo (Vector Search)
                safe_assunto = urllib.parse.quote(f"Documentação: {title}")
                existing_mlp = client._supabase_request(f"memoria_longo_prazo?assunto=eq.{safe_assunto}&select=id", method="GET")

                mlp_payload = {
                    "tipo": "documentacao",
                    "assunto": f"Documentação: {title}",
                    "conteudo": content[:5000],  # Concise chunk for vector search context
                    "resumo": summary,
                    "tags": tags,
                    "importancia": 5,
                    "embedding": embedding if has_embedding else None,
                    "embedding_pendente": not has_embedding,
                    "status": "ativa",
                    "fonte": "docs_sistema",
                    "metadados": {"arquivo": file_name},
                }

                if existing_mlp and isinstance(existing_mlp, list) and len(existing_mlp) > 0:
                    mlp_id = existing_mlp[0]["id"]
                    client._supabase_request(f"memoria_longo_prazo?id=eq.{mlp_id}", payload=mlp_payload, method="PATCH")
                else:
                    client._supabase_request("memoria_longo_prazo", payload=mlp_payload, method="POST")

                synced_supabase += 1
            except Exception as e:
                logger.error(f"Error syncing {file_name} to Supabase: {e}")

        # 4. Sync to local SQLite (amr_memory.db)
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            clean_key = f"doc_{file_name.lower().replace('.', '_')}"
            sql_payload = f"Título: {title}\nResumo: {summary}\nTags: {', '.join(tags)}\n\n{content[:2500]}"
            conn.execute(
                """
                INSERT INTO memories (category, key, content, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    content = excluded.content,
                    updated_at = excluded.updated_at
                """,
                ("documentacao", clean_key, sql_payload, now_iso, now_iso),
            )
            conn.commit()
            synced_sqlite += 1
        except Exception as e:
            logger.error(f"Error syncing {file_name} to local SQLite: {e}")

        # Add to JSON cache
        cached_records.append({
            "arquivo": file_name,
            "titulo": title,
            "resumo": summary,
            "tags": tags,
            "has_embedding": has_embedding,
            "atualizado_em": datetime.now(timezone.utc).isoformat(),
        })

    conn.close()

    # 5. Save local JSON cache in data/
    data_dir = root_dir / "data"
    data_dir.mkdir(exist_ok=True)
    cache_file = data_dir / "aton_documentacao_cache.json"
    cache_data = {
        "atualizado_em": datetime.now(timezone.utc).isoformat(),
        "total_documentos": len(cached_records),
        "documentos": cached_records,
    }
    cache_file.write_text(json.dumps(cache_data, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"Local documentation cache written to {cache_file} ({len(cached_records)} records).")

    print("\n" + "=" * 65)
    print("SINCRONIZAÇÃO DE DOCUMENTAÇÃO NO SEGUNDO CÉREBRO CONCLUÍDA")
    print("=" * 65)
    print(f"Total de documentos lidos:         {len(files_to_sync)}")
    print(f"Sincronizados no Supabase:         {synced_supabase}")
    print(f"Sincronizados no SQLite local:     {synced_sqlite}")
    print(f"Cache JSON offline salvo em:       {cache_file.name}")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    sync_documentation()
