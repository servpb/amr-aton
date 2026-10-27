"""Network discovery, IP address reading, and mDNS/DNS-SD service for ATON (Phase 11)."""

import asyncio
import ipaddress
import json
import logging
import socket
from typing import Any, Dict, List, Optional
import urllib.request

import psutil

try:
    from zeroconf import IPVersion, ServiceInfo, ServiceListener, Zeroconf
    from zeroconf.asyncio import AsyncZeroconf
except ImportError:
    Zeroconf = None  # type: ignore
    AsyncZeroconf = None  # type: ignore
    ServiceInfo = None  # type: ignore
    ServiceListener = None  # type: ignore

from src.config import settings

logger = logging.getLogger(__name__)

MDNS_SERVICE_TYPE = "_aton._tcp.local."


class AtonServiceListener:
    """Listener callback for mDNS service discovery events."""

    def __init__(self):
        self.found_services: List[Dict[str, Any]] = []

    def add_service(self, zc: Any, type_: str, name: str) -> None:
        """Handle newly discovered mDNS service."""
        info = zc.get_service_info(type_, name)
        if info:
            addresses = [socket.inet_ntoa(addr) for addr in info.addresses if len(addr) == 4]
            properties = {
                k.decode("utf-8", errors="ignore"): v.decode("utf-8", errors="ignore")
                for k, v in info.properties.items()
            }
            entry = {
                "service_name": name,
                "host": info.server,
                "ip_addresses": addresses,
                "primary_ip": addresses[0] if addresses else "unknown",
                "port": info.port,
                "device_type": properties.get("device_type", "unknown"),
                "version": properties.get("version", "1.0"),
                "discovery_method": "mDNS/DNS-SD",
                "is_aton": True,
            }
            if not any(s["primary_ip"] == entry["primary_ip"] and s["port"] == entry["port"] for s in self.found_services):
                self.found_services.append(entry)

    def update_service(self, zc: Any, type_: str, name: str) -> None:
        pass

    def remove_service(self, zc: Any, type_: str, name: str) -> None:
        pass


class NetworkDiscovery:
    """Manages local network interface discovery, mDNS broadcasting, and controlled subnet probing."""

    def __init__(self):
        self._aiozc: Optional[Any] = None
        self._service_info: Optional[Any] = None
        self._is_broadcasting = False

    @staticmethod
    def get_local_interfaces() -> List[Dict[str, Any]]:
        """Inspect and return all local network interfaces and their IP addresses."""
        interfaces_list = []
        try:
            stats = psutil.net_if_stats()
            addrs = psutil.net_if_addrs()

            for name, addr_list in addrs.items():
                is_up = stats[name].isup if name in stats else False
                speed = stats[name].speed if name in stats else 0

                for addr in addr_list:
                    if addr.family == socket.AF_INET:
                        ip = addr.address
                        is_loopback = ip.startswith("127.")

                        name_lower = name.lower()
                        if "tailscale" in name_lower or ip.startswith("100."):
                            if_type = "tailscale"
                        elif "wi-fi" in name_lower or "wireless" in name_lower or "wlan" in name_lower:
                            if_type = "wifi"
                        elif "ethernet" in name_lower or "eth" in name_lower:
                            if_type = "ethernet"
                        elif is_loopback:
                            if_type = "loopback"
                        else:
                            if_type = "other"

                        interfaces_list.append({
                            "interface_name": name,
                            "ip_address": ip,
                            "netmask": addr.netmask or "255.255.255.0",
                            "broadcast": addr.broadcast or "",
                            "is_up": is_up,
                            "is_loopback": is_loopback,
                            "type": if_type,
                            "speed_mbps": speed,
                        })
        except Exception as e:
            logger.error(f"Erro ao enumerar interfaces de rede: {e}")

        return interfaces_list

    @staticmethod
    def get_primary_ip() -> str:
        """Return the preferred non-loopback local IPv4 address."""
        interfaces = NetworkDiscovery.get_local_interfaces()
        for iface in interfaces:
            if iface["is_up"] and not iface["is_loopback"] and iface["type"] in ("wifi", "ethernet"):
                return iface["ip_address"]
        for iface in interfaces:
            if iface["is_up"] and iface["type"] == "tailscale":
                return iface["ip_address"]
        for iface in interfaces:
            if iface["is_up"] and not iface["is_loopback"]:
                return iface["ip_address"]
        return "127.0.0.1"

    async def async_start_broadcasting(
        self,
        port: int = 8443,
        service_name: str = "ATON-Host",
        device_type: str = "desktop",
    ) -> bool:
        """Broadcast ATON availability on local network using AsyncZeroconf mDNS/DNS-SD."""
        if AsyncZeroconf is None or ServiceInfo is None:
            return False

        if self._is_broadcasting:
            return True

        try:
            primary_ip = self.get_primary_ip()
            if primary_ip == "127.0.0.1":
                return False

            self._aiozc = AsyncZeroconf()
            hostname = socket.gethostname()
            full_service_name = f"{service_name}-{hostname}.{MDNS_SERVICE_TYPE}"

            properties = {
                "version": "1.0",
                "device_type": device_type,
                "server_name": "Aton Host",
                "name": "ATON Assistente",
            }

            self._service_info = ServiceInfo(
                type_=MDNS_SERVICE_TYPE,
                name=full_service_name,
                addresses=[socket.inet_aton(primary_ip)],
                port=port,
                properties=properties,
                server=f"{hostname}.local.",
            )

            await self._aiozc.async_register_service(self._service_info)
            self._is_broadcasting = True
            logger.info(f"📡 mDNS anunciado: {full_service_name} em {primary_ip}:{port}")
            return True
        except Exception as e:
            logger.debug(f"Não foi possível registrar serviço mDNS: {e}")
            self._is_broadcasting = False
            return False

    def start_broadcasting(self, port: int = 8443, service_name: str = "ATON-Host", device_type: str = "desktop") -> bool:
        """Sync wrapper for async_start_broadcasting."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.async_start_broadcasting(port, service_name, device_type))
            return True
        except RuntimeError:
            return False

    async def async_stop_broadcasting(self) -> None:
        """Unregister and close mDNS broadcast cleanly."""
        if self._aiozc and self._service_info:
            try:
                await self._aiozc.async_unregister_service(self._service_info)
                await self._aiozc.async_close()
            except Exception as e:
                logger.debug(f"Erro ao fechar mDNS: {e}")
            finally:
                self._aiozc = None
                self._service_info = None
                self._is_broadcasting = False
                logger.info("Anúncio mDNS do ATON encerrado.")

    def stop_broadcasting(self) -> None:
        """Sync wrapper for async_stop_broadcasting."""
        if self._aiozc:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.async_stop_broadcasting())
            except RuntimeError:
                pass
                self._zeroconf.unregister_service(self._service_info)
                self._zeroconf.close()
            except Exception as e:
                logger.debug(f"Erro ao fechar zeroconf: {e}")
            finally:
                self._zeroconf = None
                self._service_info = None
                self._is_broadcasting = False
                logger.info("Anúncio mDNS do ATON encerrado.")

    def discover_mdns_services(self, timeout_seconds: float = 3.0) -> List[Dict[str, Any]]:
        """Browse the local network for other active ATON instances via mDNS."""
        if Zeroconf is None:
            return []

        listener = AtonServiceListener()
        zc = Zeroconf()
        try:
            browser = ServiceBrowser(zc, MDNS_SERVICE_TYPE, listener)
            import time
            time.sleep(timeout_seconds)
            browser.cancel()
        except Exception as e:
            logger.debug(f"Erro ao buscar serviços mDNS: {e}")
        finally:
            zc.close()

        return listener.found_services

    async def probe_subnet_range(
        self,
        subnet_cidr: str,
        port: int = 8443,
        timeout: float = 0.6,
        max_hosts: int = 254,
    ) -> List[Dict[str, Any]]:
        """Perform a controlled probe strictly for ATON services on a given subnet.

        Does not perform generic port scans. It only checks the specific HTTP status route
        ('/api/status') on the ATON port to confirm compatibility.
        """
        results = []
        try:
            network = ipaddress.ip_network(subnet_cidr, strict=False)
            hosts = list(network.hosts())[:max_hosts]
        except ValueError as e:
            logger.warning(f"Intervalo de sub-rede inválido '{subnet_cidr}': {e}")
            return []

        async def _check_ip(ip_str: str) -> Optional[Dict[str, Any]]:
            url = f"http://{ip_str}:{port}/api/status"
            try:
                loop = asyncio.get_running_loop()
                def _fetch():
                    req = urllib.request.Request(url, headers={"User-Agent": "ATON-Probe/1.0"})
                    with urllib.request.urlopen(req, timeout=timeout) as resp:
                        if resp.status == 200:
                            data = json.loads(resp.read().decode("utf-8"))
                            if data.get("assistant_name") == "Aton":
                                return {
                                    "service_name": f"ATON @ {ip_str}",
                                    "primary_ip": ip_str,
                                    "port": port,
                                    "device_type": data.get("device_type", "desktop"),
                                    "version": data.get("version", "unknown"),
                                    "state": data.get("state", "unknown"),
                                    "discovery_method": "Subnet Probe (/api/status)",
                                    "is_aton": True,
                                }
                    return None

                return await loop.run_in_executor(None, _fetch)
            except Exception:
                return None

        tasks = [_check_ip(str(ip)) for ip in hosts]
        done = await asyncio.gather(*tasks, return_exceptions=True)
        for res in done:
            if isinstance(res, dict) and res.get("is_aton"):
                results.append(res)

        return results
