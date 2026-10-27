"""Network discovery and authorized devices tools for ATON (Phase 11)."""

import logging
from typing import Any, Dict, List, Optional
from src.core.device_manager import DeviceManager
from src.core.network_discovery import NetworkDiscovery

logger = logging.getLogger(__name__)

# Singleton instances for tool operations
_device_manager: Optional[DeviceManager] = None
_network_discovery: Optional[NetworkDiscovery] = None


def get_device_manager() -> DeviceManager:
    """Return shared DeviceManager instance."""
    global _device_manager
    if _device_manager is None:
        _device_manager = DeviceManager()
    return _device_manager


def get_network_discovery() -> NetworkDiscovery:
    """Return shared NetworkDiscovery instance."""
    global _network_discovery
    if _network_discovery is None:
        _network_discovery = NetworkDiscovery()
    return _network_discovery


def get_network_info() -> Dict[str, Any]:
    """Obter as interfaces de rede locais ativas e os endereços IP do computador anfitrião do ATON.

    Returns:
        Informações sobre IPs locais, Wi-Fi, Ethernet, Tailscale e porta do gateway.
    """
    nd = get_network_discovery()
    interfaces = nd.get_local_interfaces()
    primary_ip = nd.get_primary_ip()

    active_ips = [
        f"{iface['interface_name']} ({iface['type']}): {iface['ip_address']}"
        for iface in interfaces
        if iface["is_up"] and not iface["is_loopback"]
    ]

    msg = (
        f"Endereço IP principal do ATON: {primary_ip}\n"
        f"Porta de serviço: 8443\n"
        f"Acesso local no navegador: http://{primary_ip}:8443\n\n"
        f"Interfaces ativas detectadas:\n" + "\n".join(f"- {ip}" for ip in active_ips)
    )

    return {
        "status": "success",
        "primary_ip": primary_ip,
        "port": 8443,
        "interfaces": interfaces,
        "message": msg,
    }


def list_network_devices() -> Dict[str, Any]:
    """Listar todos os dispositivos pareados e autorizados a se comunicar com o ATON, incluindo permissões e IP.

    Returns:
        Lista de dispositivos pareados com status, tipo, permissões e solicitações pendentes.
    """
    dm = get_device_manager()
    paired = dm.list_devices()
    pending = dm.get_pending_requests()

    lines = []
    if paired:
        lines.append(f"Dispositivos pareados ({len(paired)}):")
        for d in paired:
            perms_str = ", ".join(d.get("permissions", []))
            lines.append(
                f"- {d['device_name']} [{d['device_type'].upper()}] - IP: {d['last_ip']} "
                f"(Status: {d['status']}, Permissões: {perms_str})"
            )
    else:
        lines.append("Nenhum dispositivo externo pareado no momento.")

    if pending:
        lines.append(f"\nSolicitações de pareamento pendentes ({len(pending)}):")
        for p in pending:
            lines.append(
                f"- '{p['device_name']}' ({p['client_ip']}) - PIN: {p['pin_code']} "
                f"(Expira em {p['expires_in_seconds']}s)"
            )

    return {
        "status": "success",
        "paired_devices": paired,
        "pending_requests": pending,
        "message": "\n".join(lines),
    }


def revoke_network_device(device_identifier: str) -> Dict[str, Any]:
    """Revogar imediatamente a autorização e o acesso de um dispositivo previamente pareado.

    Args:
        device_identifier: Nome amigável do dispositivo (ex: 'Galaxy S24') ou seu ID único UUID.

    Returns:
        Status do encerramento da conexão e revogação do token.
    """
    dm = get_device_manager()
    success = dm.revoke_device(device_identifier)

    if success:
        return {
            "status": "success",
            "message": f"Acesso do dispositivo '{device_identifier}' foi revogado com sucesso. O token de sessão foi invalidado.",
        }
    return {
        "status": "error",
        "message": f"Dispositivo '{device_identifier}' não foi encontrado entre os dispositivos autorizados ativos.",
    }


def scan_network_devices(subnet_range: Optional[str] = None) -> Dict[str, Any]:
    """Descobrir instâncias e serviços ATON compatíveis na rede local usando mDNS ou sonda de sub-rede.

    Args:
        subnet_range: Opcional. Sub-rede em notação CIDR para sonda controlada (ex: '192.168.0.0/24').

    Returns:
        Dispositivos ATON encontrados na rede local.
    """
    nd = get_network_discovery()
    found = []

    if subnet_range:
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            found = loop.run_until_complete(nd.probe_subnet_range(subnet_range))
        finally:
            loop.close()
    else:
        found = nd.discover_mdns_services(timeout_seconds=2.0)

    if found:
        dev_list = "\n".join(
            f"- {d.get('service_name', 'ATON')} no IP {d.get('primary_ip', '')}:{d.get('port', 8443)} "
            f"via {d.get('discovery_method', 'mDNS')}"
            for d in found
        )
        msg = f"Foram encontrados {len(found)} serviço(s) ATON na rede local:\n{dev_list}"
    else:
        msg = "Nenhum outro serviço ATON compatível foi detectado na rede local no momento."

    return {
        "status": "success",
        "found_count": len(found),
        "devices": found,
        "message": msg,
    }


# Tool declarations for Gemini Tool Calling
NETWORK_TOOLS_DEFINITIONS = [
    {
        "name": "get_network_info",
        "description": "Obter os endereços IP locais, interfaces ativas e informações de rede do computador anfitrião do ATON.",
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        },
    },
    {
        "name": "list_network_devices",
        "description": "Listar todos os dispositivos (celulares, TVs, computadores) pareados e autorizados no ATON com seus IPs e permissões.",
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        },
    },
    {
        "name": "revoke_network_device",
        "description": "Revogar a autorização de um dispositivo conectado (celular, TV ou PC) para cortar seu acesso ao ATON.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "device_identifier": {
                    "type": "STRING",
                    "description": "Nome do dispositivo (ex: 'Galaxy S24') ou seu ID UUID.",
                },
            },
            "required": ["device_identifier"],
        },
    },
    {
        "name": "scan_network_devices",
        "description": "Procurar instâncias compatíveis do ATON na rede local utilizando mDNS/DNS-SD ou sonda de sub-rede controlada.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "subnet_range": {
                    "type": "STRING",
                    "description": "Opcional. Sub-rede no formato CIDR (ex: '192.168.0.0/24'). Se omitido, usa mDNS.",
                },
            },
        },
    },
]
