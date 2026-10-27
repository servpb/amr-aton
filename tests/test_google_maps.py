"""Unit tests for Google Maps, Navigation, and GPS tools (Phase 3)."""

from unittest.mock import patch
import pytest

from src.tools import ALL_ATON_TOOLS, dispatch_tool
from src.tools.google_maps import (
    GOOGLE_MAPS_FUNCTION_DECLARATIONS,
    dispatch_maps_tool,
    estimate_traffic_route,
    find_places_nearby,
    navigate_to,
)


def test_google_maps_declarations_schema():
    """Verify Google Maps function declarations schema."""
    assert len(GOOGLE_MAPS_FUNCTION_DECLARATIONS) == 3
    names = [t["name"] for t in GOOGLE_MAPS_FUNCTION_DECLARATIONS]
    assert "navigate_to" in names
    assert "find_places_nearby" in names
    assert "estimate_traffic_route" in names

    for decl in GOOGLE_MAPS_FUNCTION_DECLARATIONS:
        assert "name" in decl
        assert "description" in decl
        assert "parameters" in decl
        assert decl["parameters"]["type"] == "OBJECT"


@patch("webbrowser.open")
def test_navigate_to_driving(mock_open):
    """Verify navigate_to constructs Google Maps web URL and Android navigation intent."""
    res = navigate_to("Aeroporto de Congonhas", mode="driving")
    assert res["status"] == "success"
    assert "Congonhas" in res["message"]
    assert "travelmode=driving" in res["web_url"]
    assert "google.navigation:q=" in res["android_intent"]
    assert "mode=d" in res["android_intent"]
    mock_open.assert_called_once_with(res["web_url"])


@patch("webbrowser.open")
def test_navigate_to_avoid_tolls(mock_open):
    """Verify navigate_to adds avoid tolls parameters."""
    res = navigate_to("Campinas", mode="carro", avoid="pedágios")
    assert res["status"] == "success"
    assert "avoid=tolls" in res["web_url"]
    assert "avoid=t" in res["android_intent"]
    assert "sem pedágios" in res["message"]


@patch("webbrowser.open")
def test_navigate_to_avoid_highways(mock_open):
    """Verify navigate_to adds avoid highways parameters."""
    res = navigate_to("Santos", mode="carro", avoid="rodovias")
    assert res["status"] == "success"
    assert "avoid=highways" in res["web_url"]
    assert "avoid=h" in res["android_intent"]


def test_navigate_to_empty_destination():
    """Verify navigate_to safely rejects blank destination."""
    res = navigate_to("   ")
    assert res["status"] == "error"
    assert "Nenhum destino" in res["message"]


@patch("webbrowser.open")
def test_find_places_nearby_gas_station(mock_open):
    """Verify find_places_nearby maps 'posto' to 'posto de gasolina'."""
    res = find_places_nearby(place_type="posto")
    assert res["status"] == "success"
    assert "posto de gasolina mais próximo" in res["message"]
    assert "geo:0,0?q=" in res["android_intent"]
    mock_open.assert_called_once()


@patch("webbrowser.open")
def test_find_places_nearby_with_location(mock_open):
    """Verify find_places_nearby appends location reference."""
    res = find_places_nearby(place_type="farmácia", location="Vila Mariana")
    assert res["status"] == "success"
    assert "farmácia em Vila Mariana" in res["message"]


@patch("webbrowser.open")
def test_estimate_traffic_route(mock_open):
    """Verify estimate_traffic_route adds traffic layer."""
    res = estimate_traffic_route(destination="Avenida Paulista")
    assert res["status"] == "success"
    assert "layer=t" in res["web_url"]
    assert "Avenida Paulista" in res["message"]
    mock_open.assert_called_once()


def test_dispatch_maps_tool():
    """Verify dispatch_maps_tool routes tool calls correctly."""
    with patch("src.tools.google_maps.navigate_to") as mock_nav:
        mock_nav.return_value = {"status": "success"}
        res = dispatch_maps_tool("navigate_to", {"destination": "Museu do Ipiranga"})
        assert res["status"] == "success"
        mock_nav.assert_called_once_with(destination="Museu do Ipiranga", mode="driving", avoid=None)

    with patch("src.tools.google_maps.find_places_nearby") as mock_find:
        mock_find.return_value = {"status": "success"}
        res = dispatch_maps_tool("find_places_nearby", {"place_type": "restaurante"})
        assert res["status"] == "success"
        mock_find.assert_called_once_with(place_type="restaurante", location=None)

    with patch("src.tools.google_maps.estimate_traffic_route") as mock_traf:
        mock_traf.return_value = {"status": "success"}
        res = dispatch_maps_tool("estimate_traffic_route", {"destination": "Shopping"})
        assert res["status"] == "success"
        mock_traf.assert_called_once_with(destination="Shopping", origin=None)

    res_unknown = dispatch_maps_tool("unknown_maps_tool", {})
    assert res_unknown["status"] == "error"


def test_unified_dispatcher_maps():
    """Verify unified dispatch_tool routes navigate_to."""
    with patch("src.tools.dispatch_maps_tool") as mock_dm:
        mock_dm.return_value = {"status": "success"}
        res = dispatch_tool("navigate_to", {"destination": "Santos"})
        assert res["status"] == "success"
        mock_dm.assert_called_once()


def test_all_aton_tools_count_with_maps():
    """Verify ALL_ATON_TOOLS includes at least 17 tools."""
    assert len(ALL_ATON_TOOLS) >= 17
    names = [t["name"] for t in ALL_ATON_TOOLS]
    assert "navigate_to" in names
    assert "find_places_nearby" in names
    assert "estimate_traffic_route" in names
