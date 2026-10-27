"""Mobile Gateway and Remote Access server for Aton (Phase 3)."""

import asyncio
import json
import logging
from typing import Any, Dict, Optional, Tuple
import urllib.parse

from src.config import settings
from src.tools import ALL_ATON_TOOLS, dispatch_tool

logger = logging.getLogger(__name__)

# Sleek Mobile HUD HTML/CSS/JS Interface for in-car and mobile use
MOBILE_UI_HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Aton - Painel Móvel & Carro</title>
    <style>
        :root {
            --bg-color: #0b0f19;
            --card-bg: rgba(22, 30, 49, 0.85);
            --primary: #38bdf8;
            --primary-glow: rgba(56, 189, 248, 0.4);
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --success: #10b981;
            --danger: #ef4444;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
        body {
            background-color: var(--bg-color);
            color: var(--text-main);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 16px;
            overflow-x: hidden;
        }
        .header {
            width: 100%;
            max-width: 480px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 18px;
            background: var(--card-bg);
            backdrop-filter: blur(12px);
            border-radius: 16px;
            border: 1px solid rgba(255, 255, 255, 0.08);
            margin-bottom: 20px;
        }
        .brand { font-size: 20px; font-weight: 800; letter-spacing: 1px; color: var(--primary); }
        .status-badge {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 13px;
            color: var(--text-muted);
            background: rgba(0,0,0,0.3);
            padding: 4px 10px;
            border-radius: 20px;
        }
        .status-dot { width: 8px; height: 8px; border-radius: 50%; background-color: var(--success); }
        
        .main-container {
            width: 100%;
            max-width: 480px;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 20px;
            flex-grow: 1;
        }

        /* Large Car-Friendly PTT Button */
        .ptt-container {
            display: flex;
            flex-direction: column;
            align-items: center;
            margin: 20px 0;
        }
        .ptt-button {
            width: 160px;
            height: 160px;
            border-radius: 50%;
            background: radial-gradient(circle, #0284c7 0%, #0369a1 100%);
            border: 4px solid var(--primary);
            color: #fff;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            box-shadow: 0 0 35px var(--primary-glow);
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            user-select: none;
            -webkit-user-select: none;
        }
        .ptt-button:active, .ptt-button.active {
            transform: scale(0.94);
            box-shadow: 0 0 50px rgba(56, 189, 248, 0.8);
            background: radial-gradient(circle, #0369a1 0%, #0c4a6e 100%);
        }
        .ptt-icon { font-size: 44px; margin-bottom: 4px; }
        .ptt-label { font-size: 13px; font-weight: 700; letter-spacing: 0.5px; text-transform: uppercase; }

        /* Output Card */
        .response-card {
            width: 100%;
            background: var(--card-bg);
            border-radius: 16px;
            border: 1px solid rgba(255, 255, 255, 0.08);
            padding: 16px;
            min-height: 90px;
            font-size: 15px;
            line-height: 1.5;
            color: var(--text-main);
            display: flex;
            align-items: center;
            justify-content: center;
            text-align: center;
        }

        /* Quick Action Grid */
        .section-title { width: 100%; font-size: 13px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; margin-top: 10px; }
        .quick-actions {
            width: 100%;
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 12px;
        }
        .action-btn {
            background: var(--card-bg);
            border: 1px solid rgba(255, 255, 255, 0.08);
            color: var(--text-main);
            padding: 14px 12px;
            border-radius: 12px;
            font-size: 14px;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 10px;
            cursor: pointer;
            transition: background 0.15s ease;
        }
        .action-btn:active { background: rgba(56, 189, 248, 0.15); border-color: var(--primary); }
        .action-btn span { font-size: 20px; }
    </style>
</head>
<body>
    <header class="header">
        <div class="brand">ATON</div>
        <div class="status-badge">
            <span class="status-dot"></span>
            <span id="conn-text">Tailscale Conectado</span>
        </div>
    </header>

    <main class="main-container">
        <div class="response-card" id="response-box">
            Às suas ordens, senhor. Toque no botão para falar ou use os atalhos abaixo.
        </div>

        <div class="ptt-container">
            <button class="ptt-button" id="ptt-btn">
                <span class="ptt-icon">🎙️</span>
                <span class="ptt-label">Falar</span>
            </button>
        </div>

        <div class="section-title">Ações Rápidas (Carro, Casa & PC)</div>
        <div class="quick-actions">
            <button class="action-btn" onclick="sendQuickAction('get_daily_briefing', {})">
                <span>📋</span> Resumo do Dia
            </button>
            <button class="action-btn" onclick="sendQuickAction('get_system_telemetry', {metric: 'all'})">
                <span>📊</span> Status do PC
            </button>
            <button class="action-btn" onclick="sendQuickAction('set_system_volume', {level: 50})">
                <span>🔊</span> Volume PC 50%
            </button>
            <button class="action-btn" onclick="sendQuickAction('control_system_media', {action: 'play_pause'})">
                <span>⏯️</span> Play / Pause
            </button>
            <button class="action-btn" onclick="sendQuickAction('control_system_media', {action: 'next'})">
                <span>⏭️</span> Próxima Faixa
            </button>
            <button class="action-btn" onclick="sendQuickAction('navigate_to', {destination: 'Casa'})">
                <span>🚗</span> Traçar Rota p/ Casa
            </button>
            <button class="action-btn" onclick="sendQuickAction('find_places_nearby', {place_type: 'posto de gasolina'})">
                <span>⛽</span> Posto Próximo
            </button>
            <button class="action-btn" onclick="sendQuickAction('control_tv_volume', {action: 'mute'})">
                <span>📺</span> TV no Mudo
            </button>
            <button class="action-btn" onclick="sendQuickAction('control_lights', {action: 'off'})">
                <span>💡</span> Apagar Luzes
            </button>
            <button class="action-btn" onclick="sendQuickAction('find_phone', {action: 'ring'})">
                <span>📱</span> Localizar Celular
            </button>
            <button class="action-btn" onclick="sendQuickAction('search_youtube', {query: 'música para viagem'})">
                <span>🎵</span> Música na Estrada
            </button>
        </div>
    </main>

    <script>
        const responseBox = document.getElementById('response-box');
        const pttBtn = document.getElementById('ptt-btn');

        async function sendCommand(payload) {
            responseBox.innerText = "Processando comando...";
            try {
                const res = await fetch('/api/command', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                const reply = data.message || "Comando executado com sucesso, senhor.";
                responseBox.innerText = reply;
                speakReply(reply);
            } catch (err) {
                responseBox.innerText = "Erro ao conectar com o Aton no PC: " + err;
            }
        }

        function sendQuickAction(toolName, args) {
            sendCommand({ tool_name: toolName, tool_args: args });
        }

        function speakReply(text) {
            if ('speechSynthesis' in window) {
                window.speechSynthesis.cancel();
                const utterance = new SpeechSynthesisUtterance(text);
                utterance.lang = 'pt-BR';
                window.speechSynthesis.speak(utterance);
            }
        }

        // Web Speech API for Push-to-Talk
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (SpeechRecognition) {
            const recognition = new SpeechRecognition();
            recognition.lang = 'pt-BR';
            recognition.continuous = false;
            recognition.interimResults = false;

            recognition.onstart = () => {
                pttBtn.classList.add('active');
                responseBox.innerText = "Ouvindo você falar no microfone...";
            };

            recognition.onresult = (event) => {
                const transcript = event.results[0][0].transcript;
                responseBox.innerText = 'Você: "' + transcript + '"';
                sendCommand({ command: transcript });
            };

            recognition.onerror = (event) => {
                responseBox.innerText = "Erro ao captar voz: " + event.error;
                pttBtn.classList.remove('active');
            };

            recognition.onend = () => {
                pttBtn.classList.remove('active');
            };

            pttBtn.addEventListener('click', () => {
                try {
                    recognition.start();
                } catch(e) {
                    recognition.stop();
                }
            });
        } else {
            pttBtn.addEventListener('click', () => {
                const text = prompt("Digite seu comando para o Aton:");
                if (text) sendCommand({ command: text });
            });
        }
    </script>
</body>
</html>
"""


class MobileGatewayServer:
    """Lightweight async HTTP server for remote mobile and car access over Tailscale."""

    def __init__(
        self,
        assistant: Any = None,
        host: str = "0.0.0.0",
        port: int = 8443,
        api_token: str = "",
    ):
        self.assistant = assistant
        self.host = host
        self.port = port
        self.api_token = api_token
        self._server: Optional[asyncio.Server] = None
        self._is_running = False

    async def start(self) -> bool:
        """Start the background async HTTP server."""
        if self._is_running:
            return True

        try:
            self._server = await asyncio.start_server(
                self._handle_client,
                self.host,
                self.port,
            )
            self._is_running = True
            logger.info(f"📱 Mobile Gateway online em http://{self.host}:{self.port} (Tailscale)")
            return True
        except Exception as exc:
            logger.error(f"Erro ao iniciar Mobile Gateway na porta {self.port}: {exc}")
            self._is_running = False
            return False

    async def stop(self) -> None:
        """Stop the background gateway server cleanly."""
        if not self._is_running or self._server is None:
            return

        self._server.close()
        await self._server.wait_closed()
        self._server = None
        self._is_running = False
        logger.info("Mobile Gateway finalizado com sucesso.")

    def _is_authorized(self, headers: Dict[str, str], query_params: Dict[str, str]) -> bool:
        """Verify API token if configured."""
        if not self.api_token:
            return True  # Open within private Tailscale VPN mesh

        auth_header = headers.get("authorization", "")
        if auth_header.startswith("Bearer ") and auth_header[7:].strip() == self.api_token:
            return True

        if query_params.get("token") == self.api_token:
            return True

        return False

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Process incoming HTTP requests from mobile client or Tasker."""
        try:
            # Read HTTP request header
            data = await reader.read(4096)
            if not data:
                writer.close()
                return

            text = data.decode("utf-8", errors="ignore")
            lines = text.split("\r\n")
            if not lines:
                writer.close()
                return

            request_line = lines[0]
            parts = request_line.split(" ")
            if len(parts) < 2:
                writer.close()
                return

            method = parts[0].upper()
            full_path = parts[1]

            # Parse headers
            headers = {}
            body_start_index = 0
            for i, line in enumerate(lines[1:], start=1):
                if not line:
                    body_start_index = i + 1
                    break
                if ":" in line:
                    k, v = line.split(":", 1)
                    headers[k.strip().lower()] = v.strip()

            body = "\r\n".join(lines[body_start_index:]) if body_start_index < len(lines) else ""

            # Parse URL and query params
            parsed_url = urllib.parse.urlparse(full_path)
            path = parsed_url.path
            query_params = dict(urllib.parse.parse_qsl(parsed_url.query))

            # Security check
            if not self._is_authorized(headers, query_params):
                self._send_response(writer, 401, "application/json", json.dumps({"error": "Unauthorized"}))
                return

            # Route 1: Status API
            if method == "GET" and path == "/api/status":
                state_val = getattr(self.assistant, "state", "running")
                if hasattr(state_val, "value"):
                    state_val = state_val.value
                resp_data = {
                    "status": "online",
                    "assistant_name": "Aton",
                    "version": "0.1.0",
                    "state": str(state_val),
                    "tools_count": len(ALL_ATON_TOOLS),
                }
                self._send_response(writer, 200, "application/json", json.dumps(resp_data))

            # Route 2: Command Execution API
            elif method == "POST" and path == "/api/command":
                try:
                    payload = json.loads(body) if body else {}
                except Exception:
                    payload = {}

                tool_name = payload.get("tool_name")
                tool_args = payload.get("tool_args", {})
                command_text = payload.get("command")

                result: Dict[str, Any] = {}
                if tool_name:
                    logger.info(f"📱 Remote Mobile command received: {tool_name}({tool_args})")
                    result = dispatch_tool(tool_name, tool_args)
                elif command_text:
                    logger.info(f"📱 Remote Mobile voice text command: '{command_text}'")
                    result = self._process_text_command(command_text)
                else:
                    result = {"status": "error", "message": "Nenhum comando ou ferramenta especificada."}

                self._send_response(writer, 200, "application/json", json.dumps(result))

            # Route 3: Mobile PWA / Web HUD UI
            elif method == "GET" and path in ("/", "/mobile", "/index.html"):
                self._send_response(writer, 200, "text/html; charset=utf-8", MOBILE_UI_HTML)

            else:
                self._send_response(writer, 404, "application/json", json.dumps({"error": "Not Found"}))

        except Exception as exc:
            logger.error(f"Error handling Mobile Gateway request: {exc}")
            try:
                self._send_response(writer, 500, "application/json", json.dumps({"error": str(exc)}))
            except Exception:
                pass
        finally:
            try:
                await writer.drain()
                writer.close()
            except Exception:
                pass

    def _process_text_command(self, text: str) -> Dict[str, Any]:
        """Simple natural language heuristic for remote mobile actions."""
        lower = text.lower().strip()

        # Navigation & Maps
        if "rota" in lower or "como chego" in lower or "ir para" in lower:
            # Extract destination
            dest = lower.replace("trace uma rota para", "").replace("trace rota para", "").replace("ir para", "").strip()
            return dispatch_tool("navigate_to", {"destination": dest or "Centro"})
        elif "posto" in lower or "gasolina" in lower:
            return dispatch_tool("find_places_nearby", {"place_type": "posto de gasolina"})

        # Smart TV
        elif "tv" in lower and ("mudo" in lower or "mutar" in lower):
            return dispatch_tool("control_tv_volume", {"action": "mute"})
        elif "tv" in lower and ("pause" in lower or "pausar" in lower):
            return dispatch_tool("control_tv_media", {"action": "pause"})

        # Lights & Plugs
        elif "luz" in lower and ("apagar" in lower or "desligar" in lower):
            return dispatch_tool("control_lights", {"action": "off"})
        elif "luz" in lower and ("acender" in lower or "ligar" in lower):
            return dispatch_tool("control_lights", {"action": "on"})
        elif "celular" in lower and ("onde" in lower or "tocar" in lower or "achar" in lower):
            return dispatch_tool("find_phone", {"action": "ring"})

        # Google Calendar
        elif "agenda" in lower or "compromisso" in lower or "o que tenho" in lower:
            return dispatch_tool("get_calendar_events", {"time_min": "hoje"})

        # Gmail
        elif "email" in lower or "e-mail" in lower or "correio" in lower:
            return dispatch_tool("list_unread_emails", {"max_results": 5})

        # Google Tasks
        elif "tarefa" in lower or "lembrete" in lower or "pendênci" in lower or "pendenci" in lower:
            return dispatch_tool("list_tasks", {"show_completed": False})

        # Daily Briefing (Phase 5)
        elif "resumo" in lower or "briefing" in lower or "bom dia" in lower:
            return dispatch_tool("get_daily_briefing", {})

        # Semantic Memory (Phase 5)
        elif "lembre-se" in lower or "lembrar que" in lower:
            fact = lower.replace("lembre-se de que", "").replace("lembre-se que", "").replace("lembre-se", "").strip()
            return dispatch_tool("remember_fact", {"category": "preferência", "key": "nota_voz", "content": fact or text})
        # System Telemetry (Phase 6)
        elif "status do pc" in lower or "desempenho" in lower or "como está o pc" in lower or "como esta o pc" in lower:
            return dispatch_tool("get_system_telemetry", {"metric": "all"})
        elif "bateria" in lower:
            return dispatch_tool("get_system_telemetry", {"metric": "battery"})
        elif "processador" in lower or "cpu" in lower:
            return dispatch_tool("get_system_telemetry", {"metric": "cpu"})
        elif "memória" in lower or "memoria" in lower or "ram" in lower:
            return dispatch_tool("get_system_telemetry", {"metric": "memory"})
        elif "disco" in lower or "armazenamento" in lower or "espaço livre" in lower or "espaco livre" in lower:
            return dispatch_tool("get_system_telemetry", {"metric": "disk"})

        # System Audio & Media (Phase 6)
        elif "volume do pc" in lower or "volume do computador" in lower or "volume em" in lower:
            import re
            match = re.search(r'\b(\d{1,3})\b', lower)
            vol_val = int(match.group(1)) if match else 50
            return dispatch_tool("set_system_volume", {"level": vol_val})
        elif "mutar pc" in lower or "mudo no pc" in lower or "mute o pc" in lower:
            return dispatch_tool("set_system_volume", {"mute": True})
        elif "desmutar pc" in lower:
            return dispatch_tool("set_system_volume", {"mute": False})
        elif "pausar música" in lower or "pausar musica" in lower or "pause a música" in lower or "pause a musica" in lower or "play/pause" in lower:
            return dispatch_tool("control_system_media", {"action": "play_pause"})
        elif "próxima música" in lower or "proxima musica" in lower or "pular música" in lower or "pular musica" in lower:
            return dispatch_tool("control_system_media", {"action": "next"})
        elif "música anterior" in lower or "musica anterior" in lower or "voltar música" in lower or "voltar musica" in lower:
            return dispatch_tool("control_system_media", {"action": "previous"})

        # Default web search
        return dispatch_tool("web_search", {"query": text})

    def _send_response(
        self,
        writer: asyncio.StreamWriter,
        status_code: int,
        content_type: str,
        body: str,
    ) -> None:
        """Write formatted HTTP response headers and body."""
        body_bytes = body.encode("utf-8")
        status_text = {
            200: "OK",
            401: "Unauthorized",
            404: "Not Found",
            500: "Internal Server Error",
        }.get(status_code, "OK")

        response_header = (
            f"HTTP/1.1 {status_code} {status_text}\r\n"
            f"Content-Type: {content_type}\r\n"
            f"Content-Length: {len(body_bytes)}\r\n"
            f"Access-Control-Allow-Origin: *\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        )
        writer.write(response_header.encode("utf-8") + body_bytes)

    @property
    def is_running(self) -> bool:
        """Return True if gateway server is currently listening."""
        return self._is_running


async def start_gateway(assistant: Any = None) -> Optional[MobileGatewayServer]:
    """Factory helper to start the mobile gateway if enabled in settings."""
    if not settings.gateway_enabled:
        return None

    server = MobileGatewayServer(
        assistant=assistant,
        host=settings.gateway_host,
        port=settings.gateway_port,
        api_token=settings.gateway_api_token,
    )
    started = await server.start()
    return server if started else None
