"""CLI utility to authenticate, check status, or remove Gmail OAuth 2.0 Desktop accounts in Aton."""

import argparse
from pathlib import Path
import sys

# Ensure project root is on sys.path when invoked directly
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.integrations.gmail_service import get_gmail_service


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ATON - Gerenciador Multi-Contas de Conexão e Autenticação OAuth 2.0 do Gmail"
    )
    parser.add_argument(
        "positional_email",
        nargs="?",
        default=None,
        help="Opcional. Endereço de e-mail da conta alvo (ex: cursopb@gmail.com).",
    )
    parser.add_argument(
        "--email",
        "--account",
        dest="email",
        default=None,
        help="Endereço de e-mail da conta esperada para autenticar, consultar ou remover.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Verifica passivamente o status atual das contas conectadas sem abrir o navegador.",
    )
    parser.add_argument(
        "--remove",
        metavar="EMAIL",
        default=None,
        help="Desconecta e remove o token local de uma conta específica no Aton.",
    )
    parser.add_argument(
        "--revoke",
        action="store_true",
        help="Usado com --remove: além de apagar o token local, solicita a revogação remota nos servidores do Google.",
    )
    args = parser.parse_args()

    target_email = args.remove or args.email or args.positional_email
    service = get_gmail_service()

    print("=" * 68)
    print("       ATON - Conexão Multi-Contas com Gmail (OAuth 2.0 Desktop)")
    print("=" * 68)
    print(f" [Arquivo de Credenciais]: {service.credentials_path}")
    print(f" [Diretório de Tokens]:    {service.tokens_dir}")
    print(f" [Índice de Contas]:       {service.index_path}")
    print(f" [Escopos Solicitados]:    {', '.join(service.scopes)}")
    print("-" * 68)

    if args.remove:
        print(f"[INFO] Removendo a conta '{args.remove}' do Aton (revoke_remote={args.revoke})...")
        result = service.remove_account(account=args.remove, revoke_remote=args.revoke)
        status = result.get("status", "unknown")
        message = result.get("message", "")
        print(f"\n[STATUS]: {status}")
        print(f"[MENSAGEM]: {message}")
        remaining = result.get("remaining_accounts", [])
        print(f"[CONTAS RESTANTES ({len(remaining)})]: {', '.join(remaining) if remaining else 'nenhuma'}")
        print("=" * 68)
        return 0 if status == "removed" else 1

    if args.status:
        if target_email:
            print(f"[INFO] Verificando status da conta '{target_email}' (modo passivo)...")
        else:
            print("[INFO] Verificando status de todas as contas do Gmail cadastradas (modo passivo)...")
        result = service.check_connection(account=target_email)
        status = result.get("status", "unknown")
        message = result.get("message", "")
        print(f"\n[STATUS]: {status}")
        print(f"[MENSAGEM]: {message}")

        accounts_list = result.get("accounts")
        if isinstance(accounts_list, list) and accounts_list:
            print("\n[DETALHAMENTO POR CONTA]:")
            for item in accounts_list:
                acc_mail = item.get("email", "?")
                acc_st = item.get("status", "?")
                if acc_st == "connected":
                    total_msgs = item.get("messages_total", 0)
                    print(f"  - {acc_mail}: CONECTADA ({total_msgs} mensagens totais)")
                else:
                    print(f"  - {acc_mail}: {acc_st} -> {item.get('message', '')}")
        elif result.get("email_address"):
            print(f"[CONTA ATIVA]: {result.get('email_address')}")

        print(
            "\n[AVISO MODO TESTANDO]: Enquanto o app OAuth estiver em modo 'Testando' (Externo) no "
            "Google Cloud, os tokens de atualização do Gmail expiram após 7 dias."
        )
        print("=" * 68)
        return 0 if status in ("authenticated", "connected") else 1

    # Interactive authentication mode
    if target_email:
        print(f"[INFO] Iniciando autenticação OAuth 2.0 no navegador para a conta esperada: {target_email}")
        print("       (Se você selecionar outra conta por engano no navegador, o Aton cancelará sem sobrescrever nada.)")
    else:
        print("[INFO] Iniciando autenticação interativa do Gmail no navegador...")

    result = service.authenticate_interactive(open_browser=True, expected_email=target_email)
    status = result.get("status", "unknown")
    message = result.get("message", "")

    print(f"\n[STATUS]: {status}")
    print(f"[MENSAGEM]: {message}")
    if result.get("connected_accounts"):
        conns = result["connected_accounts"]
        print(f"[CONTAS CONECTADAS ({len(conns)})]: {', '.join(conns)}")
    print(
        "\n[AVISO MODO TESTANDO]: Lembre-se de que em modo 'Testando' (Externo) no Google Cloud, "
        "os tokens do Gmail expiram a cada 7 dias."
    )
    print("=" * 68)

    return 0 if status in ("authenticated", "connected") else 1


if __name__ == "__main__":
    sys.exit(main())
