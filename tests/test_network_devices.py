"""Unit and integration tests for Network Discovery, Device Authorization, and Pairing (Phase 11)."""

import asyncio
import json
import os
import tempfile
import urllib.request
import pytest

from src.core.device_manager import DeviceManager, VALID_PERMISSIONS
from src.core.network_discovery import NetworkDiscovery
from src.integrations.mobile_gateway import MobileGatewayServer
from src.tools.network_tools import (
    get_network_info,
    list_network_devices,
    revoke_network_device,
    scan_network_devices,
)


@pytest.fixture
def temp_db(tmp_path):
    """Provide a temporary SQLite database path for isolated testing."""
    db_file = tmp_path / "test_devices.db"
    return str(db_file)


def test_device_manager_request_pairing_pin(temp_db):
    """Verify pairing request generates a 6-digit numeric PIN and sets expiration."""
    dm = DeviceManager(db_path=temp_db)
    req = dm.request_pairing(
        client_ip="192.168.0.50",
        device_name="Samsung Galaxy S24",
        device_type="mobile",
        requested_permissions=["commands", "audio"],
    )

    assert req["status"] == "pending"
    assert len(req["pin_code"]) == 6
    assert req["pin_code"].isdigit()
    assert req["client_ip"] == "192.168.0.50"
    assert req["device_name"] == "Samsung Galaxy S24"
    assert req["expires_in_seconds"] > 0


def test_device_manager_confirm_pairing_valid_pin(temp_db):
    """Verify pairing confirmation with correct PIN generates bearer token."""
    dm = DeviceManager(db_path=temp_db)
    req = dm.request_pairing(
        client_ip="192.168.0.51",
        device_name="LG WebOS TV",
        device_type="tv",
        requested_permissions=["commands"],
    )

    result = dm.confirm_pairing(request_id=req["request_id"], pin_code=req["pin_code"])
    assert result is not None
    assert "token" in result
    assert result["token"].startswith("aton_")
    assert result["device_name"] == "LG WebOS TV"
    assert result["permissions"] == ["commands"]

    # Verify device appears in paired list
    devices = dm.list_devices()
    assert len(devices) == 1
    assert devices[0]["device_name"] == "LG WebOS TV"
    assert devices[0]["status"] == "active"


def test_device_manager_confirm_pairing_invalid_pin(temp_db):
    """Verify pairing confirmation fails with incorrect PIN."""
    dm = DeviceManager(db_path=temp_db)
    req = dm.request_pairing(
        client_ip="192.168.0.52",
        device_name="Notebook Dell",
        device_type="desktop",
    )

    result = dm.confirm_pairing(request_id=req["request_id"], pin_code="000000")
    assert result is None


def test_device_manager_granular_permissions(temp_db):
    """Verify token validation correctly enforces granular permissions."""
    dm = DeviceManager(db_path=temp_db)
    req = dm.request_pairing(
        client_ip="192.168.0.53",
        device_name="Tablet iPad",
        device_type="mobile",
        requested_permissions=["commands", "audio"],
    )

    paired = dm.confirm_pairing(
        request_id=req["request_id"],
        pin_code=req["pin_code"],
        granted_permissions=["commands", "audio"],
    )
    token = paired["token"]

    # 1. Allowed permission 'commands' -> Should succeed
    valid, dev, msg = dm.validate_token(token, required_permission="commands")
    assert valid is True
    assert dev["device_name"] == "Tablet iPad"

    # 2. Allowed permission 'audio' -> Should succeed
    valid, dev, msg = dm.validate_token(token, required_permission="audio")
    assert valid is True

    # 3. Disallowed permission 'screen' -> Must be rejected!
    valid, dev, msg = dm.validate_token(token, required_permission="screen")
    assert valid is False
    assert "não possui a permissão 'screen'" in msg

    # 4. Disallowed permission 'control' -> Must be rejected!
    valid, dev, msg = dm.validate_token(token, required_permission="control")
    assert valid is False


def test_device_manager_revoke_device(temp_db):
    """Verify device revocation immediately invalidates bearer token."""
    dm = DeviceManager(db_path=temp_db)
    req = dm.request_pairing(
        client_ip="192.168.0.54",
        device_name="Celular Antigo",
        device_type="mobile",
    )
    paired = dm.confirm_pairing(request_id=req["request_id"], pin_code=req["pin_code"])
    token = paired["token"]

    # Token initially valid
    valid, _, _ = dm.validate_token(token)
    assert valid is True

    # Revoke access
    revoked = dm.revoke_device(paired["device_id"])
    assert revoked is True

    # Token is now rejected
    valid, _, msg = dm.validate_token(token)
    assert valid is False
    assert "revogado" in msg.lower()


def test_network_discovery_interfaces():
    """Verify NetworkDiscovery returns local interfaces with valid IP structures."""
    nd = NetworkDiscovery()
    interfaces = nd.get_local_interfaces()
    assert isinstance(interfaces, list)
    assert len(interfaces) > 0

    # Ensure at least loopback or local IP is present
    has_ip = any("." in iface.get("ip_address", "") for iface in interfaces)
    assert has_ip is True

    primary_ip = nd.get_primary_ip()
    assert isinstance(primary_ip, str)
    assert len(primary_ip) >= 7


def test_network_tools():
    """Verify network tools return expected dictionary structures."""
    info = get_network_info()
    assert info["status"] == "success"
    assert "primary_ip" in info

    devices = list_network_devices()
    assert devices["status"] == "success"
    assert "paired_devices" in devices

    revoke_res = revoke_network_device("non_existent_device_id_999")
    assert revoke_res["status"] == "error"

    scan_res = scan_network_devices()
    assert scan_res["status"] == "success"


async def _async_http_request(port: int, method: str, path: str, headers: dict = None, body: dict = None):
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    headers = headers or {}
    body_str = json.dumps(body) if body is not None else ""
    body_bytes = body_str.encode("utf-8")

    req_lines = [f"{method} {path} HTTP/1.1", f"Host: 127.0.0.1:{port}"]
    for k, v in headers.items():
        req_lines.append(f"{k}: {v}")
    if body_str:
        req_lines.append("Content-Type: application/json")
        req_lines.append(f"Content-Length: {len(body_bytes)}")
    req_lines.append("Connection: close")
    req_lines.append("")
    req_lines.append("")

    header_data = "\r\n".join(req_lines).encode("utf-8")
    writer.write(header_data + body_bytes)
    await writer.drain()

    raw_resp = await reader.read(8192)
    writer.close()
    await writer.wait_closed()

    text = raw_resp.decode("utf-8")
    status_line = text.split("\r\n")[0]
    status_code = int(status_line.split(" ")[1])
    body_part = text.split("\r\n\r\n")[1] if "\r\n\r\n" in text else ""
    try:
        json_data = json.loads(body_part) if body_part else {}
    except Exception:
        json_data = {}
    return status_code, json_data


@pytest.mark.asyncio
async def test_gateway_pairing_and_permission_enforcement(temp_db):
    """Integration test: pair a device over HTTP gateway and verify permission enforcement."""
    dm = DeviceManager(db_path=temp_db)
    server = MobileGatewayServer(
        assistant=None,
        host="127.0.0.1",
        port=18499,
        api_token="test_master_secret",
        device_manager=dm,
    )
    started = await server.start()
    assert started is True

    try:
        # 1. Request Pairing via POST /api/pair/request
        status, pair_data = await _async_http_request(
            port=18499,
            method="POST",
            path="/api/pair/request",
            body={
                "device_name": "Test iPhone 15",
                "device_type": "mobile",
                "requested_permissions": ["commands"],
            },
        )
        assert status == 200
        request_id = pair_data["request_id"]
        pin_code = pair_data["pin_code"]

        # 2. Confirm Pairing via POST /api/pair/confirm
        status, auth_data = await _async_http_request(
            port=18499,
            method="POST",
            path="/api/pair/confirm",
            body={
                "request_id": request_id,
                "pin_code": pin_code,
            },
        )
        assert status == 200
        device_token = auth_data["token"]
        assert device_token.startswith("aton_")

        # 3. Call allowed tool with granted 'commands' permission
        status, cmd_res = await _async_http_request(
            port=18499,
            method="POST",
            path="/api/command",
            headers={"Authorization": f"Bearer {device_token}"},
            body={
                "tool_name": "get_network_info",
                "tool_args": {},
            },
        )
        assert status == 200
        assert cmd_res["status"] == "success"

        # 4. Attempt to call a tool requiring 'control' permission (e.g. close_application)
        # The device only has 'commands' permission, so it MUST be rejected with 403 Forbidden!
        status, err_res = await _async_http_request(
            port=18499,
            method="POST",
            path="/api/command",
            headers={"Authorization": f"Bearer {device_token}"},
            body={
                "tool_name": "close_application",
                "tool_args": {"app_name": "notepad"},
            },
        )
        assert status == 403
        assert "Permissão negada" in err_res.get("message", "")

    finally:
        await server.stop()

