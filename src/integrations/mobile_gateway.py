"""Mobile Gateway, Network Discovery, and Authorized Device Access server for Aton (Phase 3 & Phase 11)."""

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
import urllib.parse

from src.config import settings
from src.core.device_manager import DeviceManager, TOOL_PERMISSION_MAP
from src.core.network_discovery import NetworkDiscovery
from src.tools import ALL_ATON_TOOLS, dispatch_tool

logger = logging.getLogger(__name__)

# Sleek Multi-Device Responsive UI (Mobile HUD, Smart TV, and Network Devices Manager)
MOBILE_UI_HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Aton - Painel Móvel & Carro</title>
    <style>
        :root { --bg: #0b0f19; --card: rgba(22,30,49,0.85); --border: rgba(255,255,255,0.08); --primary: #38bdf8; --glow: rgba(56,189,248,0.35); --text: #f8fafc; --muted: #94a3b8; --success: #10b981; --danger: #ef4444; }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
        body { background: var(--bg); color: var(--text); min-height: 100vh; display: flex; flex-direction: column; align-items: center; padding: 12px; }
        .header { width: 100%; max-width: 680px; display: flex; justify-content: space-between; align-items: center; padding: 12px 18px; background: var(--card); backdrop-filter: blur(14px); border-radius: 16px; border: 1px solid var(--border); margin-bottom: 14px; }
        .brand { font-size: 22px; font-weight: 800; letter-spacing: 1.5px; color: var(--primary); }
        .status-badge { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--muted); background: rgba(0,0,0,0.4); padding: 6px 12px; border-radius: 20px; }
        .status-dot { width: 9px; height: 9px; border-radius: 50%; background: var(--success); }
        .tabs { width: 100%; max-width: 680px; display: flex; gap: 8px; margin-bottom: 14px; }
        .tab-btn { flex: 1; padding: 10px 12px; border-radius: 12px; background: var(--card); border: 1px solid var(--border); color: var(--muted); font-size: 14px; font-weight: 600; cursor: pointer; text-align: center; }
        .tab-btn.active { background: rgba(56,189,248,0.15); border-color: var(--primary); color: var(--text); box-shadow: 0 0 15px var(--glow); }
        .main-container { width: 100%; max-width: 680px; display: flex; flex-direction: column; gap: 16px; flex-grow: 1; }
        .tab-content { display: none; width: 100%; flex-direction: column; gap: 16px; }
        .tab-content.active { display: flex; }
        .card { background: var(--card); border-radius: 16px; border: 1px solid var(--border); padding: 18px; backdrop-filter: blur(12px); }
        .card-title { font-size: 15px; font-weight: 700; color: var(--primary); text-transform: uppercase; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; }
        .form-group { display: flex; flex-direction: column; gap: 6px; margin-bottom: 12px; }
        .form-label { font-size: 13px; color: var(--muted); }
        .form-input, .form-select { background: rgba(0,0,0,0.4); border: 1px solid var(--border); padding: 10px 14px; border-radius: 10px; color: var(--text); font-size: 14px; outline: none; }
        .form-input:focus, .form-select:focus { border-color: var(--primary); }
        .btn-action { background: var(--primary); color: #0b0f19; font-weight: 700; border: none; padding: 12px 18px; border-radius: 10px; cursor: pointer; width: 100%; font-size: 14px; }
        .btn-action:hover { background: #0284c7; color: #fff; }
        .btn-danger { background: var(--danger); color: #fff; padding: 6px 12px; border-radius: 8px; border: none; cursor: pointer; font-size: 12px; }
        .ptt-container { display: flex; flex-direction: column; align-items: center; margin: 16px 0; }
        .ptt-button { width: 150px; height: 150px; border-radius: 50%; background: radial-gradient(circle, #0284c7 0%, #0369a1 100%); border: 4px solid var(--primary); color: #fff; display: flex; flex-direction: column; align-items: center; justify-content: center; cursor: pointer; box-shadow: 0 0 35px var(--glow); transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1); user-select: none; }
        .ptt-button:active, .ptt-button.active { transform: scale(0.94); box-shadow: 0 0 50px rgba(56,189,248,0.8); background: radial-gradient(circle, #0369a1 0%, #0c4a6e 100%); }
        .ptt-icon { font-size: 42px; margin-bottom: 4px; }
        .ptt-label { font-size: 13px; font-weight: 700; text-transform: uppercase; }
        .response-card { background: var(--card); border-radius: 16px; border: 1px solid var(--border); padding: 16px; min-height: 80px; font-size: 15px; line-height: 1.5; color: var(--text); display: flex; align-items: center; justify-content: center; text-align: center; }
        .quick-actions { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
        .action-btn { background: var(--card); border: 1px solid var(--border); color: var(--text); padding: 12px 10px; border-radius: 12px; font-size: 13px; font-weight: 600; display: flex; align-items: center; gap: 8px; cursor: pointer; }
        .action-btn:hover { background: rgba(56,189,248,0.12); border-color: var(--primary); }
        .device-item { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid var(--border); }
        .device-item:last-child { border-bottom: none; }
        .device-info { display: flex; flex-direction: column; gap: 2px; }
        .device-name { font-weight: 600; font-size: 14px; }
        .device-sub { font-size: 12px; color: var(--muted); }
        .tv-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
        .tv-btn { background: var(--card); border: 2px solid var(--border); border-radius: 16px; padding: 24px 12px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; color: var(--text); font-size: 15px; font-weight: 700; cursor: pointer; }
        .tv-btn:focus, .tv-btn:hover { border-color: var(--primary); background: rgba(56,189,248,0.2); transform: scale(1.03); box-shadow: 0 0 20px var(--glow); outline: none; }
        .tv-btn span { font-size: 32px; }
    </style>
</head>
<body>
    <header class="header">
        <div class="brand">ATON</div>
        <div class="status-badge">
            <span class="status-dot"></span>
            <span id="conn-text">Conectando...</span>
        </div>
    </header>

    <nav class="tabs">
        <button class="tab-btn active" onclick="switchTab('hud')">🎙️ Assistente</button>
        <button class="tab-btn" onclick="switchTab('network')">🌐 Rede & Dispositivos</button>
        <button class="tab-btn" onclick="switchTab('tv')">📺 Modo TV</button>
    </nav>

    <main class="main-container">
        <!-- TAB 1: HUD & VOZ -->
        <div id="tab-hud" class="tab-content active">
            <div class="response-card" id="response-box">
                Às suas ordens, senhor. Toque no botão para falar ou use os atalhos abaixo.
            </div>

            <div class="ptt-container">
                <button class="ptt-button" id="ptt-btn">
                    <span class="ptt-icon">🎙️</span>
                    <span class="ptt-label">Falar</span>
                </button>
            </div>

            <div class="quick-actions">
                <button class="action-btn" onclick="sendQuickAction('get_daily_briefing', {})"><span>📋</span> Resumo do Dia</button>
                <button class="action-btn" onclick="sendQuickAction('get_system_telemetry', {metric: 'all'})"><span>📊</span> Status do PC</button>
                <button class="action-btn" onclick="sendQuickAction('set_system_volume', {level: 50})"><span>🔊</span> Volume PC 50%</button>
                <button class="action-btn" onclick="sendQuickAction('control_system_media', {action: 'play_pause'})"><span>⏯️</span> Play / Pause</button>
                <button class="action-btn" onclick="sendQuickAction('navigate_to', {destination: 'Casa'})"><span>🚗</span> Traçar Rota p/ Casa</button>
                <button class="action-btn" onclick="sendQuickAction('find_places_nearby', {place_type: 'posto de gasolina'})"><span>⛽</span> Posto Próximo</button>
                <button class="action-btn" onclick="sendQuickAction('control_lights', {action: 'off'})"><span>💡</span> Apagar Luzes</button>
                <button class="action-btn" onclick="sendQuickAction('find_phone', {action: 'ring'})"><span>📱</span> Localizar Celular</button>
            </div>
        </div>

        <!-- TAB 2: REDE E DISPOSITIVOS AUTORIZADOS -->
        <div id="tab-network" class="tab-content">
            <!-- Host Network Info Card -->
            <div class="card">
                <div class="card-title">
                    <span>📡 Computador Anfitrião ATON</span>
                    <button class="btn-action" style="width: auto; padding: 4px 10px; font-size: 12px;" onclick="loadNetworkInfo()">Atualizar</button>
                </div>
                <div id="host-network-info" style="font-size: 13px; line-height: 1.6; color: var(--text-muted);">
                    Carregando interfaces de rede...
                </div>
            </div>

            <!-- Pairing Card -->
            <div class="card" id="pairing-card">
                <div class="card-title">🔐 Pareamento de Novo Dispositivo</div>
                <div class="form-group">
                    <label class="form-label">Nome deste Dispositivo:</label>
                    <input type="text" id="dev-name" class="form-input" placeholder="Ex: Meu Celular, Tablet, Smart TV">
                </div>
                <div class="form-group">
                    <label class="form-label">Tipo de Dispositivo:</label>
                    <select id="dev-type" class="form-select">
                        <option value="mobile">Celular / Smartphone</option>
                        <option value="desktop">Outro Computador / Notebook</option>
                        <option value="tv">Smart TV</option>
                        <option value="other">Outro</option>
                    </select>
                </div>
                <button class="btn-action" onclick="requestDevicePairing()">1. Solicitar Pareamento e Gerar PIN</button>

                <div id="pin-verification-box" style="display: none; margin-top: 14px; padding-top: 14px; border-top: 1px solid var(--card-border);">
                    <div class="form-group">
                        <label class="form-label">Código PIN (6 dígitos):</label>
                        <input type="text" id="pin-input" class="form-input" placeholder="Digite o PIN de 6 dígitos">
                    </div>
                    <button class="btn-action" style="background: var(--success);" onclick="confirmDevicePairing()">2. Validar PIN e Conectar</button>
                </div>
            </div>

            <!-- Authorized Devices List -->
            <div class="card">
                <div class="card-title">
                    <span>📱 Dispositivos Autorizados</span>
                    <button class="btn-action" style="width: auto; padding: 4px 10px; font-size: 12px;" onclick="loadPairedDevices()">Recarregar</button>
                </div>
                <div id="paired-devices-list" style="font-size: 13px;">
                    Carregando dispositivos autorizados...
                </div>
            </div>

            <!-- Controlled Subnet Discovery -->
            <div class="card">
                <div class="card-title">🔍 Descobrir Serviços ATON na Rede</div>
                <div class="form-group">
                    <label class="form-label">Sub-rede para Sonda Controlada (Opcional):</label>
                    <input type="text" id="subnet-input" class="form-input" placeholder="Ex: 192.168.0.0/24 (Deixe vazio para mDNS)">
                </div>
                <button class="btn-action" onclick="scanNetwork()">Procurar Serviços ATON</button>
                <div id="scan-results" style="margin-top: 10px; font-size: 13px; color: var(--text-muted);"></div>
            </div>
        </div>

        <!-- TAB 3: MODO TV -->
        <div id="tab-tv" class="tab-content">
            <div class="response-card" id="tv-response-box">
                Controle Remoto Smart TV ATON - Use as teclas do controle para navegar
            </div>
            <div class="tv-grid">
                <button class="tv-btn" onclick="sendQuickAction('control_tv_volume', {action: 'vol_up'})"><span>🔊</span> Vol +</button>
                <button class="tv-btn" onclick="sendQuickAction('control_tv_media', {action: 'play_pause'})"><span>⏯️</span> Play/Pause</button>
                <button class="tv-btn" onclick="sendQuickAction('control_tv_volume', {action: 'vol_down'})"><span>🔉</span> Vol -</button>
                <button class="tv-btn" onclick="sendQuickAction('control_tv_volume', {action: 'mute'})"><span>🔇</span> Mudo</button>
                <button class="tv-btn" onclick="sendQuickAction('get_daily_briefing', {})"><span>📋</span> Resumo</button>
                <button class="tv-btn" onclick="sendQuickAction('control_tv_power', {})"><span>⚡</span> TV Power</button>
                <button class="tv-btn" onclick="sendQuickAction('control_lights', {action: 'on'})"><span>💡</span> Luzes On</button>
                <button class="tv-btn" onclick="sendQuickAction('control_lights', {action: 'off'})"><span>🌙</span> Luzes Off</button>
                <button class="tv-btn" onclick="sendQuickAction('find_phone', {action: 'ring'})"><span>📱</span> Celular</button>
            </div>
        </div>
    </main>

    <script>
        const responseBox = document.getElementById('response-box');
        const tvResponseBox = document.getElementById('tv-response-box');
        const pttBtn = document.getElementById('ptt-btn');
        const connText = document.getElementById('conn-text');

        let currentRequestId = "";

        function switchTab(tabId) {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            document.getElementById('tab-' + tabId).classList.add('active');
            event.target.classList.add('active');

            if (tabId === 'network') {
                loadNetworkInfo();
                loadPairedDevices();
            }
        }

        function getAuthHeader() {
            const token = localStorage.getItem('aton_device_token') || "";
            return token ? { 'Authorization': 'Bearer ' + token } : {};
        }

        let availableVoices = [];
        function initVoices() {
            if ('speechSynthesis' in window) {
                availableVoices = window.speechSynthesis.getVoices();
            }
        }
        if ('speechSynthesis' in window) {
            initVoices();
            window.speechSynthesis.onvoiceschanged = initVoices;
        }

        function speakReply(text) {
            if (!('speechSynthesis' in window) || !text) return;
            try {
                window.speechSynthesis.cancel();
                const utterance = new SpeechSynthesisUtterance(text);
                utterance.lang = 'pt-BR';
                utterance.rate = 1.05;
                if (!availableVoices.length) initVoices();
                const ptVoice = availableVoices.find(v => v.lang.toLowerCase().includes('pt'));
                if (ptVoice) utterance.voice = ptVoice;
                window.speechSynthesis.speak(utterance);
            } catch (e) {
                console.warn("Speech synthesis notice:", e);
            }
        }

        async function sendCommand(payload) {
            responseBox.innerText = "Processando comando...";
            tvResponseBox.innerText = "Processando comando...";
            if ('speechSynthesis' in window && window.speechSynthesis.paused) {
                window.speechSynthesis.resume();
            }
            try {
                const headers = Object.assign({ 'Content-Type': 'application/json' }, getAuthHeader());
                const res = await fetch('/api/command', {
                    method: 'POST',
                    headers: headers,
                    body: JSON.stringify(payload)
                });
                const data = await res.json();

                if (res.status === 401 || res.status === 403) {
                    const msg = data.error || data.message || "Acesso não autorizado. Por favor, faça o pareamento do dispositivo.";
                    responseBox.innerText = msg;
                    tvResponseBox.innerText = msg;
                    speakReply(msg);
                    return;
                }

                const reply = data.message || "Comando executado com sucesso, senhor.";
                responseBox.innerText = reply;
                tvResponseBox.innerText = reply;
                speakReply(reply);
            } catch (err) {
                const errStr = "Erro de conexão com o ATON: " + err;
                responseBox.innerText = errStr;
                tvResponseBox.innerText = errStr;
            }
        }

        function sendQuickAction(toolName, args) {
            sendCommand({ tool_name: toolName, tool_args: args });
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
                try { recognition.start(); } catch(e) { recognition.stop(); }
            });
        } else {
            pttBtn.addEventListener('click', () => {
                const text = prompt("Digite seu comando para o Aton:");
                if (text) sendCommand({ command: text });
            });
        }

        // Network Information and Pairing Operations
        async function loadNetworkInfo() {
            try {
                const res = await fetch('/api/network/interfaces');
                const data = await res.json();
                let html = `<b>IP Principal:</b> ${data.primary_ip}:${data.port}<br>`;
                html += `<b>Interfaces de Rede Ativas:</b><br>`;
                data.interfaces.forEach(iface => {
                    if (iface.is_up && !iface.is_loopback) {
                        html += `• ${iface.interface_name} (${iface.type}): <code>${iface.ip_address}</code><br>`;
                    }
                });
                document.getElementById('host-network-info').innerHTML = html;
                connText.innerText = `Online (${data.primary_ip})`;
            } catch (e) {
                document.getElementById('host-network-info').innerText = "Erro ao carregar interfaces: " + e;
            }
        }

        async function requestDevicePairing() {
            const name = document.getElementById('dev-name').value || "Dispositivo Web";
            const type = document.getElementById('dev-type').value;

            try {
                const res = await fetch('/api/pair/request', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ device_name: name, device_type: type })
                });
                const data = await res.json();
                currentRequestId = data.request_id;
                document.getElementById('pin-verification-box').style.display = 'block';

                // Display PIN if returned (or prompt user)
                if (data.pin_code) {
                    document.getElementById('pin-input').value = data.pin_code;
                    alert(`Código PIN gerado pelo ATON: ${data.pin_code}\\n\\nClique em 'Validar PIN e Conectar' para finalizar o pareamento.`);
                }
            } catch (e) {
                alert("Erro ao solicitar pareamento: " + e);
            }
        }

        async function confirmDevicePairing() {
            const pin = document.getElementById('pin-input').value;
            if (!pin || !currentRequestId) {
                alert("Por favor, informe o PIN gerado.");
                return;
            }

            try {
                const res = await fetch('/api/pair/confirm', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ request_id: currentRequestId, pin_code: pin })
                });
                const data = await res.json();
                if (data.token) {
                    localStorage.setItem('aton_device_token', data.token);
                    alert(`✅ Dispositivo pareado com sucesso!\\nPermissões concedidas: ${data.permissions.join(', ')}`);
                    document.getElementById('pin-verification-box').style.display = 'none';
                    loadPairedDevices();
                } else {
                    alert("Erro ao validar PIN: " + (data.error || "Código incorreto"));
                }
            } catch (e) {
                alert("Erro ao confirmar pareamento: " + e);
            }
        }

        async function loadPairedDevices() {
            try {
                const res = await fetch('/api/network/devices', { headers: getAuthHeader() });
                const data = await res.json();
                const container = document.getElementById('paired-devices-list');

                if (!data.paired_devices || data.paired_devices.length === 0) {
                    container.innerHTML = "<i>Nenhum dispositivo externo pareado no momento.</i>";
                    return;
                }

                let html = "";
                data.paired_devices.forEach(dev => {
                    const isRevoked = dev.status === 'revoked';
                    html += `
                        <div class="device-item">
                            <div class="device-info">
                                <span class="device-name">${dev.device_name} [${dev.device_type.toUpperCase()}]</span>
                                <span class="device-sub">IP: ${dev.last_ip} | Permissões: ${dev.permissions.join(', ')} | Status: ${dev.status}</span>
                            </div>
                            <div>
                                ${!isRevoked ? `<button class="btn-danger" onclick="revokeDevice('${dev.device_id}')">Revogar</button>` : `<span style="color: var(--danger); font-size: 12px;">Revogado</span>`}
                            </div>
                        </div>
                    `;
                });
                container.innerHTML = html;
            } catch (e) {
                document.getElementById('paired-devices-list').innerText = "Erro ao carregar dispositivos: " + e;
            }
        }

        async function revokeDevice(deviceId) {
            if (!confirm("Tem certeza que deseja revogar o acesso deste dispositivo?")) return;
            try {
                const res = await fetch('/api/devices/revoke', {
                    method: 'POST',
                    headers: Object.assign({ 'Content-Type': 'application/json' }, getAuthHeader()),
                    body: JSON.stringify({ device_id: deviceId })
                });
                const data = await res.json();
                alert(data.message || "Acesso revogado.");
                loadPairedDevices();
            } catch (e) {
                alert("Erro ao revogar: " + e);
            }
        }

        async function scanNetwork() {
            const subnet = document.getElementById('subnet-input').value.trim();
            const resultsBox = document.getElementById('scan-results');
            resultsBox.innerText = "Buscando instâncias ATON na rede...";

            try {
                const res = await fetch('/api/network/scan', {
                    method: 'POST',
                    headers: Object.assign({ 'Content-Type': 'application/json' }, getAuthHeader()),
                    body: JSON.stringify({ subnet: subnet || null })
                });
                const data = await res.json();
                if (!data.found_services || data.found_services.length === 0) {
                    resultsBox.innerText = "Nenhum outro serviço ATON compatível encontrado na rede.";
                    return;
                }

                let html = `<b>Encontrados (${data.found_services.length}):</b><br>`;
                data.found_services.forEach(s => {
                    html += `• ${s.service_name} @ <code>${s.primary_ip}:${s.port}</code> (${s.discovery_method})<br>`;
                });
                resultsBox.innerHTML = html;
            } catch (e) {
                resultsBox.innerText = "Erro ao escanear rede: " + e;
            }
        }

        // Initial setup
        loadNetworkInfo();
    </script>
</body>
</html>
"""


class MobileGatewayServer:
    """Lightweight async HTTP server for remote mobile, car, TV, and authorized network device access (Phase 3 & 11)."""

    def __init__(
        self,
        assistant: Any = None,
        host: str = "0.0.0.0",
        port: int = 8443,
        api_token: str = "",
        device_manager: Optional[DeviceManager] = None,
        network_discovery: Optional[NetworkDiscovery] = None,
    ):
        self.assistant = assistant
        self.host = host
        self.port = port
        self.api_token = api_token
        self.device_manager = device_manager or DeviceManager()
        self.network_discovery = network_discovery or NetworkDiscovery()
        self._server: Optional[asyncio.Server] = None
        self._is_running = False

    async def start(self) -> bool:
        """Start the background async HTTP server and mDNS broadcast."""
        if self._is_running:
            return True

        try:
            self._server = await asyncio.start_server(
                self._handle_client,
                self.host,
                self.port,
            )
            self._is_running = True
            primary_ip = self.network_discovery.get_primary_ip()
            logger.info(f"📱 ATON Gateway online em http://{self.host}:{self.port} (IP Local: http://{primary_ip}:{self.port})")

            # Start local network mDNS discovery announcement
            if settings.network_discovery_enabled:
                await self.network_discovery.async_start_broadcasting(
                    port=self.port,
                    service_name="ATON-Host",
                    device_type="desktop",
                )

            return True
        except Exception as exc:
            logger.error(f"Erro ao iniciar ATON Gateway na porta {self.port}: {exc}")
            self._is_running = False
            return False

    async def stop(self) -> None:
        """Stop the background gateway server and mDNS broadcast cleanly."""
        if not self._is_running or self._server is None:
            return

        # Stop mDNS announcement
        await self.network_discovery.async_stop_broadcasting()

        self._server.close()
        await self._server.wait_closed()
        self._server = None
        self._is_running = False
        logger.info("ATON Gateway finalizado com sucesso.")

    def _is_authorized(self, headers: Dict[str, str], query_params: Dict[str, str]) -> bool:
        """Verify legacy master API token if configured (compatibility with Phase 3 tests)."""
        if not self.api_token:
            return True
        auth_header = headers.get("authorization", "")
        if auth_header.startswith("Bearer ") and auth_header[7:].strip() == self.api_token:
            return True
        if query_params.get("token") == self.api_token:
            return True
        return False

    def _extract_token(self, headers: Dict[str, str], query_params: Dict[str, str]) -> str:
        """Extract bearer token from headers or query params."""
        auth_header = headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:].strip()
        return query_params.get("token", "").strip()

    def _is_client_authorized(
        self,
        token: str,
        client_ip: str,
        required_permission: Optional[str] = None,
    ) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """Verify device authorization against DeviceManager or master API token."""
        # 1. Master global API token configured in .env (Full Admin access)
        if self.api_token and token == self.api_token:
            return True, {"device_name": "Master Admin", "permissions": ["all"]}, "OK"

        # 2. Paired device token validation with granular permissions
        if token and token.startswith("aton_"):
            return self.device_manager.validate_token(
                token=token,
                required_permission=required_permission,
                client_ip=client_ip,
            )

        # 3. Localhost requests on 127.0.0.1 when no master token is required
        if client_ip in ("127.0.0.1", "::1") and not self.api_token:
            return True, {"device_name": "Host Localhost", "permissions": ["all"]}, "OK"

        return False, None, "Acesso não autorizado. Dispositivo não pareado."


    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Process incoming HTTP requests from mobile client, TV, or network nodes."""
        client_ip = "127.0.0.1"
        try:
            peer = writer.get_extra_info("peername")
            if peer and isinstance(peer, (tuple, list)) and len(peer) > 0:
                client_ip = str(peer[0])

            # Read HTTP request header
            data = await reader.read(8192)
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

            # Handle CORS preflight
            if method == "OPTIONS":
                self._send_response(writer, 200, "application/json", "{}")
                return

            token = self._extract_token(headers, query_params)

            # Enforce master token check on API routes when server is configured with api_token
            if self.api_token and not self._is_authorized(headers, query_params):
                if not (token.startswith("aton_") or path.startswith("/api/pair/") or path in ("/", "/mobile", "/index.html", "/tv", "/network")):
                    self._send_response(writer, 401, "application/json", json.dumps({"error": "Unauthorized"}))
                    return

            # Public Route 1: Status API (Used for mDNS, Ping and Discovery)
            if method == "GET" and path == "/api/status":
                state_val = getattr(self.assistant, "state", "running")
                if hasattr(state_val, "value"):
                    state_val = state_val.value
                resp_data = {
                    "status": "online",
                    "assistant_name": "Aton",
                    "version": "1.0.0",
                    "state": str(state_val),
                    "device_type": "desktop",
                    "tools_count": len(ALL_ATON_TOOLS),
                }
                self._send_response(writer, 200, "application/json", json.dumps(resp_data))

            # Public Route 2: Network Interfaces & Host IPs
            elif method == "GET" and path == "/api/network/interfaces":
                interfaces = self.network_discovery.get_local_interfaces()
                primary_ip = self.network_discovery.get_primary_ip()
                self._send_response(
                    writer,
                    200,
                    "application/json",
                    json.dumps({
                        "primary_ip": primary_ip,
                        "port": self.port,
                        "interfaces": interfaces,
                    }),
                )

            # Public Route 3: Request New Device Pairing (Generates one-time PIN)
            elif method == "POST" and path == "/api/pair/request":
                try:
                    payload = json.loads(body) if body else {}
                except Exception:
                    payload = {}

                device_name = payload.get("device_name", "Dispositivo Desconhecido")
                device_type = payload.get("device_type", "mobile")
                perms = payload.get("requested_permissions", ["commands", "audio"])

                pairing_info = self.device_manager.request_pairing(
                    client_ip=client_ip,
                    device_name=device_name,
                    device_type=device_type,
                    requested_permissions=perms,
                )

                # Play chime on host if available to notify user
                if self.assistant and getattr(self.assistant, "player", None):
                    try:
                        self.assistant.player.play_wake_chime()
                    except Exception:
                        pass

                self._send_response(writer, 200, "application/json", json.dumps(pairing_info))

            # Public Route 4: Confirm Device Pairing with PIN (Returns permanent bearer token)
            elif method == "POST" and path == "/api/pair/confirm":
                try:
                    payload = json.loads(body) if body else {}
                except Exception:
                    payload = {}

                req_id = payload.get("request_id", "")
                pin = payload.get("pin_code", "")
                auth_result = self.device_manager.confirm_pairing(request_id=req_id, pin_code=pin)

                if auth_result:
                    self._send_response(writer, 200, "application/json", json.dumps(auth_result))
                else:
                    self._send_response(
                        writer,
                        401,
                        "application/json",
                        json.dumps({"error": "PIN incorreto ou solicitação de pareamento expirada."}),
                    )

            # Route 5: List Authorized & Pending Devices
            elif method == "GET" and path == "/api/network/devices":
                paired = self.device_manager.list_devices()
                pending = self.device_manager.get_pending_requests()
                self._send_response(
                    writer,
                    200,
                    "application/json",
                    json.dumps({"paired_devices": paired, "pending_requests": pending}),
                )

            # Route 6: Scan Local Network for ATON Instances
            elif method == "POST" and path == "/api/network/scan":
                try:
                    payload = json.loads(body) if body else {}
                except Exception:
                    payload = {}
                subnet = payload.get("subnet")

                if subnet:
                    found = await self.network_discovery.probe_subnet_range(subnet)
                else:
                    loop = asyncio.get_running_loop()
                    found = await loop.run_in_executor(None, self.network_discovery.discover_mdns_services, 2.0)

                self._send_response(writer, 200, "application/json", json.dumps({"found_services": found}))

            # Route 7: Revoke Authorized Device
            elif method == "POST" and path == "/api/devices/revoke":
                try:
                    payload = json.loads(body) if body else {}
                except Exception:
                    payload = {}
                target_id = payload.get("device_id", "")
                revoked = self.device_manager.revoke_device(target_id)
                self._send_response(
                    writer,
                    200,
                    "application/json",
                    json.dumps({"status": "success" if revoked else "not_found"}),
                )

            # Protected Route 8: Command Execution API
            elif method == "POST" and path == "/api/command":
                try:
                    payload = json.loads(body) if body else {}
                except Exception:
                    payload = {}

                tool_name = payload.get("tool_name", "")
                tool_args = payload.get("tool_args", {})
                command_text = payload.get("command", "")

                # Determine required permission for the specified tool
                required_perm = TOOL_PERMISSION_MAP.get(tool_name, "commands")

                # Validate authorization and granular permissions
                is_auth, dev_info, err_msg = self._is_client_authorized(
                    token=token,
                    client_ip=client_ip,
                    required_permission=required_perm,
                )

                if not is_auth:
                    logger.warning(f"🚫 Acesso negado para IP {client_ip} na ferramenta '{tool_name}': {err_msg}")
                    self._send_response(writer, 403, "application/json", json.dumps({"status": "error", "message": err_msg}))
                    return

                result: Dict[str, Any] = {}
                if tool_name:
                    logger.info(f"📱 Remote command from {dev_info.get('device_name', client_ip)}: {tool_name}({tool_args})")
                    result = dispatch_tool(tool_name, tool_args)
                elif command_text:
                    logger.info(f"📱 Remote voice command from {dev_info.get('device_name', client_ip)}: '{command_text}'")
                    result = self._process_text_command(command_text)
                else:
                    result = {"status": "error", "message": "Nenhum comando ou ferramenta especificada."}

                # Audio feedback on Host PC if assistant is active
                if self.assistant and hasattr(self.assistant, "player"):
                    try:
                        self.assistant.player.play_wake_chime()
                    except Exception:
                        pass

                self._send_response(writer, 200, "application/json", json.dumps(result))

            # Route 9: Mobile & TV Web UI HTML
            elif method == "GET" and path in ("/", "/mobile", "/index.html", "/network", "/tv", "/pair"):
                self._send_response(writer, 200, "text/html; charset=utf-8", MOBILE_UI_HTML)

            else:
                self._send_response(writer, 404, "application/json", json.dumps({"error": "Not Found"}))

        except Exception as exc:
            logger.error(f"Error handling Gateway request: {exc}")
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

    def _ask_conversational_ai(self, prompt: str) -> str:
        """Generate an intelligent natural language response via Second Brain Q&A or Gemini."""
        # 1. Try Second Brain
        try:
            from src.tools.second_brain_tools import perguntar_ao_cerebro
            sb_res = perguntar_ao_cerebro(prompt)
            if sb_res and sb_res.get("status") == "success" and sb_res.get("resposta") and sb_res.get("status") != "not_found":
                return sb_res["resposta"]
        except Exception:
            pass

        # 2. Try Gemini Flash directly
        if settings.gemini_api_key:
            try:
                from google import genai
                client = genai.Client(api_key=settings.gemini_api_key)
                sys_prompt = (
                    "Você é o Aton, um assistente pessoal inteligente inspirado no JARVIS. "
                    "Responda em Português do Brasil de forma concisa, elegante e prestativa para ser ouvida por voz "
                    "(1 a 3 frases, sem markdown pesado)."
                )
                resp = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=f"{sys_prompt}\n\nComando/Pergunta: {prompt}",
                )
                if resp and resp.text:
                    return resp.text.strip()
            except Exception as e:
                logger.debug(f"Gemini conversational fallback notice: {e}")

        return f"Comando '{prompt}' recebido e processado, senhor."

    def _process_text_command(self, text: str) -> Dict[str, Any]:
        """Process natural language commands from mobile HUD, TV, and remote clients."""
        lower = text.lower().strip()
        clean = re.sub(r'[^\w\s]', '', lower).strip()

        # 1. Greetings, Wake Word Calls & Presence Inquiries
        wake_tokens = {
            "aton", "áton", "atón", "ola", "olá", "oi", "opa", "alo", "alô",
            "esta ai", "está aí", "ta ai", "tá aí", "acorde", "bom dia", "boa tarde", "boa noite"
        }
        words = set(clean.split())
        if clean in wake_tokens or (words & {"aton", "áton", "atón"} and len(words) <= 3):
            if self.assistant and hasattr(self.assistant, "player"):
                try:
                    self.assistant.player.play_greeting()
                except Exception:
                    pass
            return {
                "status": "success",
                "message": "Olá! Estou online e ouvindo, senhor. Como posso ajudar?",
            }

        if clean in ("quem e voce", "quem é você", "quem te criou", "qual seu nome"):
            return {
                "status": "success",
                "message": "Eu sou o Aton, seu assistente pessoal inteligente. Como posso ser útil agora, senhor?",
            }

        # 2. Explicit Web Search
        if any(k in lower for k in ("pesquise no google", "pesquise sobre", "procure na web", "procure no google", "busca no google", "pesquisar")):
            query = re.sub(r'^(pesquise|pesquisar|procure|busque)\s+(no google|na web|sobre|por)?\s*', '', lower).strip()
            return dispatch_tool("web_search", {"query": query or text})

        # 3. Navigation & Maps
        if "rota" in lower or "como chego" in lower or "ir para" in lower:
            dest = lower.replace("trace uma rota para", "").replace("trace rota para", "").replace("ir para", "").strip()
            return dispatch_tool("navigate_to", {"destination": dest or "Centro"})
        elif "posto" in lower or "gasolina" in lower:
            return dispatch_tool("find_places_nearby", {"place_type": "posto de gasolina"})

        # 4. Smart TV
        elif "tv" in lower and ("mudo" in lower or "mutar" in lower):
            return dispatch_tool("control_tv_volume", {"action": "mute"})
        elif "tv" in lower and ("pause" in lower or "pausar" in lower):
            return dispatch_tool("control_tv_media", {"action": "pause"})

        # 5. Lights & Plugs
        elif "luz" in lower and ("apagar" in lower or "desligar" in lower):
            return dispatch_tool("control_lights", {"action": "off"})
        elif "luz" in lower and ("acender" in lower or "ligar" in lower):
            return dispatch_tool("control_lights", {"action": "on"})
        elif "celular" in lower and ("onde" in lower or "tocar" in lower or "achar" in lower):
            return dispatch_tool("find_phone", {"action": "ring"})

        # 6. Google Calendar
        elif "agenda" in lower or "compromisso" in lower or "o que tenho" in lower:
            return dispatch_tool("get_calendar_events", {"time_min": "hoje"})

        # 7. Gmail
        elif "email" in lower or "e-mail" in lower or "correio" in lower:
            return dispatch_tool("list_unread_emails", {"max_results": 5})

        # 8. Google Tasks
        elif "tarefa" in lower or "lembrete" in lower or "pendênci" in lower or "pendenci" in lower:
            return dispatch_tool("list_tasks", {"show_completed": False})

        # 9. Daily Briefing
        elif "resumo" in lower or "briefing" in lower or "bom dia" in lower:
            return dispatch_tool("get_daily_briefing", {})

        # 10. System Telemetry & Audio
        elif "status do pc" in lower or "desempenho" in lower or "como está o pc" in lower:
            return dispatch_tool("get_system_telemetry", {"metric": "all"})
        elif "volume" in lower and "pc" in lower:
            match = re.search(r'\b(\d{1,3})\b', lower)
            vol_val = int(match.group(1)) if match else 50
            return dispatch_tool("set_system_volume", {"level": vol_val})

        # 11. Network & Devices
        elif "dispositivos" in lower or "rede" in lower or "ip" in lower:
            return dispatch_tool("list_network_devices", {})

        # 12. Conversational AI fallback via Second Brain / Gemini
        ai_reply = self._ask_conversational_ai(text)
        return {"status": "success", "message": ai_reply}

    def _send_response(
        self,
        writer: asyncio.StreamWriter,
        status_code: int,
        content_type: str,
        body: str,
    ) -> None:
        """Write formatted HTTP response headers and body with CORS support."""
        body_bytes = body.encode("utf-8")
        status_text = {
            200: "OK",
            401: "Unauthorized",
            403: "Forbidden",
            404: "Not Found",
            500: "Internal Server Error",
        }.get(status_code, "OK")

        response_header = (
            f"HTTP/1.1 {status_code} {status_text}\r\n"
            f"Content-Type: {content_type}\r\n"
            f"Content-Length: {len(body_bytes)}\r\n"
            f"Access-Control-Allow-Origin: *\r\n"
            f"Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n"
            f"Access-Control-Allow-Headers: Content-Type, Authorization\r\n"
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
