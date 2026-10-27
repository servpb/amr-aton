"""Unit tests for Mobile Gateway and Remote Access (Phase 3)."""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.integrations.mobile_gateway import MobileGatewayServer, start_gateway


@pytest.fixture
def mock_assistant():
    assistant = MagicMock()
    assistant.state = MagicMock()
    assistant.state.value = "conversing"
    return assistant


@pytest.mark.asyncio
async def test_gateway_server_lifecycle(mock_assistant):
    """Test starting and stopping the Mobile Gateway server."""
    # Use high port for testing to avoid conflicts
    server = MobileGatewayServer(assistant=mock_assistant, host="127.0.0.1", port=18443)
    assert not server.is_running

    started = await server.start()
    assert started is True
    assert server.is_running

    # Second start should be idempotent
    assert await server.start() is True

    await server.stop()
    assert not server.is_running


def test_gateway_authorization():
    """Test API token authorization logic."""
    # Open access when token is empty
    open_server = MobileGatewayServer(api_token="")
    assert open_server._is_authorized({}, {}) is True

    # Secured server
    secure_server = MobileGatewayServer(api_token="secret_aton_key")
    assert secure_server._is_authorized({}, {}) is False
    assert secure_server._is_authorized({"authorization": "Bearer secret_aton_key"}, {}) is True
    assert secure_server._is_authorized({"authorization": "Bearer wrong_key"}, {}) is False
    assert secure_server._is_authorized({}, {"token": "secret_aton_key"}) is True
    assert secure_server._is_authorized({}, {"token": "wrong_key"}) is False


@pytest.mark.asyncio
async def test_gateway_api_status(mock_assistant):
    """Test /api/status endpoint response."""
    server = MobileGatewayServer(assistant=mock_assistant, host="127.0.0.1", port=18444)
    await server.start()

    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", 18444)
        request = (
            "GET /api/status HTTP/1.1\r\n"
            "Host: 127.0.0.1\r\n"
            "Connection: close\r\n\r\n"
        )
        writer.write(request.encode("utf-8"))
        await writer.drain()

        response = await reader.read(4096)
        writer.close()
        await writer.wait_closed()

        text = response.decode("utf-8")
        assert "200 OK" in text
        assert "application/json" in text

        body = text.split("\r\n\r\n")[1]
        data = json.loads(body)
        assert data["status"] == "online"
        assert data["assistant_name"] == "Aton"
        assert data["state"] == "conversing"
        assert data["tools_count"] >= 17

    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_gateway_api_command_tool_dispatch(mock_assistant):
    """Test /api/command invoking tool_name directly."""
    server = MobileGatewayServer(assistant=mock_assistant, host="127.0.0.1", port=18445)
    await server.start()

    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", 18445)
        payload = json.dumps({
            "tool_name": "control_lights",
            "tool_args": {"action": "status"}
        })
        request = (
            f"POST /api/command HTTP/1.1\r\n"
            f"Host: 127.0.0.1\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(payload)}\r\n"
            f"Connection: close\r\n\r\n"
            f"{payload}"
        )
        writer.write(request.encode("utf-8"))
        await writer.drain()

        response = await reader.read(4096)
        writer.close()
        await writer.wait_closed()

        text = response.decode("utf-8")
        assert "200 OK" in text
        body = text.split("\r\n\r\n")[1]
        data = json.loads(body)
        assert "status" in data
        assert "message" in data

    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_gateway_api_command_text_heuristics(mock_assistant):
    """Test /api/command with voice transcript heuristics."""
    server = MobileGatewayServer(assistant=mock_assistant, host="127.0.0.1", port=18446)
    await server.start()

    try:
        # 1. Navigation command
        reader, writer = await asyncio.open_connection("127.0.0.1", 18446)
        payload = json.dumps({"command": "ir para o aeroporto"})
        request = (
            f"POST /api/command HTTP/1.1\r\n"
            f"Host: 127.0.0.1\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(payload)}\r\n"
            f"Connection: close\r\n\r\n"
            f"{payload}"
        )
        writer.write(request.encode("utf-8"))
        await writer.drain()
        response = await reader.read(4096)
        writer.close()
        await writer.wait_closed()
        assert "200 OK" in response.decode("utf-8")

        # 2. TV mute command
        reader, writer = await asyncio.open_connection("127.0.0.1", 18446)
        payload = json.dumps({"command": "mutar a tv"})
        request = (
            f"POST /api/command HTTP/1.1\r\n"
            f"Host: 127.0.0.1\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(payload)}\r\n"
            f"Connection: close\r\n\r\n"
            f"{payload}"
        )
        writer.write(request.encode("utf-8"))
        await writer.drain()
        response = await reader.read(4096)
        writer.close()
        await writer.wait_closed()
        assert "200 OK" in response.decode("utf-8")

        # 3. Find phone command
        reader, writer = await asyncio.open_connection("127.0.0.1", 18446)
        payload = json.dumps({"command": "onde está meu celular"})
        request = (
            f"POST /api/command HTTP/1.1\r\n"
            f"Host: 127.0.0.1\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(payload)}\r\n"
            f"Connection: close\r\n\r\n"
            f"{payload}"
        )
        writer.write(request.encode("utf-8"))
        await writer.drain()
        response = await reader.read(4096)
        writer.close()
        await writer.wait_closed()
        assert "200 OK" in response.decode("utf-8")

    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_gateway_mobile_ui_rendering(mock_assistant):
    """Test GET / returns Mobile HUD HTML page."""
    server = MobileGatewayServer(assistant=mock_assistant, host="127.0.0.1", port=18447)
    await server.start()

    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", 18447)
        request = (
            "GET /mobile HTTP/1.1\r\n"
            "Host: 127.0.0.1\r\n"
            "Connection: close\r\n\r\n"
        )
        writer.write(request.encode("utf-8"))
        await writer.drain()

        response = await reader.read(8192)
        writer.close()
        await writer.wait_closed()

        text = response.decode("utf-8")
        assert "200 OK" in text
        assert "text/html" in text
        assert "Aton - Painel Móvel & Carro" in text
        assert "Traçar Rota p/ Casa" in text
        assert "Posto Próximo" in text

    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_gateway_unauthorized_access(mock_assistant):
    """Test 401 when token is missing on protected server."""
    server = MobileGatewayServer(assistant=mock_assistant, host="127.0.0.1", port=18448, api_token="secret_pass")
    await server.start()

    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", 18448)
        request = (
            "GET /api/status HTTP/1.1\r\n"
            "Host: 127.0.0.1\r\n"
            "Connection: close\r\n\r\n"
        )
        writer.write(request.encode("utf-8"))
        await writer.drain()

        response = await reader.read(4096)
        writer.close()
        await writer.wait_closed()

        text = response.decode("utf-8")
        assert "401 Unauthorized" in text
        assert "Unauthorized" in text

    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_start_gateway_setting_toggle(mock_assistant):
    """Test start_gateway helper when disabled vs enabled."""
    with patch("src.integrations.mobile_gateway.settings.gateway_enabled", False):
        res = await start_gateway(assistant=mock_assistant)
        assert res is None

    with patch("src.integrations.mobile_gateway.settings.gateway_enabled", True), \
         patch("src.integrations.mobile_gateway.settings.gateway_port", 18449):
        srv = await start_gateway(assistant=mock_assistant)
        assert srv is not None
        assert srv.is_running
        await srv.stop()
