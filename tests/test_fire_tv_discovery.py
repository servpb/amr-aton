"""Unit tests for Fire TV Stick DHCP discovery, identity verification, and reconnection."""

import json
from pathlib import Path
import subprocess
import time
from unittest.mock import MagicMock, patch

import pytest

from src.core.fire_tv_discovery import (
    FireTVConnectionManager,
    normalize_mac,
    get_windows_arp_table,
    get_active_local_subnets,
    probe_tcp_port,
    load_confirmed_fire_tv_state,
    save_confirmed_fire_tv_state,
    verify_adb_identity,
    mask_serial,
    sanitize_fire_tv_state,
)
from src.tools.fire_tv import _execute, control_fire_tv


class MockCompletedProcess:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


@pytest.fixture
def clean_manager(tmp_path):
    """Create an isolated FireTVConnectionManager instance using a temp state file."""
    state_file = tmp_path / "fire_tv_state.json"
    mgr = FireTVConnectionManager(
        state_file_path=state_file,
        expected_mac="24:CE:33:E2:0F:9E",
        expected_serial="G071CQ2042741DJK",
        expected_model="AFTSS",
    )
    return mgr


# 1. MAC normalization: handles colons, hyphens, and lowercase/uppercase
def test_mac_normalization():
    assert normalize_mac("24:ce:33:e2:0f:9e") == "24:CE:33:E2:0F:9E"
    assert normalize_mac("24-CE-33-E2-0F-9E") == "24:CE:33:E2:0F:9E"
    assert normalize_mac("24-ce-33-e2-0f-9e") == "24:CE:33:E2:0F:9E"
    assert normalize_mac("24ce33e20f9e") == "24:CE:33:E2:0F:9E"
    assert normalize_mac("invalid-mac") == ""
    assert normalize_mac("") == ""


# 2. Priority IP with valid serial, model, and ARP MAC connects directly and caches
def test_priority_ip_valid_connects_without_scan(clean_manager):
    runner = MagicMock()

    def mock_runner(args, timeout=8):
        cmd_str = " ".join(args)
        if "connect" in cmd_str:
            return MockCompletedProcess("connected to 192.168.0.13:5555")
        if "get-state" in cmd_str:
            return MockCompletedProcess("device\n")
        if "ro.serialno" in cmd_str:
            return MockCompletedProcess("G071CQ2042741DJK\n")
        if "ro.product.model" in cmd_str:
            return MockCompletedProcess("AFTSS\n")
        return MockCompletedProcess("")

    runner.side_effect = mock_runner

    with patch(
        "src.core.fire_tv_discovery.get_windows_arp_table",
        return_value={"192.168.0.13": "24:CE:33:E2:0F:9E"},
    ), patch(
        "src.core.fire_tv_discovery.scan_subnet_for_adb_hosts"
    ) as mock_scan:
        ip, msg = clean_manager.get_verified_device_ip(
            runner_fn=runner, candidate_ips=["192.168.0.13"]
        )

        assert ip == "192.168.0.13"
        assert "conectado e verificado" in msg
        mock_scan.assert_not_called()

        # Second call within TTL should return cached IP without calling runner again
        runner.reset_mock()
        cached_ip, cached_msg = clean_manager.get_verified_device_ip(runner_fn=runner)
        assert cached_ip == "192.168.0.13"
        runner.assert_not_called()


# 3. Priority IP occupied by another device triggers discovery and finds Fire Stick on another IP
def test_priority_ip_different_serial_triggers_discovery(clean_manager):
    runner = MagicMock()

    def mock_runner(args, timeout=8):
        cmd_str = " ".join(args)
        if "192.168.0.13:5555" in cmd_str:
            if "get-state" in cmd_str:
                return MockCompletedProcess("device\n")
            if "ro.serialno" in cmd_str:
                return MockCompletedProcess("WRONG_SERIAL_12345\n")
            if "ro.product.model" in cmd_str:
                return MockCompletedProcess("DifferentDevice\n")
            return MockCompletedProcess("connected to 192.168.0.13:5555")
        elif "192.168.0.45:5555" in cmd_str:
            if "get-state" in cmd_str:
                return MockCompletedProcess("device\n")
            if "ro.serialno" in cmd_str:
                return MockCompletedProcess("G071CQ2042741DJK\n")
            if "ro.product.model" in cmd_str:
                return MockCompletedProcess("AFTSS\n")
            return MockCompletedProcess("connected to 192.168.0.45:5555")
        return MockCompletedProcess("")

    runner.side_effect = mock_runner

    # ARP table has the real Fire TV on 192.168.0.45
    arp_data = {
        "192.168.0.13": "00:11:22:33:44:55",
        "192.168.0.45": "24:CE:33:E2:0F:9E",
    }

    with patch("src.core.fire_tv_discovery.get_windows_arp_table", return_value=arp_data):
        ip, msg = clean_manager.get_verified_device_ip(
            runner_fn=runner, candidate_ips=["192.168.0.13"]
        )

        assert ip == "192.168.0.45"
        assert "novo endereço" in msg or "conectado" in msg


# 4. Device with same model but different serial is rejected
def test_same_model_different_serial_rejected(clean_manager):
    runner = MagicMock()

    def mock_runner(args, timeout=8):
        cmd_str = " ".join(args)
        if "get-state" in cmd_str:
            return MockCompletedProcess("device\n")
        if "ro.serialno" in cmd_str:
            return MockCompletedProcess("IMPOSTOR_SERIAL\n")
        if "ro.product.model" in cmd_str:
            return MockCompletedProcess("AFTSS\n")
        return MockCompletedProcess("connected")

    runner.side_effect = mock_runner

    with patch("src.core.fire_tv_discovery.get_windows_arp_table", return_value={}):
        verified, reason, details = verify_adb_identity(
            "192.168.0.99",
            expected_serial="G071CQ2042741DJK",
            expected_model="AFTSS",
            runner_fn=runner,
        )
        assert verified is False
        assert reason == "divergent_serial"
        assert "não confere" in details.get("message", "")


# 5. IP change discovered via ARP table with matching MAC connects directly
def test_ip_change_discovered_via_arp(clean_manager):
    runner = MagicMock()

    def mock_runner(args, timeout=8):
        cmd_str = " ".join(args)
        if "192.168.0.13" in cmd_str:
            return MockCompletedProcess(stderr="failed to connect", returncode=1)
        if "192.168.0.88" in cmd_str:
            if "get-state" in cmd_str:
                return MockCompletedProcess("device\n")
            if "ro.serialno" in cmd_str:
                return MockCompletedProcess("G071CQ2042741DJK\n")
            if "ro.product.model" in cmd_str:
                return MockCompletedProcess("AFTSS\n")
            return MockCompletedProcess("connected")
        return MockCompletedProcess("")

    runner.side_effect = mock_runner

    arp_data = {"192.168.0.88": "24:CE:33:E2:0F:9E"}

    with patch("src.core.fire_tv_discovery.get_windows_arp_table", return_value=arp_data):
        ip, msg = clean_manager.get_verified_device_ip(
            runner_fn=runner, candidate_ips=["192.168.0.13"]
        )
        assert ip == "192.168.0.88"
        assert "G071CQ2042741DJK" in clean_manager.get_device_info().get("serial", "")


# 6. Outdated ARP table falls back to TCP 5555 subnet scan and confirms identity
def test_outdated_arp_falls_back_to_subnet_scan(clean_manager):
    runner = MagicMock()

    def mock_runner(args, timeout=8):
        cmd_str = " ".join(args)
        if "192.168.0.13" in cmd_str:
            return MockCompletedProcess(stderr="failed to connect", returncode=1)
        if "192.168.0.77" in cmd_str:
            if "get-state" in cmd_str:
                return MockCompletedProcess("device\n")
            if "ro.serialno" in cmd_str:
                return MockCompletedProcess("G071CQ2042741DJK\n")
            if "ro.product.model" in cmd_str:
                return MockCompletedProcess("AFTSS\n")
            return MockCompletedProcess("connected")
        return MockCompletedProcess("")

    runner.side_effect = mock_runner

    # ARP is empty or outdated
    arp_data = {}

    with patch("src.core.fire_tv_discovery.get_windows_arp_table", return_value=arp_data), \
         patch("src.core.fire_tv_discovery.get_active_local_subnets", return_value=["192.168.0.0/24"]), \
         patch("src.core.fire_tv_discovery.scan_subnet_for_adb_hosts", return_value=["192.168.0.77"]):

        ip, msg = clean_manager.get_verified_device_ip(
            runner_fn=runner, candidate_ips=["192.168.0.13"]
        )
        assert ip == "192.168.0.77"


# 7. Unauthorized device returns clear instruction to authorize on television
def test_unauthorized_device_instruction(clean_manager):
    runner = MagicMock()

    def mock_runner(args, timeout=8):
        cmd_str = " ".join(args)
        if "devices" in cmd_str:
            return MockCompletedProcess("List of devices attached\n192.168.0.13:5555\tunauthorized\n")
        return MockCompletedProcess("unauthorized\n")

    runner.side_effect = mock_runner

    with patch("src.core.fire_tv_discovery.get_windows_arp_table", return_value={}):
        verified, reason, details = verify_adb_identity(
            "192.168.0.13",
            expected_serial="G071CQ2042741DJK",
            expected_model="AFTSS",
            runner_fn=runner,
        )
        assert verified is False
        assert reason == "unauthorized"
        assert "autorização na televisão" in details.get("message", "")


# 8. No candidates found returns clear error message without hanging
def test_no_candidates_found_returns_error(clean_manager):
    runner = MagicMock()
    runner.return_value = MockCompletedProcess(stderr="failed to connect", returncode=1)

    with patch("src.core.fire_tv_discovery.get_windows_arp_table", return_value={}), \
         patch("src.core.fire_tv_discovery.get_active_local_subnets", return_value=["192.168.0.0/24"]), \
         patch("src.core.fire_tv_discovery.scan_subnet_for_adb_hosts", return_value=[]):

        ip, msg = clean_manager.get_verified_device_ip(
            runner_fn=runner, candidate_ips=["192.168.0.13"]
        )
        assert ip is None
        assert "não foi possível localizar" in msg.lower()


# 9. Multiple candidates with same serial / identity ambiguity
def test_multiple_verified_candidates_guarded(clean_manager):
    runner = MagicMock()

    def mock_runner(args, timeout=8):
        cmd_str = " ".join(args)
        if "get-state" in cmd_str:
            return MockCompletedProcess("device\n")
        if "ro.serialno" in cmd_str:
            return MockCompletedProcess("G071CQ2042741DJK\n")
        if "ro.product.model" in cmd_str:
            return MockCompletedProcess("AFTSS\n")
        return MockCompletedProcess("connected")

    runner.side_effect = mock_runner

    with patch("src.core.fire_tv_discovery.get_windows_arp_table", return_value={}), \
         patch("src.core.fire_tv_discovery.get_active_local_subnets", return_value=["192.168.0.0/24"]), \
         patch("src.core.fire_tv_discovery.scan_subnet_for_adb_hosts", return_value=["192.168.0.50", "192.168.0.60"]):

        ip, msg = clean_manager.get_verified_device_ip(runner_fn=runner, candidate_ips=[])
        # Should detect multiple candidates and request clarification without guessing
        assert ip is None
        assert "mais de um" in msg.lower()


# 10. Atomic persistence in state file and precedence over .env
def test_atomic_persistence_and_precedence(tmp_path):
    state_file = tmp_path / "fire_tv_state.json"

    # Save state
    save_confirmed_fire_tv_state(
        ip="192.168.0.99",
        serial="G071CQ2042741DJK",
        model="AFTSS",
        mac="24:CE:33:E2:0F:9E",
        state_file_path=state_file,
    )

    # State file must exist and contain the saved data
    assert state_file.is_file()
    loaded = load_confirmed_fire_tv_state(state_file)
    assert loaded["confirmed_ip"] == "192.168.0.99"
    assert loaded["serial"] == "G071CQ2042741DJK"
    assert loaded["mac"] == "24:CE:33:E2:0F:9E"

    # Confirmed IP takes precedence over .env default in candidate order
    mgr = FireTVConnectionManager(
        state_file_path=state_file,
        expected_mac="24:CE:33:E2:0F:9E",
        expected_serial="G071CQ2042741DJK",
        expected_model="AFTSS",
    )

    runner = MagicMock()
    runner.side_effect = lambda args, timeout=8: MockCompletedProcess(
        "G071CQ2042741DJK\n"
        if "ro.serialno" in " ".join(args)
        else ("AFTSS\n" if "ro.product.model" in " ".join(args) else "device\n")
    )

    with patch("src.core.fire_tv_discovery.get_windows_arp_table", return_value={}):
        ip, _ = mgr.get_verified_device_ip(runner_fn=runner)
        assert ip == "192.168.0.99"


# 11. Sensitive physical action failure returns status "uncertain" without duplicate execution
def test_sensitive_action_failure_returns_uncertain(tmp_path):
    dummy_adb = tmp_path / "adb.exe"
    dummy_adb.write_text("dummy")

    with patch("src.tools.fire_tv.get_fire_tv_connection_manager") as mock_get_mgr, \
         patch("src.tools.fire_tv.settings") as mock_settings, \
         patch("src.tools.fire_tv._run") as mock_run:

        mock_mgr = MagicMock()
        mock_mgr.get_candidate_priority_ip.return_value = "192.168.0.13"
        mock_mgr.get_verified_device_ip.return_value = ("192.168.0.13", "conectado")
        mock_get_mgr.return_value = mock_mgr

        mock_settings.fire_tv_adb_path = str(dummy_adb)

        # Simulating a physical action command (is_read_only=False) that raises or exits with error
        mock_run.return_value = MockCompletedProcess(stderr="device offline", returncode=1)

        result = control_fire_tv(action="select", count=1)

        # Must return "uncertain" and the exact mandated Portuguese warning
        assert result.get("status") == "uncertain"
        assert "não vou repeti-lo automaticamente" in result.get("message", "")
        mock_mgr.invalidate_cache.assert_called()


# 12. Concurrency lock ensures single discovery execution and respects rate limit
def test_concurrency_lock_and_rate_limit(clean_manager):
    runner = MagicMock()
    runner.return_value = MockCompletedProcess(stderr="failed to connect", returncode=1)

    with patch("src.core.fire_tv_discovery.get_windows_arp_table", return_value={}), \
         patch("src.core.fire_tv_discovery.get_active_local_subnets", return_value=["192.168.0.0/24"]), \
         patch("src.core.fire_tv_discovery.scan_subnet_for_adb_hosts", return_value=[]) as mock_scan:

        # First discovery attempt
        clean_manager.get_verified_device_ip(runner_fn=runner, candidate_ips=[])
        assert mock_scan.call_count == 1

        # Second attempt immediately after should be rate limited (within min_interval of 30s)
        clean_manager.get_verified_device_ip(runner_fn=runner, candidate_ips=[])
        # scan_subnet_for_adb_hosts should NOT have been called a second time
        assert mock_scan.call_count == 1


# 13. Serial masking rules: >8 chars masked, <=8 chars hidden, empty/None hidden
def test_mask_serial_formatting():
    # Long serial (> 8 characters)
    assert mask_serial("G071CQ2042741DJK") == "G071...1DJK"
    assert mask_serial("123456789") == "1234...6789"

    # Exactly 8 characters or shorter
    assert mask_serial("12345678") == "***"
    assert mask_serial("ABCD") == "***"
    assert mask_serial("") == "***"
    assert mask_serial(None) == "***"


# 14. Sanitized state copy generates safe representation without mutating original
def test_sanitize_fire_tv_state_presentation():
    raw_state = {
        "confirmed_ip": "192.168.0.13",
        "confirmed_at": 1793484084.0,
        "serial": "G071CQ2042741DJK",
        "model": "AFTSS",
        "mac": "24:CE:33:E2:0F:9E",
    }

    sanitized = sanitize_fire_tv_state(raw_state)

    # Sanitized state must have masked serial
    assert sanitized["serial"] == "G071...1DJK"
    assert "G071CQ2042741DJK" not in str(sanitized)

    # Original state MUST retain the full unmasked serial
    assert raw_state["serial"] == "G071CQ2042741DJK"


# 15. Internal identity comparison preserves and validates against the full unmasked serial
def test_internal_identity_comparison_preserves_full_serial(tmp_path):
    full_serial = "G071CQ2042741DJK"
    masked = mask_serial(full_serial)
    state_file = tmp_path / "fire_tv_state.json"

    # 1. State file on disk must persist the full unmasked serial
    save_confirmed_fire_tv_state(
        ip="192.168.0.13",
        serial=full_serial,
        model="AFTSS",
        mac="24:CE:33:E2:0F:9E",
        state_file_path=state_file,
    )

    loaded = load_confirmed_fire_tv_state(state_file)
    assert loaded["serial"] == full_serial

    # 2. Comparison must strictly reject when a device returns the masked string instead of the real serial
    runner = MagicMock()
    def mock_side_effect(args, timeout=8):
        cmd = " ".join(args)
        if "get-state" in cmd:
            return MockCompletedProcess("device")
        if "ro.serialno" in cmd:
            return MockCompletedProcess(f"{masked}")
        if "ro.product.model" in cmd:
            return MockCompletedProcess("AFTSS")
        return MockCompletedProcess("connected")
    runner.side_effect = mock_side_effect

    with patch("src.core.fire_tv_discovery.get_windows_arp_table", return_value={}):
        verified, reason, details = verify_adb_identity(
            "192.168.0.13",
            expected_serial=full_serial,
            expected_model="AFTSS",
            runner_fn=runner,
        )
        # Must be rejected because masked != full_serial
        assert verified is False
        assert reason == "divergent_serial"


# 16. verify_adb_identity return structures never leak full serial in model-facing messages or mismatch logs
def test_verify_adb_identity_output_never_leaks_full_serial():
    full_serial = "G071CQ2042741DJK"

    runner = MagicMock()
    def mock_side_effect_full(args, timeout=8):
        cmd = " ".join(args)
        if "get-state" in cmd:
            return MockCompletedProcess("device")
        if "ro.serialno" in cmd:
            return MockCompletedProcess(f"{full_serial}")
        if "ro.product.model" in cmd:
            return MockCompletedProcess("AFTSS")
        return MockCompletedProcess("connected")
    runner.side_effect = mock_side_effect_full

    with patch("src.core.fire_tv_discovery.get_windows_arp_table", return_value={}):
        verified, reason, details = verify_adb_identity(
            "192.168.0.13",
            expected_serial=full_serial,
            expected_model="AFTSS",
            runner_fn=runner,
        )
        assert verified is True
        # Model-facing message must not contain full serial
        assert full_serial not in details.get("message", "")
        # Masked serial must be present
        assert details.get("masked_serial") == "G071...1DJK"
