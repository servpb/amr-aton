# Catálogo Geral de Módulos Implementados — ATON

Este documento serve como o **índice mestre e inventário oficial** de todos os módulos, subsistemas, bibliotecas e ferramentas implementadas no assistente pessoal **Aton**.

---

## 1. Visão Geral da Arquitetura em Três Camadas

```
┌────────────────────────────────────────────────────────────────────────┐
│                        CAMADA DE VOZ (Tempo Real)                     │
│  - Wake Word Offline "Aton" (openWakeWord / Porcupine)                │
│  - Push-to-Talk de Emergência                                          │
│  - Gemini Live API Bidirecional (WebSockets PCM 16/24kHz - Voz Aoede) │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Tool Calling Desacoplado
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                      CAMADA DE TRABALHO (Worker Local)                 │
│  - Automação Windows, Janelas, Digitação, Office                      │
│  - Percepção Visual e Compreensão de Tela Multimodal (Gemini Flash)    │
│  - Automação Web (Playwright) e Pesquisa na Web                        │
│  - IoT Local (Smart TV, Luzes/Tomadas Wi-Fi, Localizador de Celular)   │
│  - Navegação e GPS (Google Maps e Android Intents)                     │
│  - Produtividade Google Workspace (Calendar, Gmail, Tasks)             │
│  - Telemetria de Hardware, Volume Master e Ícone System Tray           │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                    CAMADA DE MEMÓRIA (Segundo Cérebro)                 │
│  - Persistência em Nuvem: Supabase PostgreSQL 15 + RLS                 │
│  - Busca Híbrida: Vetorial HNSW 768d + Full-Text Search pt-BR          │
│  - Memória Local de Contingência: SQLite (amr_memory.db)               │
│  - Base de Autoconhecimento Introspectada e Changelog de Versões       │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Inventário Completo de Módulos Implementados

| # | Módulo | Código-Fonte | Ferramentas / Recursos | Testes Automatizados | Documentação Dedicada |
| :-: | :--- | :--- | :--- | :--- | :--- |
| **01** | **Fundação e Configurações Base** | [`src/config.py`](file:///c:/xampp/htdocs/amr/src/config.py) | Gerenciamento de `.env`, Pydantic Settings, chaves de API e portas | `tests/test_config.py` | [docs/config_and_foundation.md](file:///c:/xampp/htdocs/amr/docs/config_and_foundation.md) |
| **02** | **Motor de Áudio em Tempo Real** | [`src/audio/`](file:///c:/xampp/htdocs/amr/src/audio) | Gravação de microfone, reprodução PCM, VAD, supressão acústica e bipes harmônicos | `tests/test_audio.py` | [docs/audio_engine.md](file:///c:/xampp/htdocs/amr/docs/audio_engine.md) |
| **03** | **Wake Word Offline e Push-to-Talk** | [`src/audio/wake_word.py`](file:///c:/xampp/htdocs/amr/src/audio/wake_word.py), [`src/audio/push_to_talk.py`](file:///c:/xampp/htdocs/amr/src/audio/push_to_talk.py) | Detecção local contínua de "Aton" a custo zero e atalho global de teclado/mouse | `tests/test_wake_word.py` | [docs/wake_word.md](file:///c:/xampp/htdocs/amr/docs/wake_word.md) |
| **04** | **Cliente Gemini Live API** | [`src/core/live_client.py`](file:///c:/xampp/htdocs/amr/src/core/live_client.py), [`src/core/prompts.py`](file:///c:/xampp/htdocs/amr/src/core/prompts.py) | WebSocket bidirecional em tempo real, streaming de áudio nativo e voz Aoede | `tests/test_live_client.py` | [docs/gemini_live_client.md](file:///c:/xampp/htdocs/amr/docs/gemini_live_client.md) |
| **05** | **Orquestrador do Loop Principal** | [`src/core/assistant.py`](file:///c:/xampp/htdocs/amr/src/core/assistant.py), [`src/main.py`](file:///c:/xampp/htdocs/amr/src/main.py) | Máquina de estados finitos (Sleeping, Listening, Speaking, Processing) | `tests/test_assistant.py` | [docs/main_loop_and_orchestrator.md](file:///c:/xampp/htdocs/amr/docs/main_loop_and_orchestrator.md) |
| **06** | **Gerenciador de Aplicativos Windows** | [`src/tools/windows_apps.py`](file:///c:/xampp/htdocs/amr/src/tools/windows_apps.py) | `open_application`, `close_application`, `list_running_applications` (fechamento inteligente em 3 camadas) | `tests/test_windows_apps.py` | [docs/windows_apps.md](file:///c:/xampp/htdocs/amr/docs/windows_apps.md) |
| **07** | **Navegação Web e Pesquisa** | [`src/tools/web_browser.py`](file:///c:/xampp/htdocs/amr/src/tools/web_browser.py) | `web_search`, `search_youtube`, `open_webpage` (integração Playwright e navegador nativo) | `tests/test_web_browser.py` | [docs/web_browser.md](file:///c:/xampp/htdocs/amr/docs/web_browser.md) |
| **08** | **Controle de Smart TV na Rede Wi-Fi** | [`src/tools/smart_tv.py`](file:///c:/xampp/htdocs/amr/src/tools/smart_tv.py) | `control_tv_volume`, `control_tv_media`, `control_tv_power`, `launch_tv_app`, `get_tv_status` (Samsung, LG, Sony, Roku) | `tests/test_smart_tv.py` | [docs/smart_tv.md](file:///c:/xampp/htdocs/amr/docs/smart_tv.md) |
| **09** | **Localizador de Celular Android** | [`src/tools/phone_finder.py`](file:///c:/xampp/htdocs/amr/src/tools/phone_finder.py) | `find_phone` (Disparo de alarme sonoro em volume máximo via Webhooks / ADB sem fio) | `tests/test_phone_finder.py` | [docs/phone_finder.md](file:///c:/xampp/htdocs/amr/docs/phone_finder.md) |
| **10** | **Iluminação e Tomadas Inteligentes** | [`src/tools/smart_lights.py`](file:///c:/xampp/htdocs/amr/src/tools/smart_lights.py) | `control_lights`, `control_smart_plug` (Philips Hue, Shelly, Tasmota, Sonoff, Yeelight, Tuya) | `tests/test_smart_lights.py` | [docs/smart_lights.md](file:///c:/xampp/htdocs/amr/docs/smart_lights.md) |
| **11** | **Navegação, Rotas e GPS (Google Maps)** | [`src/tools/google_maps.py`](file:///c:/xampp/htdocs/amr/src/tools/google_maps.py) | `navigate_to`, `find_places_nearby`, `estimate_traffic_route` (Android Intents a custo zero) | `tests/test_google_maps.py` | [docs/google_maps.md](file:///c:/xampp/htdocs/amr/docs/google_maps.md) |
| **12** | **Mobile Gateway & Acesso Remoto** | [`src/integrations/mobile_gateway.py`](file:///c:/xampp/htdocs/amr/src/integrations/mobile_gateway.py) | Servidor HTTP REST assíncrono, Painel Web HUD PWA para celular/carro e VPN Tailscale | `tests/test_mobile_gateway.py` | [docs/tailscale_and_mobile_gateway.md](file:///c:/xampp/htdocs/amr/docs/tailscale_and_mobile_gateway.md) |
| **13** | **Google Calendar (Agenda)** | [`src/tools/google_calendar.py`](file:///c:/xampp/htdocs/amr/src/tools/google_calendar.py) | `get_calendar_events`, `create_calendar_event` (parser de datas naturais em português) | `tests/test_google_calendar.py` | [docs/google_calendar.md](file:///c:/xampp/htdocs/amr/docs/google_calendar.md) |
| **14** | **Gmail (Somente Leitura)** | [`src/tools/gmail.py`](file:///c:/xampp/htdocs/amr/src/tools/gmail.py) | `list_unread_emails`, `get_email_content` (escopo seguro readonly e decodificador HTML) | `tests/test_gmail.py` | [docs/gmail.md](file:///c:/xampp/htdocs/amr/docs/gmail.md) |
| **15** | **Google Tasks (Tarefas)** | [`src/tools/google_tasks.py`](file:///c:/xampp/htdocs/amr/src/tools/google_tasks.py) | `list_tasks`, `create_task`, `complete_task` (gestão e baixa de afazeres por voz) | `tests/test_google_tasks.py` | [docs/google_tasks.md](file:///c:/xampp/htdocs/amr/docs/google_tasks.md) |
| **16** | **Memória Semântica Local e Briefing** | [`src/core/memory.py`](file:///c:/xampp/htdocs/amr/src/core/memory.py) | `remember_fact`, `recall_memory`, `forget_memory`, `get_daily_briefing` (SQLite) | `tests/test_memory.py` | [docs/memory.md](file:///c:/xampp/htdocs/amr/docs/memory.md) |
| **17** | **Telemetria de Hardware Windows** | [`src/tools/system_telemetry.py`](file:///c:/xampp/htdocs/amr/src/tools/system_telemetry.py) | `get_system_telemetry` (CPU, Memória RAM, Espaço em Disco e Bateria via `psutil`) | `tests/test_system_telemetry.py` | [docs/system_telemetry.md](file:///c:/xampp/htdocs/amr/docs/system_telemetry.md) |
| **18** | **Controle de Volume e Multimídia** | [`src/tools/system_audio.py`](file:///c:/xampp/htdocs/amr/src/tools/system_audio.py) | `set_system_volume`, `control_system_media` (Volume Master Windows via `pycaw` e teclas Win32) | `tests/test_system_audio.py` | [docs/system_audio.md](file:///c:/xampp/htdocs/amr/docs/system_audio.md) |
| **19** | **Residente Windows (System Tray)** | [`src/integrations/system_tray.py`](file:///c:/xampp/htdocs/amr/src/integrations/system_tray.py) | Presença silenciosa na barra de tarefas, ícone de 4 estados visuais e menu de contexto | `tests/test_system_tray.py` | [docs/system_tray.md](file:///c:/xampp/htdocs/amr/docs/system_tray.md) |
| **20** | **Automação de Digitação & Documentos** | [`src/tools/desktop_automation.py`](file:///c:/xampp/htdocs/amr/src/tools/desktop_automation.py) | `type_text_in_active_window`, `create_and_open_document`, `send_keyboard_shortcut`, `focus_application_window` | `tests/test_desktop_automation.py` | [docs/desktop_automation.md](file:///c:/xampp/htdocs/amr/docs/desktop_automation.md) |
| **21** | **Segundo Cérebro Supabase + pgvector** | [`src/core/second_brain.py`](file:///c:/xampp/htdocs/amr/src/core/second_brain.py), [`src/tools/second_brain_tools.py`](file:///c:/xampp/htdocs/amr/src/tools/second_brain_tools.py) | `salvar_memoria`, `buscar_memoria`, `perguntar_ao_cerebro`, `criar_cliente_cerebro`, `criar_tarefa_cerebro`, `resumo_geral_cerebro` | `tests/test_second_brain.py` | [docs/second_brain.md](file:///c:/xampp/htdocs/amr/docs/second_brain.md) |
| **22** | **Autoconhecimento do Aton e Changelog** | [`scripts/sincronizar_autoconhecimento.py`](file:///c:/xampp/htdocs/amr/scripts/sincronizar_autoconhecimento.py) | `consultar_autoconhecimento` (Base de autoidentidade grounded, regra de honestidade e cache offline) | `tests/test_autoconhecimento.py` | [docs/aton_self_knowledge.md](file:///c:/xampp/htdocs/amr/docs/aton_self_knowledge.md) |
| **23** | **Percepção Visual e Interação com a Tela** | [`src/core/screen_perceiver.py`](file:///c:/xampp/htdocs/amr/src/core/screen_perceiver.py), [`src/tools/screen_perception.py`](file:///c:/xampp/htdocs/amr/src/tools/screen_perception.py) | `descrever_tela`, `ler_conteudo_tela`, `localizar_e_clicar_elemento`, `preencher_campo_na_tela`, `rolar_tela` (Multimodal) | `tests/test_screen_perception.py` | [docs/screen_perception.md](file:///c:/xampp/htdocs/amr/docs/screen_perception.md) |
| **24** | **Rede & Dispositivos Autorizados** | [`src/core/network_discovery.py`](file:///c:/xampp/htdocs/amr/src/core/network_discovery.py), [`src/core/device_manager.py`](file:///c:/xampp/htdocs/amr/src/core/device_manager.py), [`src/tools/network_tools.py`](file:///c:/xampp/htdocs/amr/src/tools/network_tools.py) | `get_network_info`, `list_network_devices`, `revoke_network_device`, `scan_network_devices` (mDNS ZeroConf, Pareamento com PIN 6 dígitos, Permissões Granulares e Modo TV) | `tests/test_network_devices.py` | [docs/network_devices.md](file:///c:/xampp/htdocs/amr/docs/network_devices.md) |
| **25** | **Explicação de Módulos e Capacidades** | [`src/core/module_registry.py`](file:///c:/xampp/htdocs/amr/src/core/module_registry.py), [`src/tools/module_tools.py`](file:///c:/xampp/htdocs/amr/src/tools/module_tools.py) | `listar_modulos`, `detalhar_modulo`, `listar_recursos_pendentes` (Registro dinâmico, classificação honesta de estados, exemplos de comandos e mensagens de voz) | `tests/test_module_registry.py` | [docs/module_explanation.md](file:///c:/xampp/htdocs/amr/docs/module_explanation.md) |
| **26** | **Contexto de Tarefa e Confirmação de Resultados** | [`src/core/task_context.py`](file:///c:/xampp/htdocs/amr/src/core/task_context.py), [`src/tools/task_tools.py`](file:///c:/xampp/htdocs/amr/src/tools/task_tools.py) | `consultar_status_tarefa`, `selecionar_opcao_pendente`, `cancelar_tarefa_atual` (Contrato de evidências, estados de transporte e verificação, descarte de tarefas antigas e cancelamento cooperativo) | `tests/test_task_context.py` | [docs/task_context_and_confirmation.md](file:///c:/xampp/htdocs/amr/docs/task_context_and_confirmation.md) |

---

## 3. Status Atual dos 21 Módulos de Voz do Catálogo (`module_registry.py`)

> Para o detalhamento individual do que está funcionando e do que precisa de configuração nos 21 módulos do catálogo de voz, consulte também [`docs/módulos.md`](file:///c:/xampp/htdocs/amr/docs/módulos.md).

- **✅ Funcionando e Ativos (16 de 21):**
  1. **Controle do Fire TV Stick** (Pareado no IP `192.168.0.7`, modelo `AFTSS`)
  5. **Aplicativos e Janelas do Windows**
  6. **Navegação Web e Pesquisa**
  7. **Automação de Digitação e Documentos**
  8. **Volume e Multimídia do Windows**
  9. **Telemetria e Diagnóstico de Hardware**
  10. **Rede e Dispositivos Autorizados**
  11. **Percepção Visual e Compreensão de Tela**
  13. **Gmail (Somente Leitura)** — Autenticado (`servpb@gmail.com`)
  14. **Google Agenda (Calendar)** — Autenticado (`servpb@gmail.com`, `America/Fortaleza`, 11 ferramentas de voz)
  16. **Rotas e GPS (Google Maps)**
  17. **Timers e Lembretes**
  18. **Segundo Cérebro e Memória Permanente**
  19. **Memória Local e Briefing Diário**
  20. **Inferência Rápida Groq LPU** (`openai/gpt-oss-20b`)
  21. **Planejamento Avançado NVIDIA Nemotron** (`llama-3.1-nemotron-70b-instruct`)

- **⚙️ Não Funcionam Ainda — Precisam de Configuração / Autenticação (4 de 21):**
  - **2. Localizador de Celular:** requer configurar `ANDROID_PHONE_IP` / Webhook no `.env`.
  - **3. Iluminação e Tomadas Inteligentes:** requer configurar `SMART_LIGHTS_BRIDGE_IP` no `.env`.
  - **12. Canais e Vídeos do YouTube:** requer ativar a API no Google Cloud e rodar `.\run.bat youtube-auth`.
  - **15. Google Tarefas (Tasks):** requer ativar a *Google Tasks API* no Google Cloud e autorizar o escopo `tasks`.

- **🚫 Desativado por Design (1 de 21):**
  - **4. Smart TV Convencional:** volume e energia física da TV informam indisponibilidade por segurança (uso via Fire TV Stick).

---

## 4. Resumo Quantitativo

- **Total de Módulos de Voz no Catálogo:** 21 módulos (16 ativos, 4 aguardando configuração, 1 desativado por design)
- **Total de Ferramentas Ativas Expostas ao Gemini Live:** 92 ferramentas operacionais
- **Suíte de Testes Automatizados:** 250+ testes unitários e de integração aprovados
- **Documentação Técnica Individual:** 100% dos módulos documentados na pasta [`docs/`](file:///c:/xampp/htdocs/amr/docs)
