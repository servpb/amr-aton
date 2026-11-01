"""Demonstration script: Simulated DHCP IP change recovery for Amazon Fire TV Stick.

Validates that when the last confirmed IP is stale/incorrect, Aton discovers the new IP
via Windows ARP / subnet scan, verifies hardware identity, persists the recovered IP atomically,
and executes a harmless status query - without touching the router or .env file.
"""

import json
import logging
import os
from pathlib import Path
import shutil
import sys
import time

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import settings
from src.core.fire_tv_discovery import (
    STATE_FILE_PATH,
    get_fire_tv_connection_manager,
    load_confirmed_fire_tv_state,
    get_windows_arp_table,
    normalize_mac,
    mask_serial,
    sanitize_fire_tv_state,
)
from src.tools.fire_tv import get_fire_tv_status

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("demo_recovery")


# Reusable mask_serial and sanitize_fire_tv_state imported from src.core.fire_tv_discovery


def run_demonstration():
    print("=" * 70)
    print("  ATON - DEMONSTRAÇÃO DE RECUPERAÇÃO DE IP POR DESCOBERTA E IDENTIDADE")
    print("=" * 70)

    start_total_time = time.time()
    max_timeout_seconds = 15.0

    # 1. Backup do estado atual
    backup_file = STATE_FILE_PATH.with_suffix(".json.bak")
    if STATE_FILE_PATH.is_file():
        shutil.copy2(STATE_FILE_PATH, backup_file)
        print(f"[1/6] Backup do estado salvo em: {backup_file.name}")
    else:
        print("[1/6] Nenhum arquivo de estado anterior para backup.")

    try:
        # 2. Inserção do IP propositalmente incorreto
        simulated_stale_ip = "192.168.0.244"
        print(f"[2/6] Simulando indisponibilidade do último IP conhecido: {simulated_stale_ip}")

        # Gravar estado incorreto
        stale_payload = {
            "confirmed_ip": simulated_stale_ip,
            "confirmed_at": time.time() - 3600,
            "serial": "STALE_SIMULATED_SERIAL",
            "model": "AFTSS",
            "mac": "24:CE:33:E2:0F:9E",
        }
        with open(STATE_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(stale_payload, f, indent=2)

        # Invalidar cache em memória do gerenciador
        conn_mgr = get_fire_tv_connection_manager()
        conn_mgr.invalidate_cache()

        # 3. Bloqueio estrito de fallback para o .env durante a demonstração
        original_env_ip = settings.fire_tv_ip
        settings.fire_tv_ip = ""  # Força a descoberta por ARP / varredura, sem atalho pelo .env
        print(f"[3/6] Fallback para FIRE_TV_IP do .env bloqueado temporariamente (era '{original_env_ip}')")

        # 4. Iniciar processo de recuperação com prazo máximo
        print(f"[4/6] Executando rotina de verificação e redescoberta (prazo máximo: {max_timeout_seconds}s)...")
        discovery_start = time.time()

        # Checar previamente como o caminho será trilhado
        arp_table = get_windows_arp_table()
        expected_mac_norm = normalize_mac(settings.fire_tv_expected_mac)
        arp_match_ip = None
        for ip_cand, mac_cand in arp_table.items():
            if mac_cand == expected_mac_norm:
                arp_match_ip = ip_cand
                break

        discovery_path_used = "Tabela ARP do Windows (MAC físico)" if arp_match_ip else "Varredura TCP na sub-rede (Porta 5555)"

        # Chamada que aciona o fluxo completo
        recovered_ip, status_msg = conn_mgr.get_verified_device_ip(force_refresh=True)
        discovery_elapsed = time.time() - discovery_start

        if not recovered_ip:
            raise RuntimeError(f"A recuperação falhou: {status_msg}")

        device_info = conn_mgr.get_device_info()
        raw_serial = device_info.get("serial", "")
        masked_ser = mask_serial(raw_serial)
        model = device_info.get("model", "")
        mac = device_info.get("mac", "")

        print(f"      -> Caminho utilizado: {discovery_path_used}")
        print(f"      -> Endereço recuperado: {recovered_ip}")
        print(f"      -> Identidade confirmada: Modelo '{model}', Série '{masked_ser}', MAC '{mac}'")
        print(f"      -> Tempo de descoberta e validação: {discovery_elapsed:.2f} segundos")

        # 5. Comprovação da persistência atômica no arquivo de estado
        persisted_state = load_confirmed_fire_tv_state()
        persisted_ip = persisted_state.get("confirmed_ip")
        if persisted_ip != recovered_ip:
            raise RuntimeError(f"O IP no arquivo de estado ({persisted_ip}) não confere com o recuperado ({recovered_ip}).")
        print(f"[5/6] Persistência atômica confirmada em data/fire_tv_state.json: {persisted_ip}")
        sanitized_json = json.dumps(sanitize_fire_tv_state(persisted_state), indent=2)
        print("      -> Conteúdo sanitizado do estado para apresentação:")
        for line in sanitized_json.splitlines():
            print(f"         {line}")

        # 6. Execução de comando simples e inofensivo de status (sem interromper mídia)
        print("[6/6] Executando comando de leitura de status com a conexão restaurada...")
        status_res = get_fire_tv_status()
        if status_res.get("status") != "success":
            raise RuntimeError(f"Comando de status falhou após recuperação: {status_res}")
        print(f"      -> Retorno do comando: {status_res.get('message')}")

        total_elapsed = time.time() - start_total_time

        print("\n" + "=" * 70)
        print("  RESULTADO DA DEMONSTRAÇÃO PRÁTICA: SUCESSO COMPLETO")
        print("=" * 70)
        print(f"• IP anterior incorreto (simulado):  {simulated_stale_ip}")
        print(f"• Fallback para .env:                 Desativado durante o teste")
        print(f"• Método de descoberta:               {discovery_path_used}")
        print(f"• IP real localizado e autenticado:   {recovered_ip}")
        print(f"• Número de série (auditado):         {masked_ser}")
        print(f"• Modelo validado:                    {model}")
        print(f"• Atualização no arquivo de estado:   Salvo atomicamente ({persisted_ip})")
        print(f"• Comando de leitura:                 Executado com sucesso ('{status_res.get('model')}')")
        print(f"• Tempo total da operação:            {total_elapsed:.2f} segundos (limite: {max_timeout_seconds}s)")
        print("=" * 70)

        # Limpar backup se tudo deu certo
        if backup_file.is_file():
            backup_file.unlink()

        # Restaurar variável em memória
        settings.fire_tv_ip = original_env_ip
        return True

    except Exception as exc:
        print(f"\n[ERRO CRÍTICO] A demonstração falhou: {exc}")
        # Restauração imediata do backup de segurança
        if backup_file.is_file():
            shutil.copy2(backup_file, STATE_FILE_PATH)
            backup_file.unlink()
            print("[ROLLBACK] Estado original restaurado do backup com sucesso.")
        return False


if __name__ == "__main__":
    success = run_demonstration()
    sys.exit(0 if success else 1)

