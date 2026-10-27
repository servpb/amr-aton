"""Google Maps, Navigation, and GPS tools for Aton (Phase 3)."""

import logging
import urllib.parse
import webbrowser
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Map friendly modes to Google Maps travel mode parameters
TRAVEL_MODES: Dict[str, str] = {
    "driving": "driving",
    "carro": "driving",
    "walking": "walking",
    "a pé": "walking",
    "transit": "transit",
    "transporte público": "transit",
    "ônibus": "transit",
    "bicycling": "bicycling",
    "bicicleta": "bicycling",
}

# Android intent mode characters
ANDROID_INTENT_MODES: Dict[str, str] = {
    "driving": "d",
    "walking": "w",
    "transit": "r",
    "bicycling": "b",
}

# Common place queries in Portuguese
PLACE_TYPE_QUERIES: Dict[str, str] = {
    "posto": "posto de gasolina",
    "gasolina": "posto de gasolina",
    "combustível": "posto de gasolina",
    "combustivel": "posto de gasolina",
    "gas_station": "posto de gasolina",
    "restaurante": "restaurante",
    "restaurant": "restaurante",
    "comida": "restaurante",
    "farmácia": "farmácia",
    "farmacia": "farmácia",
    "pharmacy": "farmácia",
    "hospital": "hospital",
    "estacionamento": "estacionamento",
    "parking": "estacionamento",
}


def navigate_to(
    destination: str,
    mode: str = "driving",
    avoid: Optional[str] = None,
) -> Dict[str, Any]:
    """Calculate and launch a turn-by-turn navigation route in Google Maps.

    Args:
        destination: Address, landmark, or city (e.g. 'Aeroporto de Congonhas', 'Avenida Paulista, 1000').
        mode: Travel mode ('driving', 'walking', 'transit', 'bicycling').
        avoid: Route restrictions ('tolls', 'highways', 'ferries').

    Returns:
        Dict with execution status, URLs, and spoken message.
    """
    cleaned_dest = destination.strip()
    if not cleaned_dest:
        return {"status": "error", "message": "Nenhum destino de navegação informado."}

    logger.info(f"Calculating Google Maps route to '{cleaned_dest}' (mode: {mode})...")

    # Resolve mode and avoid
    travel_mode = TRAVEL_MODES.get(mode.lower().strip(), "driving")
    intent_mode = ANDROID_INTENT_MODES.get(travel_mode, "d")
    encoded_dest = urllib.parse.quote_plus(cleaned_dest)

    # 1. Desktop & Web URL
    web_url = f"https://www.google.com/maps/dir/?api=1&destination={encoded_dest}&travelmode={travel_mode}"
    if avoid in ("tolls", "pedágios", "pedagios"):
        web_url += "&avoid=tolls"
    elif avoid in ("highways", "rodovias"):
        web_url += "&avoid=highways"

    # 2. Native Android Intent URI (zero Google Cloud cost, opens Maps in Turn-by-Turn GPS mode directly)
    android_intent = f"google.navigation:q={encoded_dest}&mode={intent_mode}"
    if avoid in ("tolls", "pedágios", "pedagios"):
        android_intent += "&avoid=t"
    elif avoid in ("highways", "rodovias"):
        android_intent += "&avoid=h"

    # Open route in default browser
    try:
        webbrowser.open(web_url)
    except Exception as exc:
        logger.error(f"Error opening Google Maps route: {exc}")

    avoid_text = ""
    if avoid in ("tolls", "pedágios", "pedagios"):
        avoid_text = " sem pedágios"
    elif avoid in ("highways", "rodovias"):
        avoid_text = " sem rodovias"

    return {
        "status": "success",
        "message": f"Traçando rota{avoid_text} para '{cleaned_dest}', senhor. Boa viagem!",
        "destination": cleaned_dest,
        "mode": travel_mode,
        "web_url": web_url,
        "android_intent": android_intent,
    }


def find_places_nearby(
    place_type: str = "posto de gasolina",
    location: Optional[str] = None,
) -> Dict[str, Any]:
    """Find nearby points of interest (gas stations, restaurants, pharmacies) on Google Maps.

    Args:
        place_type: Type of place ('posto', 'restaurante', 'farmácia', 'hospital', 'estacionamento').
        location: Optional city or neighborhood reference.

    Returns:
        Dict with status, search URLs, and spoken response.
    """
    cleaned_type = PLACE_TYPE_QUERIES.get(place_type.lower().strip(), place_type.strip())
    if location:
        query_text = f"{cleaned_type} em {location.strip()}"
    else:
        query_text = f"{cleaned_type} mais próximo"

    logger.info(f"Finding places nearby: '{query_text}'...")
    encoded_query = urllib.parse.quote_plus(query_text)

    web_url = f"https://www.google.com/maps/search/?api=1&query={encoded_query}"
    android_intent = f"geo:0,0?q={encoded_query}"

    try:
        webbrowser.open(web_url)
    except Exception as exc:
        logger.error(f"Error opening Google Maps search: {exc}")

    return {
        "status": "success",
        "message": f"Localizando {query_text} no Google Maps, senhor.",
        "query": query_text,
        "web_url": web_url,
        "android_intent": android_intent,
    }


def estimate_traffic_route(
    destination: str,
    origin: Optional[str] = None,
) -> Dict[str, Any]:
    """Check live traffic conditions and alternative routes to a destination.

    Args:
        destination: Destination name or address.
        origin: Optional starting point.

    Returns:
        Dict with status, live traffic map URL, and spoken confirmation.
    """
    cleaned_dest = destination.strip()
    encoded_dest = urllib.parse.quote_plus(cleaned_dest)

    web_url = f"https://www.google.com/maps/dir/?api=1&destination={encoded_dest}&travelmode=driving&layer=t"
    if origin:
        encoded_origin = urllib.parse.quote_plus(origin.strip())
        web_url += f"&origin={encoded_origin}"

    try:
        webbrowser.open(web_url)
    except Exception as exc:
        logger.error(f"Error opening traffic map: {exc}")

    return {
        "status": "success",
        "message": f"Consultando o trânsito em tempo real até '{cleaned_dest}', senhor.",
        "destination": cleaned_dest,
        "web_url": web_url,
    }


def dispatch_maps_tool(tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
    """Route Google Maps tool calls from Gemini Live."""
    if tool_name == "navigate_to":
        dest = tool_args.get("destination", "")
        mode = tool_args.get("mode", "driving")
        avoid = tool_args.get("avoid")
        return navigate_to(destination=dest, mode=mode, avoid=avoid)
    elif tool_name == "find_places_nearby":
        ptype = tool_args.get("place_type", "posto de gasolina")
        loc = tool_args.get("location")
        return find_places_nearby(place_type=ptype, location=loc)
    elif tool_name == "estimate_traffic_route":
        dest = tool_args.get("destination", "")
        orig = tool_args.get("origin")
        return estimate_traffic_route(destination=dest, origin=orig)
    else:
        return {
            "status": "error",
            "message": f"Ferramenta do Google Maps desconhecida '{tool_name}'.",
        }


# Gemini Live Function Declarations for Google Maps
GOOGLE_MAPS_FUNCTION_DECLARATIONS = [
    {
        "name": "navigate_to",
        "description": "Calcula rota e inicia a navegação curva a curva para um destino no Google Maps com suporte a opções de trânsito e pedágio.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "destination": {
                    "type": "STRING",
                    "description": "Destino desejado (ex: 'Aeroporto de Congonhas', 'Shopping Eldorado', 'Praia Grande').",
                },
                "mode": {
                    "type": "STRING",
                    "description": "Modo de transporte: 'driving' (carro), 'walking' (a pé), 'transit' (transporte público) ou 'bicycling' (bicicleta).",
                },
                "avoid": {
                    "type": "STRING",
                    "description": "Restrição de rota opcional: 'tolls' (evitar pedágios) ou 'highways' (evitar rodovias).",
                },
            },
            "required": ["destination"],
        },
    },
    {
        "name": "find_places_nearby",
        "description": "Localiza postos de gasolina, restaurantes, farmácias, hospitais ou estacionamentos próximos no Google Maps.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "place_type": {
                    "type": "STRING",
                    "description": "Tipo de local desejado: 'posto de gasolina', 'restaurante', 'farmácia', 'hospital' ou 'estacionamento'.",
                },
                "location": {
                    "type": "STRING",
                    "description": "Referência de cidade ou bairro (opcional).",
                },
            },
            "required": ["place_type"],
        },
    },
    {
        "name": "estimate_traffic_route",
        "description": "Consulta o trânsito em tempo real e visualiza o mapa de congestionamento até um destino.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "destination": {
                    "type": "STRING",
                    "description": "Destino para checar o fluxo de trânsito (ex: 'Marginal Pinheiros', 'Centro de Campinas').",
                },
                "origin": {
                    "type": "STRING",
                    "description": "Ponto de partida (opcional, padrão: localização atual).",
                },
            },
            "required": ["destination"],
        },
    },
]
