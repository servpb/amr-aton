# Catálogo Oficial de Módulos Implementados do Aton

> **Data de Publicação:** 27 de Outubro de 2026  
> **Versão do Sistema:** 0.8.0  
> **Status Geral:** 23 Módulos Operacionais • 49 Ferramentas Ativas • 174 Testes Aprovados (100%)  
> **Ambiente:** Windows 11 Nativo (Python 3.11+) • Google Gemini Live (Voz Aoede) • Supabase PostgreSQL (pgvector)  

---

## 1. Visão Geral e Identidade do Sistema

O **Aton** é um assistente pessoal inteligente, executivo e operacional de alta performance, operado prioritariamente por voz bidirecional em tempo real com áudio streaming de ultrabaixa latência (WebSockets PCM 16/24kHz), inspirado na arquitetura conceitual do J.A.R.V.I.S. e batizado como **Aton**.

### Pilares Fundamentais:
1. **Operação Headless por Voz Nativa:** Reside na bandeja do Windows em segundo plano, acionado por Wake Word offline local (*"Aton"*) ou atalho de teclado global (*Push-to-Talk*), dispensando interfaces gráficas pesadas.
2. **Duas Camadas Desacopladas:** A camada de voz responde verbalmente de imediato (*"Já estou providenciando, senhor"*), enquanto tarefas complexas de automação, visão e nuvem rodam em segundo plano de forma não bloqueante.
3. **Custo Zero Inicial:** Prioriza camadas gratuitas (Google AI Studio Free Tier, Supabase Free Tier com pgvector, VPN Tailscale a custo zero e automações locais nativas do Windows).
4. **Segundo Cérebro Permanente:** Persistência relacional e vetorial de preferências, projetos, clientes CRM, tarefas e histórico no Supabase com sincronização para SQLite local contra contingências offline.

---

## 2. Diagrama de Arquitetura em Três Camadas

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

## 3. Catálogo Detalhado dos 23 Módulos Implementados

### Módulo 01: Fundação & Configurações Base
- **Código-Fonte:** [`src/config.py`](file:///c:/xampp/htdocs/amr/src/config.py)
- **Documentação:** [`docs/config_and_foundation.md`](file:///c:/xampp/htdocs/amr/docs/config_and_foundation.md)
- **Objetivo:** Gestão centralizada de configurações e variáveis de ambiente via `pydantic-settings`, garantindo tipagem estrita, carregamento de `.env` e valores padrão resilientes.
- **Principais Recursos:**
  - Gerenciamento seguro de chaves de API (`GEMINI_API_KEY`, `SUPABASE_KEY`).
  - Configurações de áudio (taxa de amostragem 16kHz, timeouts de conversação, índices de dispositivos).
  - Configuração do modelo de visão (`GEMINI_VISION_MODEL`).

### Módulo 02: Motor de Áudio em Tempo Real
- **Código-Fonte:** [`src/audio/device_manager.py`](file:///c:/xampp/htdocs/amr/src/audio/device_manager.py), [`player.py`](file:///c:/xampp/htdocs/amr/src/audio/player.py), [`recorder.py`](file:///c:/xampp/htdocs/amr/src/audio/recorder.py)
- **Documentação:** [`docs/audio_engine.md`](file:///c:/xampp/htdocs/amr/docs/audio_engine.md)
- **Objetivo:** Captura de microfone com VAD (*Voice Activity Detection*), reprodução instantânea de áudio PCM bruto (16kHz / 24kHz) e supressão de eco acústico.
- **Principais Recursos:**
  - `Acoustic Echo Suppression`: Silencia o microfone durante a fala do assistente para evitar auto-interrupção.
  - Reprodução instantânea de saudação nativa Aoede em PCM (`src/audio/assets/greeting_aoede.pcm`).
  - Bipes harmônicos senoidais sintetizados localmente para confirmações táteis de áudio.

### Módulo 03: Wake Word Offline & Push-to-Talk
- **Código-Fonte:** [`src/audio/wake_word.py`](file:///c:/xampp/htdocs/amr/src/audio/wake_word.py), [`src/audio/push_to_talk.py`](file:///c:/xampp/htdocs/amr/src/audio/push_to_talk.py)
- **Documentação:** [`docs/wake_word.md`](file:///c:/xampp/htdocs/amr/docs/wake_word.md)
- **Objetivo:** Ativação local sem custo de nuvem por palavra-chave (*"Aton"*) e atalho global físico para ambientes barulhentos.
- **Principais Recursos:**
  - Detecção contínua offline ultraleve (< 2% CPU).
  - Cooldown anti-gatilho duplo.
  - Push-to-Talk global com captura assíncrona.

### Módulo 04: Cliente Gemini Live (Voz Realtime)
- **Código-Fonte:** [`src/core/live_client.py`](file:///c:/xampp/htdocs/amr/src/core/live_client.py), [`src/core/prompts.py`](file:///c:/xampp/htdocs/amr/src/core/prompts.py)
- **Documentação:** [`docs/gemini_live_client.md`](file:///c:/xampp/htdocs/amr/docs/gemini_live_client.md)
- **Objetivo:** Gerenciar a conexão WebSocket bidirecional em tempo real com o modelo multimodal de voz do Google.
- **Principais Recursos:**
  - Envio de áudio via `send_realtime_input(audio=...)` com MIME `audio/pcm;rate=16000`.
  - Supressão de Ping Timeout (Erro 1011) via configuração personalizada no cliente `websockets`.
  - Suporte completo a conversação contínua de múltiplos turnos com respostas na voz Aoede.

### Módulo 05: Orquestrador do Loop Principal
- **Código-Fonte:** [`src/core/assistant.py`](file:///c:/xampp/htdocs/amr/src/core/assistant.py), [`src/main.py`](file:///c:/xampp/htdocs/amr/src/main.py)
- **Documentação:** [`docs/main_loop_and_orchestrator.md`](file:///c:/xampp/htdocs/amr/docs/main_loop_and_orchestrator.md)
- **Objetivo:** Máquina de estados finitos que orquestra os ciclos de vida de repouso, audição, processamento de ferramentas e fala.
- **Principais Recursos:**
  - Transições limpas entre estados (`Sleeping`, `Listening`, `Speaking`, `Processing`).
  - Execução desacoplada de ferramentas em threads de segundo plano sem travar a voz.
  - Sincronização em tempo real com o ícone da bandeja do Windows.

### Módulo 06: Gerenciador de Aplicativos Windows
- **Código-Fonte:** [`src/tools/windows_apps.py`](file:///c:/xampp/htdocs/amr/src/tools/windows_apps.py)
- **Documentação:** [`docs/windows_apps.md`](file:///c:/xampp/htdocs/amr/docs/windows_apps.md)
- **Objetivo:** Gerenciar softwares, janelas e processos em execução no ambiente Windows.
- **Principais Recursos:**
  - Fechamento inteligente em 3 camadas:
    1. Fechamento de janela ativa via mensagem Win32 `WM_CLOSE`.
    2. Fechamento pontual por título de janela via `pygetwindow` (ex: abas do YouTube).
    3. Encerramento de processos via `taskkill` com retry forçado automático (`/F`) para navegadores como Edge e Chrome.
  - Abertura de executáveis e esquemas de URI (`ms-settings:`, URLs diretas).

### Módulo 07: Navegação Web e Pesquisa
- **Código-Fonte:** [`src/tools/web_browser.py`](file:///c:/xampp/htdocs/amr/src/tools/web_browser.py)
- **Documentação:** [`docs/web_browser.md`](file:///c:/xampp/htdocs/amr/docs/web_browser.md)
- **Objetivo:** Automação de pesquisa na internet, busca de vídeos no YouTube e navegação via Playwright e navegador nativo.

### Módulo 08: Controle de Smart TV na Rede Wi-Fi
- **Código-Fonte:** [`src/tools/smart_tv.py`](file:///c:/xampp/htdocs/amr/src/tools/smart_tv.py)
- **Documentação:** [`docs/smart_tv.md`](file:///c:/xampp/htdocs/amr/docs/smart_tv.md)
- **Objetivo:** Integração local via rede Wi-Fi com televisores inteligentes (Samsung Tizen, LG webOS, Sony Bravia, Roku).
- **Principais Recursos:** Controle de volume, mutação, reprodução multimídia, ligar/desligar (Wake-on-LAN) e abertura de apps (YouTube, Netflix, Prime Video).

### Módulo 09: Localizador de Celular Android
- **Código-Fonte:** [`src/tools/phone_finder.py`](file:///c:/xampp/htdocs/amr/src/tools/phone_finder.py)
- **Documentação:** [`docs/phone_finder.md`](file:///c:/xampp/htdocs/amr/docs/phone_finder.md)
- **Objetivo:** Disparar alarme sonoro em volume máximo no smartphone Android conectado na rede Wi-Fi através de Webhooks locais (MacroDroid, Tasker, KDE Connect, Termux) e ADB sem fio.

### Módulo 10: Iluminação & Tomadas Inteligentes (IoT)
- **Código-Fonte:** [`src/tools/smart_lights.py`](file:///c:/xampp/htdocs/amr/src/tools/smart_lights.py)
- **Documentação:** [`docs/smart_lights.md`](file:///c:/xampp/htdocs/amr/docs/smart_lights.md)
- **Objetivo:** Controle direto de iluminação e plugs inteligentes na rede local com protocolos abertos e sem latência de servidores externos (Philips Hue, Shelly, Tasmota, Sonoff, Yeelight, Tuya).

### Módulo 11: Navegação, Rotas e GPS (Google Maps)
- **Código-Fonte:** [`src/tools/google_maps.py`](file:///c:/xampp/htdocs/amr/src/tools/google_maps.py)
- **Documentação:** [`docs/google_maps.md`](file:///c:/xampp/htdocs/amr/docs/google_maps.md)
- **Objetivo:** Cálculo de rotas, estimativa de trânsito em tempo real, localização de pontos de interesse próximos e acionamento de navegação ponto a ponto via Android Intents a custo zero.

### Módulo 12: Mobile Gateway & Acesso Remoto Seguro
- **Código-Fonte:** [`src/integrations/mobile_gateway.py`](file:///c:/xampp/htdocs/amr/src/integrations/mobile_gateway.py)
- **Documentação:** [`docs/tailscale_and_mobile_gateway.md`](file:///c:/xampp/htdocs/amr/docs/tailscale_and_mobile_gateway.md)
- **Objetivo:** Servidor assíncrono ultraleve HTTP/JSON com endpoints `/api/status` e `/api/command`, Painel Web HUD PWA para smartphone e integração de rede segura ponto a ponto via VPN Tailscale a custo zero.

### Módulo 13: Google Calendar (Agenda)
- **Código-Fonte:** [`src/tools/google_calendar.py`](file:///c:/xampp/htdocs/amr/src/tools/google_calendar.py)
- **Documentação:** [`docs/google_calendar.md`](file:///c:/xampp/htdocs/amr/docs/google_calendar.md)
- **Objetivo:** Consulta e agendamento de compromissos com autenticação OAuth2 Google Workspace e parser avançado de datas e horários em linguagem natural em português.

### Módulo 14: Gmail (Somente Leitura)
- **Código-Fonte:** [`src/tools/gmail.py`](file:///c:/xampp/htdocs/amr/src/tools/gmail.py)
- **Documentação:** [`docs/gmail.md`](file:///c:/xampp/htdocs/amr/docs/gmail.md)
- **Objetivo:** Leitura segura de e-mails prioritários da caixa de entrada com escopo estrito `gmail.readonly`, decodificador base64url e sanitizador de tags HTML.

### Módulo 15: Google Tasks (Tarefas)
- **Código-Fonte:** [`src/tools/google_tasks.py`](file:///c:/xampp/htdocs/amr/src/tools/google_tasks.py)
- **Documentação:** [`docs/google_tasks.md`](file:///c:/xampp/htdocs/amr/docs/google_tasks.md)
- **Objetivo:** Gestão de afazeres, listagem de pendências, criação de novas tarefas e conclusão inteligente por título em linguagem natural.

### Módulo 16: Memória Semântica Local e Briefing Diário
- **Código-Fonte:** [`src/core/memory.py`](file:///c:/xampp/htdocs/amr/src/core/memory.py)
- **Documentação:** [`docs/memory.md`](file:///c:/xampp/htdocs/amr/docs/memory.md)
- **Objetivo:** Persistência relacional local em SQLite (`amr_memory.db`) para regras e preferências do usuário, além de rotina de Resumo Executivo Diário que sintetiza Agenda, Tarefas e E-mails em áudio.

### Módulo 17: Telemetria de Hardware Windows
- **Código-Fonte:** [`src/tools/system_telemetry.py`](file:///c:/xampp/htdocs/amr/src/tools/system_telemetry.py)
- **Documentação:** [`docs/system_telemetry.md`](file:///c:/xampp/htdocs/amr/docs/system_telemetry.md)
- **Objetivo:** Monitoramento e diagnóstico em tempo real dos recursos físicos da máquina (CPU, Memória RAM, Espaço em Disco e Bateria) com respostas em linguagem natural via `psutil`.

### Módulo 18: Controle de Volume e Multimídia do Windows
- **Código-Fonte:** [`src/tools/system_audio.py`](file:///c:/xampp/htdocs/amr/src/tools/system_audio.py)
- **Documentação:** [`docs/system_audio.md`](file:///c:/xampp/htdocs/amr/docs/system_audio.md)
- **Objetivo:** Controle de nível percentual do volume master do Windows via `pycaw`, mutação de áudio e despacho de eventos multimídia virtuais Win32 (play/pause, próxima, anterior, parar).

### Módulo 19: Residente Windows (System Tray)
- **Código-Fonte:** [`src/integrations/system_tray.py`](file:///c:/xampp/htdocs/amr/src/integrations/system_tray.py)
- **Documentação:** [`docs/system_tray.md`](file:///c:/xampp/htdocs/amr/docs/system_tray.md)
- **Objetivo:** Presença silenciosa na bandeja do sistema operacional (área de notificação) via `pystray`, com ícone dinâmico em 4 cores refletindo os estados do Aton e menu de contexto com atalhos operacionais.

### Módulo 20: Automação de Digitação & Documentos
- **Código-Fonte:** [`src/tools/desktop_automation.py`](file:///c:/xampp/htdocs/amr/src/tools/desktop_automation.py)
- **Documentação:** [`docs/desktop_automation.md`](file:///c:/xampp/htdocs/amr/docs/desktop_automation.md)
- **Objetivo:** Digitação de texto com preservação universal de caracteres especiais via clipboard (`pyperclip`), atalhos de teclado do Windows, foco dinâmico de janelas e criação direta de documentos Word (`.docx`) e planilhas Excel (`.xlsx`).

### Módulo 21: Segundo Cérebro Permanente (Supabase + pgvector)
- **Código-Fonte:** [`src/core/second_brain.py`](file:///c:/xampp/htdocs/amr/src/core/second_brain.py), [`src/tools/second_brain_tools.py`](file:///c:/xampp/htdocs/amr/src/tools/second_brain_tools.py)
- **Documentação:** [`docs/second_brain.md`](file:///c:/xampp/htdocs/amr/docs/second_brain.md) e [`docs/supabase_setup_guide.md`](file:///c:/xampp/htdocs/amr/docs/supabase_setup_guide.md)
- **Objetivo:** Nuvem de conhecimento relacional e vetorial no Supabase PostgreSQL 15, com busca híbrida semântica (HNSW 768d com embeddings Google `gemini-embedding-001` + Full-Text Search pt-BR), 18 tabelas relacionais com RLS total e fallback local para SQLite.

### Módulo 22: Autoconhecimento do Aton & Changelog
- **Código-Fonte:** [`scripts/sincronizar_autoconhecimento.py`](file:///c:/xampp/htdocs/amr/scripts/sincronizar_autoconhecimento.py), [`src/tools/second_brain_tools.py`](file:///c:/xampp/htdocs/amr/src/tools/second_brain_tools.py)
- **Documentação:** [`docs/aton_self_knowledge.md`](file:///c:/xampp/htdocs/amr/docs/aton_self_knowledge.md)
- **Objetivo:** Base de dados factual introspectada sobre a identidade real do Aton, criador (dono de agência digital e do canal Alta Restauração), arquitetura e changelog histórico de versões, com regra de honestidade absoluta (*"Isso não está registrado no meu autoconhecimento"*) e recusa estrita de senhas.

### Módulo 23: Percepção Visual e Interação com a Tela
- **Código-Fonte:** [`src/core/screen_perceiver.py`](file:///c:/xampp/htdocs/amr/src/core/screen_perceiver.py), [`src/tools/screen_perception.py`](file:///c:/xampp/htdocs/amr/src/tools/screen_perception.py)
- **Documentação:** [`docs/screen_perception.md`](file:///c:/xampp/htdocs/amr/docs/screen_perception.md)
- **Objetivo:** Visão computacional multimodal sob demanda com detecção de janelas ativas Win32, otimização JPEG para ultra-baixa latência, envio via SDK `google-genai` com cadeia resiliente de modelos Flash (`gemini-3.5-flash`, `gemini-3.6-flash`, etc.), detecção de Bounding Boxes normalizadas e interação física na interface por mouse e teclado.

### Módulo 24: Rede & Dispositivos Autorizados
- **Código-Fonte:** [`src/core/network_discovery.py`](file:///c:/xampp/htdocs/amr/src/core/network_discovery.py), [`src/core/device_manager.py`](file:///c:/xampp/htdocs/amr/src/core/device_manager.py), [`src/tools/network_tools.py`](file:///c:/xampp/htdocs/amr/src/tools/network_tools.py), [`src/integrations/mobile_gateway.py`](file:///c:/xampp/htdocs/amr/src/integrations/mobile_gateway.py)
- **Documentação:** [`docs/network_devices.md`](file:///c:/xampp/htdocs/amr/docs/network_devices.md)
- **Objetivo:** Arquitetura Hub/Anfitrião para conectar múltiplos dispositivos (celulares, TVs, outros computadores) com Zero Confiança Local, anúncio e busca mDNS/DNS-SD com `AsyncZeroconf`, pareamento seguro por PIN de uso único de 6 dígitos (5 min), tokens Bearer SHA-256 e permissões granulares (`commands`, `audio`, `screen`, `files`, `control`).

---

## 4. Tabela Completa das 49 Ferramentas Operacionais Ativas

A tabela abaixo lista todas as 49 ferramentas integradas no catálogo `ALL_ATON_TOOLS` expostas ao modelo de voz do Gemini Live:

| # | Nome da Ferramenta (*Tool*) | Módulo Responsável | Parâmetros Principais | Exemplo de Comando Falado |
| :-: | :--- | :--- | :--- | :--- |
| **01** | `open_application` | Windows Apps | `app_name`, `args` | *"Aton, abra a calculadora."* |
| **02** | `close_application` | Windows Apps | `app_name` | *"Aton, feche o YouTube."* |
| **03** | `list_running_applications` | Windows Apps | *(sem parâmetros)* | *"Aton, quais programas estão abertos?"* |
| **04** | `web_search` | Web Browser | `query` | *"Aton, pesquise as últimas notícias de tecnologia."* |
| **05** | `search_youtube` | Web Browser | `query` | *"Aton, pesquise vídeos de restauração automotiva no YouTube."* |
| **06** | `open_webpage` | Web Browser | `url` | *"Aton, abra a página do GitHub."* |
| **07** | `control_tv_volume` | Smart TV | `action` ('up'/'down'/'set'/'mute'), `value` | *"Aton, aumente o volume da TV."* |
| **08** | `control_tv_media` | Smart TV | `action` ('play'/'pause'/'stop'/'next') | *"Aton, pause o vídeo na TV."* |
| **09** | `control_tv_power` | Smart TV | `action` ('on'/'off') | *"Aton, ligue a TV da sala."* |
| **10** | `launch_tv_app` | Smart TV | `app_name` ('youtube'/'netflix') | *"Aton, abra a Netflix na televisão."* |
| **11** | `get_tv_status` | Smart TV | *(sem parâmetros)* | *"Aton, a TV da sala está ligada?"* |
| **12** | `find_phone` | Phone Finder | *(sem parâmetros)* | *"Aton, onde está meu celular?"* |
| **13** | `control_lights` | Smart Lights | `room`, `state`, `brightness`, `color` | *"Aton, acenda as luzes do escritório em 80%."* |
| **14** | `control_smart_plug` | Smart Lights | `device_name`, `state` ('on'/'off') | *"Aton, desligue a tomada do ventilador."* |
| **15** | `navigate_to` | Google Maps | `destination`, `avoid_tolls` | *"Aton, inicie a rota para o aeroporto sem pedágios."* |
| **16** | `find_places_nearby` | Google Maps | `place_type`, `radius_km` | *"Aton, encontre postos de gasolina próximos."* |
| **17** | `estimate_traffic_route` | Google Maps | `origin`, `destination` | *"Aton, como está o trânsito até o centro?"* |
| **18** | `get_calendar_events` | Google Calendar | `time_min`, `time_max`, `max_results` | *"Aton, o que eu tenho agendado para hoje?"* |
| **19** | `create_calendar_event` | Google Calendar | `summary`, `start_time`, `duration_minutes` | *"Aton, marque uma reunião amanhã às 14 horas."* |
| **20** | `list_unread_emails` | Gmail | `max_results` | *"Aton, tenho algum e-mail importante não lido?"* |
| **21** | `get_email_content` | Gmail | `email_id` | *"Aton, leia o conteúdo do último e-mail do cliente."* |
| **22** | `list_tasks` | Google Tasks | `status`, `task_list_id` | *"Aton, quais tarefas estão pendentes na minha lista?"* |
| **23** | `create_task` | Google Tasks | `title`, `notes`, `due_date` | *"Aton, adicione a tarefa de revisar o contrato até sexta."* |
| **24** | `complete_task` | Google Tasks | `task_title`, `task_id` | *"Aton, marque a tarefa de envio de orçamento como concluída."* |
| **25** | `remember_fact` | Memória Local | `category`, `key`, `content` | *"Aton, lembre-se de que eu prefiro exportar vídeos em 4K."* |
| **26** | `recall_memory` | Memória Local | `query`, `category` | *"Aton, o que você lembra sobre minhas preferências de vídeo?"* |
| **27** | `forget_memory` | Memória Local | `key` | *"Aton, esqueça a minha preferência de resolução de vídeo."* |
| **28** | `get_daily_briefing` | Memória Local | *(sem parâmetros)* | *"Aton, qual é o meu resumo diário de hoje?"* |
| **29** | `get_system_telemetry` | Telemetria | `metric` ('all'/'cpu'/'memory'/'disk'/'battery') | *"Aton, como está o uso da minha memória RAM?"* |
| **30** | `set_system_volume` | Áudio Windows | `level` (0 a 100), `mute` | *"Aton, ajuste o volume do computador para 40%."* |
| **31** | `control_system_media` | Áudio Windows | `action` ('play'/'pause'/'next'/'prev') | *"Aton, pause a música que está tocando."* |
| **32** | `type_text_in_active_window`| Automação Desktop | `text`, `app_name`, `press_enter` | *"Aton, digite o resumo da reunião no bloco de notas."* |
| **33** | `create_and_open_document` | Automação Desktop | `doc_type` ('word'/'excel'), `title`, `content` | *"Aton, crie uma planilha de controle financeiro."* |
| **34** | `send_keyboard_shortcut` | Automação Desktop | `shortcut` (ex: 'ctrl+s', 'alt+tab') | *"Aton, salve o arquivo com control s."* |
| **35** | `focus_application_window` | Automação Desktop | `app_name` | *"Aton, traga a janela do VS Code para frente."* |
| **36** | `salvar_memoria` | Segundo Cérebro | `tipo`, `titulo`, `conteudo`, `tags` | *"Aton, guarde no meu segundo cérebro esta ideia de conteúdo."* |
| **37** | `buscar_memoria` | Segundo Cérebro | `query`, `tipo`, `limite` | *"Aton, busque nas minhas anotações o roteiro do Siena 2006."* |
| **38** | `perguntar_ao_cerebro` | Segundo Cérebro | `pergunta` | *"Aton, consulte meu segundo cérebro sobre o cliente XYZ."* |
| **39** | `criar_cliente_cerebro` | Segundo Cérebro | `nome`, `empresa`, `status`, `email` | *"Aton, cadastre um novo cliente chamado Roberto da Empresa Alfa."* |
| **40** | `criar_tarefa_cerebro` | Segundo Cérebro | `titulo`, `prioridade`, `data_limite` | *"Aton, crie uma tarefa no segundo cérebro para gravar o vídeo."* |
| **41** | `resumo_geral_cerebro` | Segundo Cérebro | *(sem parâmetros)* | *"Aton, faça um resumo do meu segundo cérebro."* |
| **42** | `atualizar_memoria_cerebro`| Segundo Cérebro | `id_registro`, `novos_dados` | *(Atualização pontual de registros na nuvem)* |
| **43** | `esquecer_memoria_cerebro` | Segundo Cérebro | `id_registro` | *(Remoção lógica com soft delete)* |
| **44** | `consultar_autoconhecimento`| Autoconhecimento | `pergunta_ou_topico`, `categoria` | *"Aton, quais tecnologias você utiliza e quem é seu criador?"* |
| **45** | `descrever_tela` | Visão de Tela | `alvo` ('janela_ativa'/'fullscreen'), `detalhe` | *"Aton, o que você está vendo na minha tela?"* |
| **46** | `ler_conteudo_tela` | Visão de Tela | `alvo`, `trecho` | *"Aton, leia o texto que está visível nesta janela."* |
| **47** | `localizar_e_clicar_elemento`| Visão de Tela | `descricao_elemento`, `tipo_clique` | *"Aton, clique no botão Salvar na tela."* |
| **48** | `preencher_campo_na_tela` | Visão de Tela | `descricao_campo`, `texto`, `alvo` | *"Aton, preencha o campo de busca com 'relatório'."* |
| **49** | `rolar_tela` | Visão de Tela | `direcao` ('baixo'/'cima'), `quantidade` | *"Aton, role a página um pouco para baixo."* |
| **50** | `get_network_info` | Rede & Dispositivos | *(sem parâmetros)* | *"Aton, qual é o seu endereço IP na rede?"* |
| **51** | `list_network_devices` | Rede & Dispositivos | *(sem parâmetros)* | *"Aton, quais dispositivos estão conectados ao assistente?"* |
| **52** | `revoke_network_device` | Rede & Dispositivos | `device_identifier` (nome ou UUID) | *"Aton, desconecte o Galaxy S24."* |
| **53** | `scan_network_devices` | Rede & Dispositivos | `subnet_range` (opcional) | *"Aton, procure instâncias do Aton na rede local."* |

---

## 5. Estrutura de Banco de Dados

### 5.1. Nuvem: Supabase PostgreSQL 15 com `pgvector`
- **Extensão Vetorial:** `pgvector` com índice HNSW para vetores de 768 dimensões gerados pelo modelo `gemini-embedding-001`.
- **Busca Híbrida:** Função `buscar_memoria_hibrida` unindo busca por cosseno vetorial e Full-Text Search em Português (`portuguese`).
- **Segurança:** RLS (*Row Level Security*) ativo em 100% das tabelas.
- **Tabelas Relacionais (18 tabelas + Autoconhecimento):**
  1. `perfil_criador`: Identidade e preferências essenciais do criador.
  2. `clientes_crm`: Clientes da agência digital, contatos e status comercial.
  3. `projetos`: Projetos da agência e do canal Alta Restauração.
  4. `tarefas`: Afazeres com prioridades, prazos e vínculos com projetos.
  5. `agenda_eventos`: Compromissos espelhados e históricos.
  6. `conhecimento_tecnico`: Tutoriais, comandos e documentações operacionais.
  7. `notas_rapidas`: Ideias rápidas e anotações espontâneas.
  8. `interacoes_historico`: Logs resumidos de conversas com o assistente.
  9. `modulos_sistema`: Catálogo de módulos do Aton registrados no banco.
  10. `metadados_sistema`: Configurações dinâmicas de sistema e flags.
  11. `auditoria_modificacoes`: Logs de alterações e auditoria de ações.
  12. `aton_autoconhecimento`: Base factual introspectada sobre a identidade e limites do Aton.
  13. `aton_changelog`: Histórico de versões e migrações estruturadas.

### 5.2. Local: SQLite de Alta Resiliência (`amr_memory.db`)
- Tabela `memories` indexada por chave e categoria para acesso offline com latência inferior a 1ms.

---

## 6. Variáveis de Ambiente e Configurações (`.env`)

```ini
# Google AI Studio / Gemini
GEMINI_API_KEY=sua_chave_gemini_aqui
GEMINI_LIVE_MODEL=gemini-2.0-flash-exp
GEMINI_VISION_MODEL=gemini-3.5-flash
GEMINI_VOICE_NAME=Aoede

# Wake Word e Áudio Local
AMR_WAKE_WORD=aton
AUDIO_SAMPLE_RATE=16000
CONVERSATION_TIMEOUT_SECONDS=12

# Segundo Cérebro (Supabase Cloud)
SUPABASE_URL=https://seu-projeto.supabase.co
SUPABASE_KEY=sua_chave_service_role_aqui
EMBEDDING_MODEL=gemini-embedding-001

# Dispositivos Inteligentes e IoT (Opcionais)
SMART_TV_IP=192.168.1.150
SMART_TV_BRAND=auto
ANDROID_PHONE_IP=192.168.1.120
ANDROID_PHONE_PORT=8080

# Gateway Mobile e Tailscale
GATEWAY_ENABLED=true
GATEWAY_PORT=8443
GATEWAY_API_TOKEN=seu_token_secreto_aqui
```

---

## 7. Suíte de Testes Automatizados (174 Testes Aprovados)

O ecossistema do Aton conta com uma cobertura rigorosa de testes unitários e de integração mockados, garantindo estabilidade contínua sem depender de chamadas externas de rede ou periféricos durante o build:

| Arquivo de Teste | Módulo Testado | Status |
| :--- | :--- | :---: |
| [`tests/test_config.py`](file:///c:/xampp/htdocs/amr/tests/test_config.py) | Configurações Pydantic e Variáveis `.env` | **Aprovado** |
| [`tests/test_audio.py`](file:///c:/xampp/htdocs/amr/tests/test_audio.py) | Dispositivos de Áudio, Player PCM e Gravador VAD | **Aprovado** |
| [`tests/test_wake_word.py`](file:///c:/xampp/htdocs/amr/tests/test_wake_word.py) | Wake Word Detector e Push-to-Talk | **Aprovado** |
| [`tests/test_live_client.py`](file:///c:/xampp/htdocs/amr/tests/test_live_client.py) | WebSocket Gemini Live e Protocolo Realtime | **Aprovado** |
| [`tests/test_assistant.py`](file:///c:/xampp/htdocs/amr/tests/test_assistant.py) | Orquestrador de Estados e Despacho Assíncrono | **Aprovado** |
| [`tests/test_windows_apps.py`](file:///c:/xampp/htdocs/amr/tests/test_windows_apps.py) | Janelas, Apps, Taskkill com /F e Fallbacks | **Aprovado** |
| [`tests/test_web_browser.py`](file:///c:/xampp/htdocs/amr/tests/test_web_browser.py) | Navegação Web e Automação Playwright | **Aprovado** |
| [`tests/test_smart_tv.py`](file:///c:/xampp/htdocs/amr/tests/test_smart_tv.py) | Smart TVs (Samsung, LG, Sony, Roku, DIAL) | **Aprovado** |
| [`tests/test_phone_finder.py`](file:///c:/xampp/htdocs/amr/tests/test_phone_finder.py) | Localizador de Celular e Webhooks | **Aprovado** |
| [`tests/test_smart_lights.py`](file:///c:/xampp/htdocs/amr/tests/test_smart_lights.py) | Iluminação e Plugs Inteligentes (IoT) | **Aprovado** |
| [`tests/test_google_maps.py`](file:///c:/xampp/htdocs/amr/tests/test_google_maps.py) | Rotas, Trânsito e Android Intents de GPS | **Aprovado** |
| [`tests/test_mobile_gateway.py`](file:///c:/xampp/htdocs/amr/tests/test_mobile_gateway.py) | Endpoints REST, HUD Mobile e Autenticação | **Aprovado** |
| [`tests/test_google_calendar.py`](file:///c:/xampp/htdocs/amr/tests/test_google_calendar.py) | Google Calendar e Parser Natural pt-BR | **Aprovado** |
| [`tests/test_gmail.py`](file:///c:/xampp/htdocs/amr/tests/test_gmail.py) | Leitura de E-mails e Decodificação HTML | **Aprovado** |
| [`tests/test_google_tasks.py`](file:///c:/xampp/htdocs/amr/tests/test_google_tasks.py) | Listagem, Criação e Baixa de Tarefas | **Aprovado** |
| [`tests/test_memory.py`](file:///c:/xampp/htdocs/amr/tests/test_memory.py) | Memória Local SQLite e Daily Briefing | **Aprovado** |
| [`tests/test_system_telemetry.py`](file:///c:/xampp/htdocs/amr/tests/test_system_telemetry.py) | Diagnóstico de Hardware CPU/RAM/Disco/Bateria | **Aprovado** |
| [`tests/test_system_audio.py`](file:///c:/xampp/htdocs/amr/tests/test_system_audio.py) | Volume Master e Eventos Multimídia Win32 | **Aprovado** |
| [`tests/test_system_tray.py`](file:///c:/xampp/htdocs/amr/tests/test_system_tray.py) | Ícone na Bandeja e Menus de Ciclo de Vida | **Aprovado** |
| [`tests/test_desktop_automation.py`](file:///c:/xampp/htdocs/amr/tests/test_desktop_automation.py) | Digitação Universal, Office Word/Excel e Atalhos | **Aprovado** |
| [`tests/test_second_brain.py`](file:///c:/xampp/htdocs/amr/tests/test_second_brain.py) | Segundo Cérebro Supabase, pgvector e Fallback | **Aprovado** |
| [`tests/test_autoconhecimento.py`](file:///c:/xampp/htdocs/amr/tests/test_autoconhecimento.py) | Autoidentidade, Regra de Honestidade e Cache | **Aprovado** |
| [`tests/test_screen_perception.py`](file:///c:/xampp/htdocs/amr/tests/test_screen_perception.py) | Visão Multimodal, Bounding Boxes e Fallback Flash | **Aprovado** |

---

## 8. Como Executar o Aton

1. **Inicialização Rápida no Windows:**
   - Dê um duplo clique no arquivo [`run.bat`](file:///c:/xampp/htdocs/amr/run.bat) ou execute no PowerShell:
     ```powershell
     .\.venv\Scripts\python.exe src/main.py
     ```
2. **Ativação por Voz:**
   - Diga claramente no microfone: *"Aton"*.
   - O assistente responderá de imediato com a voz Aoede e emitirá o bipe de escuta.
3. **Push-to-Talk de Emergência:**
   - Pressione o atalho global configurado para ativar o canal de voz mesmo em ambientes com ruído.
4. **Painel Mobile HUD:**
   - Acesse via navegador local ou VPN Tailscale no smartphone: `http://localhost:8443`
