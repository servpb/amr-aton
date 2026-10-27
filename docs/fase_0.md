# Documentação: Fase 0 - Fundação & Cérebro Local (Voz em Tempo Real)

## 1. Visão Geral e Objetivos
A **Fase 0** estabeleceu os alicerces fundamentais do assistente **Aton**, implementando a comunicação bidirecional por voz em tempo real através do microfone e dos alto-falantes no ambiente Windows, sem a necessidade de interface gráfica web pesada.

O foco central foi atingir latência ultrabaixa, voz natural em Português do Brasil (pt-BR) com o modelo Aoede do Gemini Live, e operação com **custo zero** de infraestrutura.

---

## 2. Componentes e Módulos Implementados

### A. Configuração e Fundação (`src/config.py`)
- Gerenciamento unificado de variáveis de ambiente com Pydantic Settings e validação de tipos.
- Arquivo `.env.example` com instruções de obtenção de chave gratuita no Google AI Studio.
- Script executável rápido `run.bat` para PowerShell / CMD do Windows.
- Documentado em [docs/config_and_foundation.md](file:///c:/xampp/htdocs/amr/docs/config_and_foundation.md).

### B. Motor de Áudio em Tempo Real (`src/audio/`)
- **Gerenciador de Dispositivos (`src/audio/device_manager.py`):** Detecção automática de dispositivos de entrada e saída no Windows via `sounddevice`.
- **Reprodutor PCM de Baixa Latência (`src/audio/player.py`):** Reprodução de áudio em 24kHz com fila assíncrona, bipes harmônicos senoidais sintetizados (Wake Chime em C5/G5 e Sleep Chime em G5/C5) e proteção anti-eco acústico (`is_playing`).
- **Capturador de Microfone (`src/audio/recorder.py`):** Leitura de blocos de áudio de 80ms em 16kHz e descarte de buffer (`flush()`).
- Documentado em [docs/audio_engine.md](file:///c:/xampp/htdocs/amr/docs/audio_engine.md).

### C. Palavra-Chave Offline ("Aton") e Push-to-Talk (`src/audio/`)
- **Detector Wake Word Local (`src/audio/wake_word.py`):** Detecção 100% offline, ultraleve e sem custo de API com cálculo de energia RMS e cooldown contra falsos positivos.
- **Push-to-Talk (`src/audio/push_to_talk.py`):** Acionamento manual por teclado para ambientes com ruído.
- Documentado em [docs/wake_word.md](file:///c:/xampp/htdocs/amr/docs/wake_word.md).

### D. Cliente Gemini Live Bidirecional (`src/core/live_client.py`)
- Conexão streaming WebSocket em tempo real utilizando o SDK oficial `google-genai`.
- Formato MIME com taxa de amostragem explícita `audio/pcm;rate=16000` via `send_realtime_input`.
- Laço persistente `while self._is_connected:` permitindo conversação contínua por múltiplos turnos sem desconexão.
- Saudação local instantânea gravada em PCM 24kHz (`src/audio/assets/greeting_aoede.pcm`) com latência zero.
- Documentado em [docs/gemini_live_client.md](file:///c:/xampp/htdocs/amr/docs/gemini_live_client.md).

### E. Orquestrador do Loop Principal (`src/core/assistant.py` e `src/main.py`)
- Máquina de estados conversacional (`SLEEPING` -> `WAKING` -> `CONVERSING` -> `SHUTDOWN`).
- Timeout inteligente de silêncio e supressão de eco acústico.
- Documentado em [docs/main_loop_and_orchestrator.md](file:///c:/xampp/htdocs/amr/docs/main_loop_and_orchestrator.md).

---

## 3. Critérios de Pronto Atingidos (100% Concluído ✅)
- Chamar *"Aton"* no microfone e o assistente responder instantaneamente *"Sim, senhor?"*.
- Manter conversa contínua por voz natural em português sem precisar repetir o nome a cada réplica.
- Assistente retornar ao estado de repouso silencioso após timeout de inatividade.
