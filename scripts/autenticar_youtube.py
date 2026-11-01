"""CLI utility to authenticate, list channels, check status, or remove YouTube OAuth 2.0 Desktop accounts/channels in Aton."""

import argparse
from pathlib import Path
import sys

# Ensure project root is on sys.path when invoked directly
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.integrations.youtube_service import (
    YOUTUBE_MANAGE_SCOPES,
    YOUTUBE_READONLY_SCOPES,
    get_youtube_service,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ATON - Gerenciador Multi-Contas e Multi-Canais do YouTube (OAuth 2.0 Desktop)"
    )
    parser.add_argument(
        "positional_target",
        nargs="?",
        default=None,
        help="Opcional. Endereço de e-mail da conta alvo (ex: cursopb@gmail.com ou servpb@gmail.com) ou ID do canal.",
    )
    parser.add_argument(
        "--email",
        "--account",
        dest="email",
        default=None,
        help="Endereço de e-mail esperado da conta Google.",
    )
    parser.add_argument(
        "--mode",
        choices=["manage", "readonly"],
        default="manage",
        help="Modo de escopos OAuth: 'manage' (leitura + escrita/upload) ou 'readonly' (somente leitura). Padrão: manage.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Verifica passivamente o status atual das contas e canais conectados sem abrir o navegador.",
    )
    parser.add_argument(
        "--channels",
        action="store_true",
        help="Lista detalhadamente os canais do YouTube autenticados e verifica o canal UCYCmXtIR-tbWCyrwbLdczyA.",
    )
    parser.add_argument(
        "--remove",
        metavar="ALVO",
        default=None,
        help="Desconecta e remove o token local de um canal (ID UC...) ou conta (e-mail) no Aton.",
    )
    parser.add_argument(
        "--revoke",
        action="store_true",
        help="Usado com --remove: além de apagar o token local, solicita revogação remota nos servidores do Google.",
    )
    args = parser.parse_args()

    target = args.remove or args.email or args.positional_target
    service = get_youtube_service()
    scopes_preview = YOUTUBE_READONLY_SCOPES if args.mode == "readonly" else YOUTUBE_MANAGE_SCOPES

    print("=" * 74)
    print("    ATON - Conexão Multi-Contas e Multi-Canais YouTube (OAuth 2.0 Desktop)")
    print("=" * 74)
    print(f" [Arquivo de Credenciais]: {service.credentials_path}")
    print(f" [Diretório de Tokens]:    {service.tokens_dir}")
    print(f" [Índice de Canais]:       {service.index_path}")
    print(f" [Modo Selecionado]:       {args.mode} ({', '.join(scopes_preview)})")
    print("-" * 74)

    if args.remove:
        print(f"[INFO] Removendo '{args.remove}' do Aton (revoke_remote={args.revoke})...")
        result = service.remove_account_or_channel(target=args.remove, revoke_remote=args.revoke)
        status = result.get("status", "unknown")
        print(f"\n[STATUS]: {status}")
        print(f"[MENSAGEM]: {result.get('message', '')}")
        print(f"[ENTRADAS RESTANTES]: {result.get('remaining_count', 0)}")
        print("=" * 74)
        return 0 if status == "removed" else 1

    if args.status or args.channels:
        if target:
            print(f"[INFO] Verificando canais e status para '{target}' (modo passivo, sem navegador)...")
        else:
            print("[INFO] Verificando todas as contas e canais do YouTube conectados (modo passivo)...")

        result = service.check_connection_and_channels(account=target)
        status = result.get("status", "unknown")
        print(f"\n[STATUS GERAL]: {status}")
        print(f"[MENSAGEM]: {result.get('message', '')}")

        channels = result.get("channels", [])
        if channels:
            print(f"\n[CANAIS AUTENTICADOS ({len(channels)})]:")
            for idx, ch in enumerate(channels, start=1):
                print(
                    f"  {idx}. {ch.get('title')} [{ch.get('channel_id')}] ({ch.get('custom_url') or 'sem @handle'})\n"
                    f"     Conta Google: {ch.get('account_email')} | Modo: {ch.get('access_mode')}\n"
                    f"     Inscritos: {ch.get('subscriber_count')} | Vídeos: {ch.get('video_count')} | "
                    f"Views totais: {ch.get('view_count')}"
                )
        else:
            print("\n[CANAIS AUTENTICADOS]: Nenhum canal ativo encontrado.")

        target_check = result.get("target_channel_check", {})
        if target_check:
            print("\n[VERIFICAÇÃO DO CANAL ALVO UCYCmXtIR-tbWCyrwbLdczyA]:")
            print(f"  - Autorizado: {'SIM' if target_check.get('authorized') else 'NÃO'}")
            print(f"  - Detalhe: {target_check.get('message', '')}")

        print(
            "\n[DICA CONTAS DE MARCA (BRAND ACCOUNTS)]:\n"
            "  Uma mesma conta Google pode administrar vários canais/Contas de Marca.\n"
            "  Como `channels.list(mine=True)` retorna o canal associado à identidade escolhida\n"
            "  na tela de consentimento do Google, repita `run.bat youtube-auth <email>` para cada\n"
            "  Conta de Marca adicional — o Aton salvará um arquivo de token separado por (conta + canal)."
        )
        print("=" * 74)
        return 0 if status == "connected" else 1

    # Interactive authentication flow
    if target:
        print(f"[INFO] Iniciando autenticação OAuth 2.0 no navegador para a conta esperada: {target} (modo: {args.mode})")
        print("       (Se a conta tiver mais de um canal/Conta de Marca, selecione a identidade do canal desejado.)")
    else:
        print(f"[INFO] Iniciando autenticação interativa do YouTube no navegador (modo: {args.mode})...")

    result = service.authenticate_interactive(
        open_browser=True,
        expected_email=target,
        mode=args.mode,
    )
    status = result.get("status", "unknown")
    print(f"\n[STATUS]: {status}")
    print(f"[MENSAGEM]: {result.get('message', '')}")

    channels = result.get("channels", [])
    if channels:
        print(f"\n[CANAL(IS) VINCULADO(S) NESTA SESSÃO ({len(channels)})]:")
        for ch in channels:
            print(
                f"  - {ch.get('title')} [{ch.get('channel_id')}] "
                f"(conta: {ch.get('account_email')}, modo: {ch.get('access_mode')}, "
                f"{ch.get('subscriber_count')} inscritos, {ch.get('video_count')} vídeos)"
            )

    print(
        "\n[AVISO MODO TESTANDO]: Enquanto o app OAuth estiver em modo 'Testando' (Externo) no "
        "Google Cloud, os tokens de atualização expiram após 7 dias."
    )
    print("=" * 74)
    return 0 if status in ("authenticated", "authenticated_no_channels") else 1


if __name__ == "__main__":
    sys.exit(main())

