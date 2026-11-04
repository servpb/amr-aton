"""
CLI utility for authenticating, checking status, and removing Google Calendar accounts
for Aton. Interactive OAuth 2.0 browser flow is strictly restricted to this CLI tool.

Usage:
  python scripts/autenticar_agenda.py [email_opcional]
  python scripts/autenticar_agenda.py --status [email_opcional]
  python scripts/autenticar_agenda.py --remove <email> [--revoke]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.integrations.calendar_service import get_calendar_connection_service


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="Gerenciador CLI OAuth 2.0 do Google Agenda para o Aton")
    parser.add_argument("email", nargs="?", default=None, help="E-mail esperado da conta Google (opcional)")
    parser.add_argument("--status", action="store_true", help="Verifica a conexão ativa com o Google Agenda")
    parser.add_argument("--remove", metavar="EMAIL", help="Remove o token local da conta informada")
    parser.add_argument("--revoke", action="store_true", help="Revoga também o token remotamente no Google")
    args = parser.parse_args()

    service = get_calendar_connection_service()

    if args.remove:
        res = service.remove_account(args.remove, revoke=args.revoke)
        print(f"[AGENDA] {res.get('message')}")
        return 0 if res.get("ok") else 1

    if args.status:
        index = service.load_accounts_index()
        accounts = index.get("accounts") or {}
        default_acct = index.get("default_account")
        print("=== Status do Google Agenda (Aton) ===")
        print(f"Conta padrão configurada: {default_acct or '(nenhuma / legado)'}")
        if accounts:
            print(f"Contas registradas ({len(accounts)}):")
            for email_key, meta in accounts.items():
                print(f"  - {email_key} (fuso: {meta.get('timezone')}, arquivo: {meta.get('token_file')})")
        status = service.check_connection(account=args.email)
        print(f"Resultado da verificação: {status.get('message')}")
        return 0 if status.get("ok") else 1

    print("[AGENDA] Iniciando autenticação OAuth 2.0 Desktop no navegador...")
    res = service.authenticate_interactive(expected_email=args.email, set_as_default=True)
    print(f"[AGENDA] {res.get('message')}")
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
