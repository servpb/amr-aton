"""Backup Script for Supabase Second Brain Tables.

Exports full database state (all 18 tables) in both JSON and CSV formats
with timestamped directory and filenames prior to schema migrations.
"""

import csv
from datetime import datetime, timezone
import json
import logging
import os
import sys

# Ensure workspace root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from typing import Any, Dict, List
from src.core.second_brain import SecondBrainClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

TABLES = [
    "modulos_sistema",
    "auditoria_sistema",
    "perfil_criador",
    "historico_decisoes",
    "clientes",
    "contatos_clientes",
    "interacoes_clientes",
    "projetos",
    "etapas_projeto",
    "ideias_projetos",
    "tarefas",
    "dependencias_tarefas",
    "agenda_eventos",
    "lembretes_agenda",
    "base_conhecimento",
    "conversas_sessao",
    "turnos_conversa",
    "memoria_longo_prazo",
]


def run_backup() -> Dict[str, Any]:
    """Execute complete backup of all Supabase tables."""
    client = SecondBrainClient()
    if not client.is_configured:
        logger.error("Supabase client is not configured. Check SUPABASE_URL and SUPABASE_KEY in .env.")
        sys.exit(1)

    now_utc = datetime.now(timezone.utc)
    timestamp_str = now_utc.strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.abspath(os.path.join("backups", f"backup_{timestamp_str}"))
    os.makedirs(backup_dir, exist_ok=True)

    backup_data: Dict[str, List[Dict[str, Any]]] = {}
    record_counts: Dict[str, int] = {}
    csv_files: Dict[str, str] = {}

    logger.info(f"Starting database backup to: {backup_dir}")

    for table in TABLES:
        # Request all rows for the table
        endpoint = f"{table}?select=*"
        rows = client._supabase_request(endpoint, method="GET")

        if rows is None:
            logger.error(f"FATAL: Failed to fetch table '{table}' from Supabase.")
            sys.exit(1)

        if not isinstance(rows, list):
            logger.error(f"FATAL: Unexpected response format for table '{table}': {type(rows)}")
            sys.exit(1)

        count = len(rows)
        record_counts[table] = count
        backup_data[table] = rows

        # Write individual table CSV
        csv_filename = f"backup_{timestamp_str}_{table}.csv"
        csv_filepath = os.path.join(backup_dir, csv_filename)

        if count > 0:
            fieldnames = list(rows[0].keys())
        else:
            # Fallback headers for empty tables
            fieldnames = ["id", "created_at"]

        with open(csv_filepath, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for r in rows:
                row_serialized = {}
                for k, v in r.items():
                    if isinstance(v, (dict, list)):
                        row_serialized[k] = json.dumps(v, ensure_ascii=False)
                    else:
                        row_serialized[k] = v
                writer.writerow(row_serialized)

        csv_files[table] = csv_filepath
        logger.info(f"✓ Table '{table}': {count} records exported -> {csv_filename}")

    # Write unified JSON backup
    json_filename = f"backup_{timestamp_str}_full.json"
    json_filepath = os.path.join(backup_dir, json_filename)
    payload = {
        "metadata": {
            "backup_name": f"backup_{timestamp_str}",
            "created_at_utc": now_utc.isoformat(),
            "supabase_project": client.supabase_url,
            "total_tables": len(TABLES),
            "record_counts": record_counts,
            "total_records": sum(record_counts.values()),
        },
        "tables": backup_data,
    }

    with open(json_filepath, mode="w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    logger.info(f"✓ Unified JSON backup generated: {json_filepath}")
    logger.info(f"BACKUP COMPLETED SUCCESSFULLY. Total records: {sum(record_counts.values())}")

    return {
        "status": "success",
        "backup_dir": backup_dir,
        "json_file": json_filepath,
        "csv_files": csv_files,
        "counts": record_counts,
        "timestamp": timestamp_str,
        "total_records": sum(record_counts.values()),
    }


if __name__ == "__main__":
    result = run_backup()
    print("\n--- RESUMO DO BACKUP ---")
    print(f"Diretório: {result['backup_dir']}")
    print(f"Arquivo JSON: {result['json_file']}")
    print(f"Total de registros exportados: {result['total_records']}")
    for tbl, cnt in result["counts"].items():
        print(f"  - {tbl}: {cnt} registros")
