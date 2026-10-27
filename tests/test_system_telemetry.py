"""Tests for System Telemetry Tool (Phase 6)."""

import pytest
from src.tools.system_telemetry import (
    SYSTEM_TELEMETRY_FUNCTION_DECLARATIONS,
    dispatch_telemetry_tool,
    get_system_telemetry,
)
from src.tools import ALL_ATON_TOOLS, dispatch_tool


def test_get_system_telemetry_all():
    """Verify full telemetry returns battery, cpu, memory, and disk."""
    res = get_system_telemetry(metric="all")
    assert res["status"] == "success"
    assert "Status do sistema:" in res["message"]
    data = res["data"]
    assert "cpu" in data
    assert "memory" in data
    assert "disk" in data
    assert "battery" in data
    assert data["cpu"]["percent"] >= 0.0
    assert data["memory"]["percent"] >= 0.0
    assert data["disk"]["total_gb"] > 0


def test_get_system_telemetry_specific_metrics():
    """Verify individual metrics can be queried specifically."""
    # CPU
    cpu_res = get_system_telemetry(metric="cpu")
    assert cpu_res["status"] == "success"
    assert "cpu" in cpu_res["data"]
    assert "processador" in cpu_res["message"].lower() or "cpu" in cpu_res["message"].lower()

    # Memory
    mem_res = get_system_telemetry(metric="memory")
    assert mem_res["status"] == "success"
    assert "memory" in mem_res["data"]
    assert "memória" in mem_res["message"].lower()

    # Disk
    disk_res = get_system_telemetry(metric="disk")
    assert disk_res["status"] == "success"
    assert "disk" in disk_res["data"]
    assert "disco" in disk_res["message"].lower()

    # Battery
    battery_res = get_system_telemetry(metric="battery")
    assert battery_res["status"] == "success"
    assert "battery" in battery_res["data"]


def test_dispatch_telemetry_tool():
    """Verify tool dispatcher handles get_system_telemetry."""
    res = dispatch_telemetry_tool("get_system_telemetry", {"metric": "cpu"})
    assert res["status"] == "success"
    assert "cpu" in res["data"]

    # Unknown tool
    err_res = dispatch_telemetry_tool("unknown_telemetry", {})
    assert err_res["status"] == "error"


def test_unified_dispatch_telemetry():
    """Verify dispatch_tool routes get_system_telemetry correctly."""
    res = dispatch_tool("get_system_telemetry", {"metric": "all"})
    assert res["status"] == "success"
    assert "Status do sistema:" in res["message"]


def test_system_telemetry_in_all_aton_tools():
    """Verify get_system_telemetry is registered in ALL_ATON_TOOLS."""
    names = [t["name"] for t in ALL_ATON_TOOLS]
    assert "get_system_telemetry" in names
    assert any(t["name"] == "get_system_telemetry" for t in SYSTEM_TELEMETRY_FUNCTION_DECLARATIONS)
