"""Fire TV discovery, identity verification, and dynamic DHCP IP recovery for Aton."""

import concurrent.futures
import ipaddress
import json
import logging
import os
from pathlib import Path
import re
import socket
import subprocess
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import psutil

from src.config import settings

logger = logging.getLogger(__name__)

# State file storing last confirmed IP across restarts without altering .env
STATE_FILE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "fire_tv_state.json"

# Suffix for atomic file replacements
STATE_TMP_SUFFIX = ".tmp"


def normalize_mac(mac: Optional[str]) -> str:
    """Normalize MAC address string to uppercase XX:XX:XX:XX:XX:XX format.

    Handles colons, hyphens, uppercase/lowercase, and plain 12-char hex strings.
    """
    if not mac:
        return ""
    cleaned = re.sub(r"[^a-fA-F0-9]", "", str(mac).strip().upper())
    if len(cleaned) == 12:
        return ":".join(cleaned[i : i + 2] for i in range(0, 12, 2))
    return ""




def mask_serial(serial: Optional[str]) -> str:
    """Mask serial number for logging, reporting, and model tool returns.

    Format:
        'G071...1DJK' for strings with > 8 characters.
        '***' for strings with <= 8 characters or empty/None.
    """
    if not serial:
        return "***"
    s = str(serial).strip()
    if len(s) > 8:
        return f"{s[:4]}...{s[-4:]}"
    return "***"


def sanitize_fire_tv_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """Return a safe, sanitized copy of the Fire TV state dictionary for display.

    Does not modify the original dictionary or the on-disk state.
    """
    sanitized = dict(state)
    if "serial" in sanitized:
        sanitized["serial"] = mask_serial(sanitized["serial"])
    return sanitized


def get_windows_arp_table() -> Dict[str, str]:
    """Parse local ARP table / Neighbor cache on Windows to map IPv4 -> normalized MAC."""
    mapping: Dict[str, str] = {}
    try:
        res = subprocess.run(
            ["arp", "-a"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
            shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                line = line.strip()
                match = re.search(
                    r"(\d{1,3}(?:\.\d{1,3}){3})\s+([0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}[-:][0-9a-fA-F]{2})",
                    line,
                )
                if match:
                    ip = match.group(1).strip()
                    raw_mac = match.group(2).strip()
                    norm = normalize_mac(raw_mac)
                    if norm and not norm.startswith("FF:FF:FF") and not norm.startswith("01:00:5E"):
                        mapping[ip] = norm
    except Exception as exc:
        logger.debug(f"Could not read Windows ARP table: {exc}")
    return mapping


def get_active_local_subnets() -> List[ipaddress.IPv4Network]:
    """Identify active local IPv4 subnets, excluding loopback, VPN/Tailscale, and overly large networks."""
    # 1. If explicit subnet configured, honor it immediately
    if settings.fire_tv_discovery_subnet.strip():
        try:
            return [ipaddress.IPv4Network(settings.fire_tv_discovery_subnet.strip(), strict=False)]
        except Exception as exc:
            logger.warning(f"Configured FIRE_TV_DISCOVERY_SUBNET invalid ({exc}); falling back to auto-detection.")

    subnets: List[ipaddress.IPv4Network] = []
    stats = psutil.net_if_stats()
    addrs = psutil.net_if_addrs()

    for iface_name, iface_addrs in addrs.items():
        iface_stat = stats.get(iface_name)
        if not iface_stat or not iface_stat.isup:
            continue

        for addr_info in iface_addrs:
            if addr_info.family != socket.AF_INET:
                continue

            ip = addr_info.address
            netmask = addr_info.netmask

            if not ip or not netmask:
                continue

            try:
                ip_obj = ipaddress.IPv4Address(ip)
                if ip_obj.is_loopback or ip_obj.is_link_local:
                    continue

                # Exclude Tailscale CGNAT subnet (100.64.0.0/10)
                tailscale_net = ipaddress.IPv4Network("100.64.0.0/10")
                if ip_obj in tailscale_net:
                    continue

                network = ipaddress.IPv4Network(f"{ip}/{netmask}", strict=False)

                # Reject broad subnets (/0 to /21) to prevent long sweeping scans
                if network.prefixlen < 22:
                    logger.debug(f"Skipping broad interface subnet {network} (< /22).")
                    continue

                if network not in subnets:
                    subnets.append(network)

            except Exception as exc:
                logger.debug(f"Error parsing interface {iface_name} network {ip}/{netmask}: {exc}")

    return subnets


def probe_tcp_port(ip: str, port: int = 5555, timeout: float = 0.35) -> bool:
    """Fast TCP socket probe to verify if ADB port 5555 is open on a host."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((ip, port))
        sock.close()
        return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False
    finally:
        try:
            sock.close()
        except Exception:
            pass


def scan_subnet_for_adb_hosts(
    subnet: ipaddress.IPv4Network,
    port: int = 5555,
    timeout: float = 0.35,
    concurrency: int = 24,
) -> List[str]:
    """Scan an IPv4 subnet for open ADB port 5555 using a bounded thread pool."""
    hosts = [str(h) for h in subnet.hosts()]
    open_hosts: List[str] = []

    if len(hosts) > 1024:
        logger.warning(f"Subnet {subnet} contains {len(hosts)} hosts; scanning first 256 only.")
        hosts = hosts[:256]

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        future_to_ip = {
            executor.submit(probe_tcp_port, host, port, timeout): host for host in hosts
        }
        for future in concurrent.futures.as_completed(future_to_ip):
            host = future_to_ip[future]
            try:
                if future.result():
                    open_hosts.append(host)
            except Exception:
                pass

    return open_hosts


def load_confirmed_fire_tv_state(state_file_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load previously confirmed Fire TV state from data/fire_tv_state.json if available."""
    target_path = state_file_path or STATE_FILE_PATH
    if not target_path.is_file():
        return {}
    try:
        with open(target_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception as exc:
        logger.debug(f"Could not read Fire TV state file: {exc}")
    return {}


def save_confirmed_fire_tv_state(
    ip: str,
    serial: str,
    model: str,
    mac: str,
    state_file_path: Optional[Path] = None,
) -> bool:
    """Atomically persist confirmed Fire TV IP and identity to data/fire_tv_state.json."""
    target_path = state_file_path or STATE_FILE_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "confirmed_ip": ip,
        "confirmed_at": time.time(),
        "serial": serial,
        "model": model,
        "mac": normalize_mac(mac),
    }
    tmp_path = target_path.with_suffix(STATE_TMP_SUFFIX)
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, target_path)
        logger.info(f"Confirmed Fire TV state atomically saved for IP {ip} ({mask_serial(serial)}).")
        return True
    except Exception as exc:
        logger.warning(f"Error persisting Fire TV state: {exc}")
        if tmp_path.is_file():
            try:
                tmp_path.unlink()
            except Exception:
                pass
        return False


def verify_adb_identity(
    ip: str,
    adb_path: Optional[str] = None,
    expected_serial: Optional[str] = None,
    expected_model: Optional[str] = None,
    expected_mac: Optional[str] = None,
    run_cmd_fn: Optional[Callable[[List[str], int], Any]] = None,
    runner_fn: Optional[Callable[[List[str], int], Any]] = None,
) -> Tuple[bool, str, Dict[str, Any]]:
    """Strictly verify Fire TV identity on an ADB session.

    Checks:
    1. ADB connection and state (device vs unauthorized vs offline).
    2. Stable hardware serial number (`ro.serialno` or `ro.boot.serialno`).
    3. Hardware model (`ro.product.model`).
    4. Active ARP link layer address correlation.

    Returns:
        Tuple of (is_verified, reason_code, details_dict).
    """
    effective_adb = adb_path or settings.fire_tv_adb_path
    effective_serial = expected_serial if expected_serial is not None else settings.fire_tv_expected_serial
    effective_model = expected_model if expected_model is not None else settings.fire_tv_expected_model
    effective_mac = expected_mac if expected_mac is not None else settings.fire_tv_expected_mac

    runner = runner_fn or run_cmd_fn or _default_adb_runner
    serial_endpoint = f"{ip}:5555"

    # Fast TCP port pre-check on live network if no mock runner is injected
    if runner_fn is None and run_cmd_fn is None:
        if not probe_tcp_port(ip, 5555, timeout=0.5):
            return False, "offline", {
                "ip": ip,
                "message": f"O Fire Stick em {ip} está offline ou inacessível via ADB.",
            }

    try:
        # Step 1: Connect
        conn_res = runner([effective_adb, "connect", serial_endpoint], 3)
        # Step 2: Check state
        state_res = runner([effective_adb, "-s", serial_endpoint, "get-state"], 3)
        state_out = (state_res.stdout or state_res.stderr or "").strip()
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError) as exc:
        return False, "offline", {
            "ip": ip,
            "message": f"O Fire Stick em {ip} está offline ou inacessível via ADB: {exc}",
        }

    # Check devices output if state returned empty/unknown
    if "unauthorized" in state_out:
        return False, "unauthorized", {
            "ip": ip,
            "message": "O Fire Stick está aguardando autorização na televisão. Aceite a mensagem de autorização na tela da TV.",
        }

    dev_res = runner([effective_adb, "devices"], 4)
    dev_out = (dev_res.stdout or "").strip()
    for line in dev_out.splitlines():
        if serial_endpoint in line and "unauthorized" in line:
            return False, "unauthorized", {
                "ip": ip,
                "message": "O Fire Stick está aguardando autorização na televisão. Aceite a mensagem de autorização na tela da TV.",
            }

    if state_res.returncode != 0 or state_out != "device":
        return False, "offline", {
            "ip": ip,
            "message": f"O Fire Stick em {ip} está offline ou inacessível via ADB.",
        }

    # Step 3: Query stable serial and model
    serial_res = runner([effective_adb, "-s", serial_endpoint, "shell", "getprop", "ro.serialno"], 4)
    dev_serial = (serial_res.stdout or "").strip()
    if not dev_serial:
        boot_res = runner([effective_adb, "-s", serial_endpoint, "shell", "getprop", "ro.boot.serialno"], 4)
        dev_serial = (boot_res.stdout or "").strip()

    model_res = runner([effective_adb, "-s", serial_endpoint, "shell", "getprop", "ro.product.model"], 4)
    dev_model = (model_res.stdout or "").strip()

    # Step 4: Validate model
    if effective_model and dev_model.lower() != effective_model.strip().lower():
        logger.warning(f"Device at {ip} model mismatch: expected '{effective_model}', got '{dev_model}'.")
        return False, "divergent_model", {
            "ip": ip,
            "expected_model": effective_model,
            "actual_model": dev_model,
            "message": "Encontrei um aparelho, mas o modelo não corresponde ao seu Fire Stick.",
        }

    # Step 5: Validate stable serial
    if effective_serial and dev_serial.lower() != effective_serial.strip().lower():
        logger.warning(
            f"Device at {ip} serial mismatch: expected '{mask_serial(effective_serial)}', got '{mask_serial(dev_serial)}'."
        )
        return False, "divergent_serial", {
            "ip": ip,
            "expected_serial": mask_serial(effective_serial),
            "actual_serial": mask_serial(dev_serial),
            "message": "Encontrei um aparelho, mas não consegui confirmar que é o seu Fire Stick (número de série não confere).",
        }

    # Step 6: Correlate ARP MAC if present
    arp_table = get_windows_arp_table()
    actual_mac = arp_table.get(ip, "")
    norm_expected_mac = normalize_mac(effective_mac)

    if actual_mac and norm_expected_mac:
        if actual_mac != norm_expected_mac:
            logger.warning(f"Device at {ip} MAC mismatch: expected '{norm_expected_mac}', found in ARP '{actual_mac}'.")
            return False, "divergent_mac", {
                "ip": ip,
                "expected_mac": norm_expected_mac,
                "actual_mac": actual_mac,
                "message": "Encontrei um aparelho, mas o endereço físico diverge do esperado.",
            }

    return True, "confirmed", {
        "ip": ip,
        "serial": dev_serial,
        "masked_serial": mask_serial(dev_serial),
        "model": dev_model,
        "mac": actual_mac or norm_expected_mac,
        "message": f"Fire Stick conectado e verificado ({dev_model}).",
    }


def _default_adb_runner(arguments: List[str], timeout: int = 5):
    """Default bounded runner for ADB child processes."""
    return subprocess.run(
        arguments,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        shell=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


class FireTVConnectionManager:
    """Manages active connection, identity caching, concurrency locks, and DHCP discovery for Fire TV."""

    def __init__(
        self,
        state_file_path: Optional[Path] = None,
        expected_mac: Optional[str] = None,
        expected_serial: Optional[str] = None,
        expected_model: Optional[str] = None,
        cache_ttl_seconds: float = 60.0,
        min_interval_seconds: float = 30.0,
    ):
        self._lock = threading.Lock()
        self._discovery_lock = threading.Lock()
        self._cached_ip: Optional[str] = None
        self._cached_verified_at: float = 0.0
        self._cache_ttl_seconds: float = cache_ttl_seconds
        self._last_discovery_attempt_at: float = 0.0
        self._discovery_in_progress: bool = False
        self._last_discovery_result: Optional[Tuple[Optional[str], str]] = None
        self._state_file_path: Path = state_file_path or STATE_FILE_PATH
        self._expected_mac: str = expected_mac if expected_mac is not None else settings.fire_tv_expected_mac
        self._expected_serial: str = expected_serial if expected_serial is not None else settings.fire_tv_expected_serial
        self._expected_model: str = expected_model if expected_model is not None else settings.fire_tv_expected_model
        self._min_interval_seconds: float = min_interval_seconds
        self._device_info: Dict[str, Any] = {}

    def get_device_info(self) -> Dict[str, Any]:
        """Return details of verified device."""
        with self._lock:
            return dict(self._device_info)

    def invalidate_cache(self) -> None:
        """Invalidate connection cache upon network failure, disconnect, or IP change."""
        with self._lock:
            self._cached_ip = None
            self._cached_verified_at = 0.0

    def get_candidate_priority_ip(self) -> str:
        """Determine priority IP: 1. State file; 2. .env configured IP."""
        state = load_confirmed_fire_tv_state(self._state_file_path)
        state_ip = state.get("confirmed_ip", "").strip()
        if state_ip:
            return state_ip
        return settings.fire_tv_ip.strip()

    def get_verified_device_ip(
        self,
        force_refresh: bool = False,
        runner_fn: Optional[Callable] = None,
        candidate_ips: Optional[List[str]] = None,
    ) -> Tuple[Optional[str], str]:
        """Ensure and return a strictly verified Fire TV IP address before allowing control commands.

        Returns:
            Tuple of (ip_address_or_none, status_message_pt_br).
        """
        now = time.time()

        # 1. Check in-memory verified cache
        with self._lock:
            if (
                not force_refresh
                and self._cached_ip
                and (now - self._cached_verified_at <= self._cache_ttl_seconds)
            ):
                return self._cached_ip, "Fire Stick conectado e verificado."

        priority_candidates = []
        if candidate_ips is not None:
            priority_candidates.extend(candidate_ips)
        else:
            p_ip = self.get_candidate_priority_ip()
            if p_ip:
                priority_candidates.append(p_ip)

        adb_path = settings.fire_tv_adb_path.strip()

        # 2. Try priority IPs first
        for candidate in priority_candidates:
            is_ok, reason, details = verify_adb_identity(
                ip=candidate,
                adb_path=adb_path,
                expected_serial=self._expected_serial,
                expected_model=self._expected_model,
                expected_mac=self._expected_mac,
                runner_fn=runner_fn,
            )
            if is_ok:
                with self._lock:
                    self._cached_ip = candidate
                    self._cached_verified_at = time.time()
                    self._device_info = details
                save_confirmed_fire_tv_state(
                    ip=candidate,
                    serial=details.get("serial", ""),
                    model=details.get("model", ""),
                    mac=details.get("mac", ""),
                    state_file_path=self._state_file_path,
                )
                return candidate, "Fire Stick conectado e verificado."
            elif reason == "unauthorized":
                self.invalidate_cache()
                return None, "O Fire Stick está aguardando autorização na televisão. Aceite a mensagem de autorização na tela da TV."

        # 3. Priority candidate failed or points to another device -> Trigger limited discovery
        if not settings.fire_tv_discovery_enabled:
            self.invalidate_cache()
            return None, "O endereço anterior não respondeu e a descoberta automática está desativada."

        logger.info(f"Priority Fire TV candidates unreachable or unverified. Initiating network discovery...")
        return self.discover_and_reconnect(runner_fn=runner_fn)

    def discover_and_reconnect(
        self,
        runner_fn: Optional[Callable] = None,
    ) -> Tuple[Optional[str], str]:
        """Run single concurrent network discovery across local subnets to find and confirm Fire TV.

        Follows priority:
        1. Query Windows ARP cache for expected MAC.
        2. Bounded TCP port 5555 probe on directly connected subnet.
        3. Strict identity verification on all responding candidates.
        """
        now = time.time()

        # Rate-limiting: minimum interval between full discovery attempts
        with self._lock:
            if (
                self._last_discovery_result
                and (now - self._last_discovery_attempt_at < self._min_interval_seconds)
            ):
                logger.debug("Discovery rate-limited. Returning previous discovery outcome.")
                return self._last_discovery_result

        # Ensure only one discovery runs at a time
        with self._discovery_lock:
            # Check again after acquiring lock
            if (
                self._cached_ip
                and (time.time() - self._cached_verified_at <= self._cache_ttl_seconds)
            ):
                return self._cached_ip, "Fire Stick conectado e verificado."

            self._last_discovery_attempt_at = time.time()
            adb_path = settings.fire_tv_adb_path.strip()

            # --- Step A: Fast ARP correlation for expected MAC ---
            arp_table = get_windows_arp_table()
            expected_mac_norm = normalize_mac(self._expected_mac)
            candidates_from_arp: List[str] = []

            if expected_mac_norm:
                for ip, mac in arp_table.items():
                    if mac == expected_mac_norm:
                        candidates_from_arp.append(ip)

            # Test ARP candidates first
            for candidate_ip in candidates_from_arp:
                is_ok, reason, details = verify_adb_identity(
                    ip=candidate_ip,
                    adb_path=adb_path,
                    expected_serial=self._expected_serial,
                    expected_model=self._expected_model,
                    expected_mac=self._expected_mac,
                    runner_fn=runner_fn,
                )
                if is_ok:
                    with self._lock:
                        self._cached_ip = candidate_ip
                        self._cached_verified_at = time.time()
                        self._device_info = details
                    save_confirmed_fire_tv_state(
                        ip=candidate_ip,
                        serial=details.get("serial", ""),
                        model=details.get("model", ""),
                        mac=details.get("mac", ""),
                        state_file_path=self._state_file_path,
                    )
                    res = (candidate_ip, "Encontrei e confirmei o Fire Stick no novo endereço.")
                    self._last_discovery_result = res
                    return res

            # --- Step B: Subnet TCP Scan on Port 5555 ---
            subnets = get_active_local_subnets()
            if not subnets:
                res = (None, "Não foi possível localizar o Fire Stick nesta rede.")
                self._last_discovery_result = res
                return res

            open_adb_ips: List[str] = []
            for subnet in subnets:
                found_ips = scan_subnet_for_adb_hosts(
                    subnet=subnet,
                    timeout=settings.fire_tv_discovery_timeout_seconds,
                    concurrency=settings.fire_tv_discovery_concurrency,
                )
                open_adb_ips.extend(found_ips)

            # Prioritize IPs that were not already tested
            untested_ips = [ip for ip in open_adb_ips if ip not in candidates_from_arp]
            confirmed_candidates: List[Tuple[str, Dict[str, Any]]] = []
            unauthorized_found = False

            for candidate_ip in untested_ips:
                is_ok, reason, details = verify_adb_identity(
                    ip=candidate_ip,
                    adb_path=adb_path,
                    expected_serial=self._expected_serial,
                    expected_model=self._expected_model,
                    expected_mac=self._expected_mac,
                    runner_fn=runner_fn,
                )
                if is_ok:
                    confirmed_candidates.append((candidate_ip, details))
                elif reason == "unauthorized":
                    unauthorized_found = True

            # Evaluate outcomes
            if len(confirmed_candidates) == 1:
                confirmed_ip, details = confirmed_candidates[0]
                with self._lock:
                    self._cached_ip = confirmed_ip
                    self._cached_verified_at = time.time()
                    self._device_info = details
                save_confirmed_fire_tv_state(
                    ip=confirmed_ip,
                    serial=details.get("serial", ""),
                    model=details.get("model", ""),
                    mac=details.get("mac", ""),
                    state_file_path=self._state_file_path,
                )
                res = (confirmed_ip, "Encontrei e confirmei o Fire Stick no novo endereço.")
                self._last_discovery_result = res
                return res
            elif len(confirmed_candidates) > 1:
                res = (None, "Encontrei mais de um Fire Stick compatível na rede; por favor, confirme o endereço.")
                self._last_discovery_result = res
                return res
            elif unauthorized_found:
                res = (None, "O Fire Stick está aguardando autorização na televisão. Aceite a mensagem de autorização na tela da TV.")
                self._last_discovery_result = res
                return res

            res = (None, "Não foi possível localizar o Fire Stick na rede.")
            self._last_discovery_result = res
            return res


_global_connection_manager: Optional[FireTVConnectionManager] = None
_manager_lock = threading.Lock()


def get_fire_tv_connection_manager() -> FireTVConnectionManager:
    """Return thread-safe singleton connection manager for Fire TV."""
    global _global_connection_manager
    if _global_connection_manager is None:
        with _manager_lock:
            if _global_connection_manager is None:
                _global_connection_manager = FireTVConnectionManager()
    return _global_connection_manager
