# Documentação: Fase 2 - Automação Residencial & IoT na Rede Local (Wi-Fi)

## 1. Visão Geral e Objetivos
A **Fase 2** transformou o **Aton** em um hub inteligente de automação doméstica capaz de controlar aparelhos e dispositivos conectados à mesma rede Wi-Fi local sem depender de servidores em nuvem lentos ou pagos, garantindo privacidade, latência quase nula e custo zero.

---

## 2. Módulos e Ferramentas Desenvolvidas

### A. Controle Universal de Smart TVs (`src/tools/smart_tv.py`)
- **Objetivo:** Ligar, pausar, alterar volume, mutar e alternar aplicativos em Smart TVs na rede Wi-Fi (Samsung Tizen, LG webOS, Android TV / Chromecast).
- **Protocolos Utilizados:** Wake-on-LAN (WoL) via pacotes mágicos UDP, protocolo universal DIAL (UPnP SSDP na porta 8008) e WebSockets REST.
- **Ferramentas (*Tool Calling* para Gemini Live):**
  - `control_tv_volume(action, level)`: mute, unmute, aumentar e diminuir volume.
  - `control_tv_media(action)`: play, pause, stop.
  - `control_tv_power(action)`: on (via WoL) ou off.
  - `launch_tv_app(app_name)`: YouTube, Netflix, Prime Video, Spotify.
  - `get_tv_status()`: verifica se a TV está online e conectada.
- **Documentado em:** [docs/smart_tv.md](file:///c:/xampp/htdocs/amr/docs/smart_tv.md).

### B. Localizador de Celular Android (`src/tools/phone_finder.py`)
- **Objetivo:** Disparar um alarme sonoro de alto volume no smartphone Android conectado ao Wi-Fi quando o usuário perguntar onde o celular está.
- **Protocolos Suportados:** Webhook HTTP local (MacroDroid, Tasker, KDE Connect, Termux) e ADB sem fio (Android Debug Bridge por porta 5555).
- **Ferramentas (*Tool Calling* para Gemini Live):**
  - `find_phone(action)`: dispara ou interrompe o alerta sonoro no smartphone.
- **Documentado em:** [docs/phone_finder.md](file:///c:/xampp/htdocs/amr/docs/phone_finder.md).

### C. Iluminação e Tomadas Inteligentes (`src/tools/smart_lights.py`)
- **Objetivo:** Controlar lâmpadas, fitas LED e plugs inteligentes compatíveis com protocolos locais (Philips Hue, Shelly, Tasmota, Sonoff, Yeelight, Tuya).
- **Ferramentas (*Tool Calling* para Gemini Live):**
  - `control_lights(action, brightness, color, room)`: on, off, toggle, brilho e cor.
  - `control_smart_plug(action, device_id)`: liga ou desliga tomadas inteligentes.
- **Documentado em:** [docs/smart_lights.md](file:///c:/xampp/htdocs/amr/docs/smart_lights.md).

---

## 3. Critérios de Pronto Atingidos (100% Concluído ✅)
- Dizer *"Aton, coloque a TV no mudo, apague a luz do quarto e onde está meu celular?"* e todas as ações responderem em tempo real pela rede local com confirmações sonoras naturais.
