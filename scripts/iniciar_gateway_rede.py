"""Script para inicializar o Aton Mobile Gateway e Descoberta em Rede para testes interativos.

Permite testar pareamento por PIN de uso único, permissões granulares e interface
multi-dispositivo no PC, no smartphone e na Smart TV.
"""

import asyncio
import logging
from pathlib import Path
import sys

# Garantir raiz do projeto no sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import settings
from src.core.network_discovery import NetworkDiscovery
from src.integrations.mobile_gateway import MobileGatewayServer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("AtonGateway")


async def main() -> None:
    discovery = NetworkDiscovery()
    interfaces = discovery.get_local_interfaces()
    primary_ip = discovery.get_primary_ip()
    port = settings.gateway_port

    print("\n" + "=" * 65)
    print("   ATON - MOBILE GATEWAY & SERVICO EM REDE ATIVO (FASE 11)")
    print("=" * 65)
    print(f"Porta do Servidor:  {port}")
    print(f"IP Principal:       {primary_ip}\n")
    print("Interfaces de Rede Locais Detectadas:")
    for iface in interfaces:
        ip = iface.get("ip_address") or iface.get("ip", "")
        if ip and iface.get("is_up") and not iface.get("is_loopback"):
            tipo = iface.get("type", "lan").upper()
            nome = iface.get("interface_name") or iface.get("name", "Desconhecido")
            print(f"  • {nome} [{tipo}]: http://{ip}:{port}")

    print(f"  • Computador Local: http://localhost:{port}")
    print("=" * 65)
    print("COMO TESTAR AGORA:")
    print(f"1. No PC Anfitrião: Abra o link: http://localhost:{port}")
    print(f"2. No Smartphone (mesmo Wi-Fi): Abra: http://{primary_ip}:{port}")
    print("3. Na aba 'Rede', faca a solicitacao de pareamento:")
    print("   - O ATON gerara um PIN numerico de 6 digitos.")
    print("   - Confirme o PIN e as permissoes desejadas.")
    print("4. Teste os comandos de voz (PTT), acoes rapidas e o modo Smart TV.")
    print("5. Para encerrar o teste, pressione Ctrl+C neste terminal.")
    print("=" * 65 + "\n")

    server = MobileGatewayServer(
        assistant=None,
        host=settings.gateway_host,
        port=port,
        api_token=settings.gateway_api_token,
    )

    started = await server.start()
    if not started:
        print("[ERRO] Nao foi possivel iniciar o servidor Gateway.")
        sys.exit(1)

    print(f"[OK] Servidor escutando em {settings.gateway_host}:{port} e mDNS ativo!")
    sys.stdout.flush()

    try:
        while True:
            await asyncio.sleep(1)
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        print("\n[INFO] Encerrando Mobile Gateway e anuncio mDNS...")
        await server.stop()
        print("[OK] Servidor finalizado.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
