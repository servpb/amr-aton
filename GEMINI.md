# GEMINI.md - Diretrizes do Projeto Aton (Assistente Pessoal)

## 1. Visão Geral do Projeto
O **Aton** é um assistente pessoal inteligente, operado prioritariamente por voz (áudio bidirecional em tempo real, sem necessidade de interface gráfica web pesada), inspirado na arquitetura de assistentes de alta performance como o J.A.R.V.I.S., batizado como "Aton".

O assistente foi desenhado para rodar inicialmente em ambiente **Windows**, com foco no **ecossistema Google** (Google GenAI, Gemini Live, Google Maps, Google Workspace, Google Cloud), começando com custo zero (camadas gratuitas) e preparado para escalar para serviços em nuvem corporativos.

---

## 2. Pilares de Arquitetura

### A. Duas Camadas Desacopladas (Voz Rápida vs. Trabalho Lento)
1. **Camada de Voz (Conversacional / Rápida):**
   - Conexão em tempo real usando **Gemini Live API** (via SDK `google-genai`).
   - Entrada de áudio pelo microfone e saída de voz natural pelo alto-falante.
   - Respostas instantâneas e suporte a interrupção de fala.
   - Ativação por palavra-chave (*Wake Word*) local **"Aton"** (utilizando modelos ultraleves e offline como `openWakeWord`) ou atalho de teclado global (*Push-to-Talk*).
2. **Camada de Trabalho (Worker / Background):**
   - Execução de tarefas em segundo plano (automação de software, navegação web, IoT).
   - O modelo de voz aciona funções assíncronas (*Tool Calling / MCP*), responde imediatamente por áudio (*"Já estou nisso, senhor"*) e a tarefa roda sem congelar a conversa.

### B. Ecossistema Google-First
- **IA e Voz:** Google AI Studio (Gemini Flash e Gemini Live na cota gratuita) -> Migrável para Vertex AI.
- **Navegação & GPS:** Google Maps Platform e Intents nativos no Android.
- **Produtividade:** Google Workspace APIs (Calendar, Gmail, Tasks, Drive).
- **Nuvem Opcional:** Google Cloud Run (com escala para zero instâncias quando ocioso).

### C. Controle Local do Windows
- Acesso nativo a softwares instalados no PC (edição de vídeo/imagem, navegadores, arquivos locais).
- Padrão **MCP (Model Context Protocol)** e bibliotecas especializadas (Playwright, APIs de sistema).

---

## 3. Especificações Detalhadas das Funcionalidades

### A. Operação 100% por Voz (Headless / Estilo Alexa & Jarvis)
- **Sem Interface Web Pesada:** O assistente roda como um processo residente em segundo plano no Windows (opcionalmente com ícone na bandeja do sistema).
- **Palavra-chave Offline ("AMR"):** Detecção local contínua via microfone usando modelo ultraleve offline (0% de custo de API e mínimo consumo de CPU).
- **Modo Conversacional Contínuo:** Uma vez acordado pelo comando *"AMR"*, o canal de áudio permanece ativo durante a interação. O usuário não precisa repetir o nome a cada réplica. O assistente volta a dormir após alguns segundos de silêncio.
- **Push-to-Talk de Emergência:** Atalho configurável no teclado/mouse para ativação imediata sem voz de ativação (ideal para ambientes com barulho ou música).

### B. Controle de Softwares e Sistema no Windows
- **Gerenciamento de Aplicativos:** Capacidade de abrir, fechar, verificar status e trazer para primeiro plano softwares instalados (editores de mídia, navegadores, explorador de arquivos).
- **Automação Web e Tarefas:** Utilização de Playwright para tarefas de navegação web visível ou headless.
- **Automação de Softwares Específicos:** Suporte modular para scripts de automação dos programas que o usuário utiliza (APIs nativas de automação).

### C. Automação Residencial e IoT na Rede Local (Wi-Fi)
- **Smart TVs:** Comunicação direta via rede local com TVs inteligentes (Samsung Tizen, LG webOS, Android TV/Chromecast) para ligar, pausar, alterar volume, mutar e alternar canais/aplicativos.
- **Iluminação e Tomadas:** Integração local com lâmpadas e plugs inteligentes compatíveis (Tuya/Smart Life, Sonoff, Philips Hue, Yeelight) sem latência de servidores externos.
- **Localizador de Celular:** Comando de voz (*"AMR, onde está meu celular?"*) para disparar um alerta sonoro de alto volume no smartphone Android conectado na rede.

### D. Mobilidade, Viagem e Carro (Android + GPS)
- **Integração no Carro:** Funcionamento contínuo pareado com o áudio do carro via Bluetooth ou Android Auto, permitindo operação hands-free no trânsito.
- **GPS e Google Maps:** Disparo de rotas ponto a ponto através de *Android Intents* (`google.navigation:q=...`), cálculo de trânsito em tempo real, desvio de pedágios e localização de postos de combustível na rota.
- **Rede Remota Segura com Tailscale:** Uso de rede privada segura (*Mesh VPN*) para comunicar o celular em trânsito com o computador em casa, sem abrir portas de roteador nem incorrer em custos com servidores.

### E. Evolução da Infraestrutura Google
- **Fase Inicial (Custo Zero):** Google AI Studio (Gemini Flash e Gemini Live), Google Cloud Run com escala para zero instâncias, Google Maps com cota mensal de crédito gratuito.
- **Fase Futura (Escala e Corporativo):** Código desenhado de forma desacoplada para facilitar a migração transparente para Google Cloud Vertex AI e infraestruturas dedicadas quando desejado pelo usuário.

---

## 4. Regras Estritas de Operação e Conduta do Agente

1. **Portão de Aprovação Prévia Obrigatória (Sim / Não):**
   - **NADA** deve ser executado, criado ou modificado sem que o agente apresente previamente o que será feito e aguarde a autorização explícita do usuário (aprovação de "Sim" ou "Não").
   - O agente nunca deve rodar comandos no terminal ou escrever códigos de funcionalidades sem a permissão formal e prévia do usuário.
2. **Registro Contínuo no GEMINI.md:**
   - Tudo o que for aprovado e efetivamente implementado deve ser imediatamente registrado e acrescentado no `GEMINI.md` (na seção de *Histórico de Funcionalidades Implementadas*), mantendo este arquivo sempre atualizado como a fonte única da verdade.
3. **Documentação Modular Obrigatória (`docs/<nome_da_funcao>.md`):**
   - Para cada funcionalidade ou módulo aprovado e implementado, o agente deve obrigatoriamente criar um arquivo individual em `docs/<nome_da_funcao>.md` detalhando o objetivo, como a função funciona, parâmetros, dependências e como testá-la.
4. **Custo Zero Inicial Obrigatório:**
   - Nunca adicione serviços, bibliotecas ou APIs pagas sem aviso e autorização prévia expressa do usuário.
   - Sempre priorize ferramentas gratuitas (AI Studio Free Tier, Cloud Run scale-to-zero, bibliotecas locais offline).
5. **Idioma e Nomenclatura:**
   - **Código, nomes de variáveis, funções, classes e mensagens de commit:** sempre em **inglês**.
   - **Interface com o usuário, respostas do assistente Aton e documentação (`docs/`):** sempre em **Português do Brasil (pt-BR)**.
   - O nome do assistente é exclusivamente **Aton**.
6. **Segurança e Confirmações do Usuário:**
   - **Zero Segredos no Código:** Chaves de API (`GEMINI_API_KEY`, etc.) devem ficar exclusivamente no arquivo `.env` (ignorado pelo `.gitignore`). O `.env.example` deve conter apenas nomes de variáveis e instruções.
   - **Portão de Confirmação para Ações Destrutivas:** Qualquer ação destrutiva ou sensível (excluir arquivos, enviar e-mails, sobrescrever projetos, compras ou pagamentos) exige confirmação verbal explícita do usuário antes da execução.
7. **Qualidade e Estabilidade:**
   - Sempre escreva código modular com tratamento de exceções robusto para dispositivos de áudio e conexões de rede.
   - Manter testes automatizados para as ferramentas do assistente.

---

## 5. Histórico de Funcionalidades Implementadas
*(Esta seção é atualizada continuamente pelo agente à medida que novas funcionalidades são aprovadas e concluídas)*
- [x] **Arquitetura Base e Diretrizes do Assistente AMR:** Documentado no [GEMINI.md](file:///c:/xampp/htdocs/amr/GEMINI.md).
- [x] **Roteiro Estruturado em 6 Fases (Fase 0 a 5):** Documentado no [docs/ROADMAP.md](file:///c:/xampp/htdocs/amr/docs/ROADMAP.md).
- [x] **Fundação e Configurações Base (Fase 0 - Passo 1):** Estrutura de pastas, `.gitignore`, `.env.example`, `pyproject.toml`, `run.bat`, `src/config.py` e `tests/test_config.py`. Documentado em [docs/config_and_foundation.md](file:///c:/xampp/htdocs/amr/docs/config_and_foundation.md) e [docs/SETUP_CHECKLIST.md](file:///c:/xampp/htdocs/amr/docs/SETUP_CHECKLIST.md).
- [x] **Motor de Áudio em Tempo Real (Fase 0 - Passo 2):** Gerenciador de dispositivos Windows (`src/audio/device_manager.py`), reprodutor PCM com bipes harmônicos sintetizados (`src/audio/player.py`), gravador de microfone (`src/audio/recorder.py`) e testes (`tests/test_audio.py`). Documentado em [docs/audio_engine.md](file:///c:/xampp/htdocs/amr/docs/audio_engine.md).
- [x] **Palavra-Chave Offline "AMR" e Push-to-Talk (Fase 0 - Passo 3):** Detector local com cooldown (`src/audio/wake_word.py`), controlador de atalho de emergência (`src/audio/push_to_talk.py`) e testes (`tests/test_wake_word.py`). Documentado em [docs/wake_word.md](file:///c:/xampp/htdocs/amr/docs/wake_word.md).
- [x] **Cliente Gemini Live em Tempo Real (Fase 0 - Passo 4):** Instruções do sistema em português (`src/core/prompts.py`), cliente de streaming WebSocket com SDK `google-genai` (`src/core/live_client.py`) e testes (`tests/test_live_client.py`). Documentado em [docs/gemini_live_client.md](file:///c:/xampp/htdocs/amr/docs/gemini_live_client.md).
- [x] **Orquestrador do Loop Principal e Ponto de Entrada (Fase 0 - Passo 5):** Máquina de estados conversacional (`src/core/assistant.py`), ponto de entrada executável (`src/main.py`) e testes de ciclo de vida (`tests/test_assistant.py`). Documentado em [docs/main_loop_and_orchestrator.md](file:///c:/xampp/htdocs/amr/docs/main_loop_and_orchestrator.md).
- [x] **Saudação Imediata Falada e Sensibilidade Conversacional:** Resposta instantânea por voz em português ao acordar via `send_text_prompt`, redução do limiar de voz ativa para RMS 300 e timeout de 12 segundos. Documentado em [docs/gemini_live_client.md](file:///c:/xampp/htdocs/amr/docs/gemini_live_client.md).
- [x] **Proteção Anti-Eco Acústico (Acoustic Echo Suppression):** Supressão da transmissão do microfone durante a fala do assistente (`is_playing`), evitando que o Aton corte sua própria voz. Documentado em [docs/audio_engine.md](file:///c:/xampp/htdocs/amr/docs/audio_engine.md).
- [x] **Canal de Áudio em Tempo Real via `send_realtime_input`:** Substituição do método legado pelo envio nativo `send_realtime_input(audio=...)`, garantindo que todas as perguntas faladas no microfone cheguem ao modelo do Gemini Live e sejam respondidas por voz. Documentado em [docs/gemini_live_client.md](file:///c:/xampp/htdocs/amr/docs/gemini_live_client.md).
- [x] **Saudação Nativa Instantânea Aoede e Canal Realtime Puro:** Gravação da saudação em PCM 24kHz (`src/audio/assets/greeting_aoede.pcm`) com reprodução instantânea com latência zero via `player.play_greeting()`, mantendo o WebSocket do Gemini Live em modo de áudio 100% puro para conversação contínua. Documentado em [docs/audio_engine.md](file:///c:/xampp/htdocs/amr/docs/audio_engine.md).
- [x] **Estabilidade WebSocket e Supressão de Ping Timeout (Erro 1011):** Desativação do ping timeout desnecessário em `websockets.asyncio.client`, tratamento elegante de desconexões e retorno limpo ao repouso sem poluição de logs. Documentado em [docs/gemini_live_client.md](file:///c:/xampp/htdocs/amr/docs/gemini_live_client.md).
- [x] **Loop Multiturnos Contínuo e MIME com Taxa (`audio/pcm;rate=16000`):** Laço persistente `while self._is_connected:` em `receive_stream()` para manter a recepção de áudio ativa através de todos os turnos de fala, especificação de taxa `rate=16000` no MIME e transcrição falada (`part.text`). Documentado em [docs/gemini_live_client.md](file:///c:/xampp/htdocs/amr/docs/gemini_live_client.md).
- [x] **Isolamento de Eco na Saudação e Descarte de Buffer:** Espera do fim da saudação local antes de iniciar o streaming e descarte de áudio gravado no buffer (`recorder.flush()`). Documentado em [docs/audio_engine.md](file:///c:/xampp/htdocs/amr/docs/audio_engine.md).
- [x] **Gerenciador de Aplicativos e Janelas do Windows (Fase 1 - Passo 1):** Módulo de controle de processos e softwares no Windows (`src/tools/windows_apps.py`), esquemas de *Tool Calling* (`open_application`, `close_application`, `list_running_applications`), fechamento inteligente em 3 camadas (fechamento de janela ativa via `WM_CLOSE`, busca por título de janela/aba via `pygetwindow` para sites como YouTube, e encerramento de processos com fallback forçado `/F` para navegadores multi-processo como Edge e Chrome), integração assíncrona desacoplada em duas camadas sem bloquear o áudio (`src/core/assistant.py` e `src/core/live_client.py`) e suíte de testes (`tests/test_windows_apps.py`). Documentado em [docs/windows_apps.md](file:///c:/xampp/htdocs/amr/docs/windows_apps.md).
- [x] **Navegação Web e Pesquisa Automatizada (Fase 1 - Passo 2):** Módulo de automação web (`src/tools/web_browser.py`), integração com Playwright e navegador nativo, esquemas de *Tool Calling* (`web_search`, `search_youtube`, `open_webpage`), despachante unificado em `src/tools/__init__.py` e testes automatizados (`tests/test_web_browser.py`). Documentado em [docs/web_browser.md](file:///c:/xampp/htdocs/amr/docs/web_browser.md).
- [x] **Controle de Smart TV e Mídia na Rede Wi-Fi (Fase 2 - Passo 1):** Módulo universal para Smart TVs (`src/tools/smart_tv.py`), esquemas de *Tool Calling* (`control_tv_volume`, `control_tv_media`, `control_tv_power`, `launch_tv_app`, `get_tv_status`), suporte a WoL e DIAL, agregação em `ALL_ATON_TOOLS` (11 ferramentas ativas) e testes automatizados (`tests/test_smart_tv.py`). Documentado em [docs/smart_tv.md](file:///c:/xampp/htdocs/amr/docs/smart_tv.md).
- [x] **Localizador de Celular Android na Rede Wi-Fi (Fase 2 - Passo 2):** Módulo de localização sonora (`src/tools/phone_finder.py`), suporte a webhooks locais (MacroDroid, Tasker, KDE Connect, Termux) e ADB sem fio, esquema de *Tool Calling* (`find_phone`) e testes automatizados (`tests/test_phone_finder.py`). Documentado em [docs/phone_finder.md](file:///c:/xampp/htdocs/amr/docs/phone_finder.md).
- [x] **Controle de Iluminação e Tomadas Inteligentes (Fase 2 - Passo 3):** Módulo de controle local de IoT (`src/tools/smart_lights.py`), esquemas de *Tool Calling* (`control_lights`, `control_smart_plug`), suporte a protocolos locais (Philips Hue, Shelly, Tasmota, Sonoff, Yeelight, Tuya), agregação em `ALL_ATON_TOOLS` (14 ferramentas ativas) e testes automatizados (`tests/test_smart_lights.py`). Documentado em [docs/smart_lights.md](file:///c:/xampp/htdocs/amr/docs/smart_lights.md).
- [x] **Navegação, Rotas e GPS com Google Maps (Fase 3 - Passo 1):** Módulo de rotas e geolocalização (`src/tools/google_maps.py`), esquemas de *Tool Calling* (`navigate_to`, `find_places_nearby`, `estimate_traffic_route`), suporte a *Android Intents* nativos a custo zero (`google.navigation:q=...`), trânsito em tempo real, agregação em `ALL_ATON_TOOLS` (17 ferramentas ativas) e testes automatizados (`tests/test_google_maps.py`). Documentado em [docs/google_maps.md](file:///c:/xampp/htdocs/amr/docs/google_maps.md).
- [x] **Mobile Gateway e Acesso Remoto Seguro com Tailscale (Fase 3 - Passo 2):** Servidor assíncrono ultraleve HTTP/JSON (`src/integrations/mobile_gateway.py`), endpoints `/api/status` e `/api/command` para acionamento remoto, painel Web HUD PWA para smartphone e carro com Push-to-Talk via Web Speech API, integração no ciclo de vida do assistente (`src/core/assistant.py`), suporte à VPN Tailscale a custo zero e suíte de testes (`tests/test_mobile_gateway.py`). Documentado em [docs/tailscale_and_mobile_gateway.md](file:///c:/xampp/htdocs/amr/docs/tailscale_and_mobile_gateway.md).
- [x] **Integração Google Workspace & Google Calendar (Fase 4 - Passo 1):** Módulo de agenda e compromissos (`src/tools/google_calendar.py`), esquemas de *Tool Calling* (`get_calendar_events`, `create_calendar_event`), autenticação OAuth2 com renovação automática, parser de linguagem natural para datas/horários em português, agregação em `ALL_ATON_TOOLS` (19 ferramentas ativas) e testes automatizados (`tests/test_google_calendar.py`). Documentado em [docs/google_calendar.md](file:///c:/xampp/htdocs/amr/docs/google_calendar.md).
- [x] **Integração Google Workspace & Gmail Somente Leitura (Fase 4 - Passo 2):** Módulo de e-mails (`src/tools/gmail.py`), esquemas de *Tool Calling* (`list_unread_emails`, `get_email_content`), escopo seguro `gmail.readonly`, decodificador base64url e sanitizador de tags HTML, agregação em `ALL_ATON_TOOLS` (21 ferramentas ativas) e testes automatizados (`tests/test_gmail.py`). Documentado em [docs/gmail.md](file:///c:/xampp/htdocs/amr/docs/gmail.md).
- [x] **Integração Google Workspace & Google Tasks (Fase 4 - Passo 3):** Módulo de afazeres e tarefas (`src/tools/google_tasks.py`), esquemas de *Tool Calling* (`list_tasks`, `create_task`, `complete_task`), suporte a conclusão inteligente por título em linguagem natural, agregação em `ALL_ATON_TOOLS` (24 ferramentas ativas) e testes automatizados (`tests/test_google_tasks.py`). Documentado em [docs/google_tasks.md](file:///c:/xampp/htdocs/amr/docs/google_tasks.md).
- [x] **Memória Semântica de Longo Prazo e Resumo Executivo (Fase 5):** Banco de dados relacional SQLite (`amr_memory.db`) para persistência de preferências, regras e fatos pessoais (`remember_fact`, `recall_memory`, `forget_memory`), rotina matinal autônoma de resumo executivo diário (`get_daily_briefing`) integrando Agenda, Tarefas e Gmail, agregação em `ALL_ATON_TOOLS` (28 ferramentas ativas) e testes automatizados (`tests/test_memory.py`). Documentado em [docs/fase_5.md](file:///c:/xampp/htdocs/amr/docs/fase_5.md).
- [x] **Sistema & Residente Windows (Fase 6):** Ícone dinâmico residente na bandeja do Windows (*System Tray*) com 4 estados e menu de contexto (`src/integrations/system_tray.py`), telemetria e diagnóstico de hardware em tempo real com `psutil` (`get_system_telemetry`), controle de volume mestre e controle multimídia universal via `pycaw` e teclas virtuais do Windows (`set_system_volume`, `control_system_media`), agregação em `ALL_ATON_TOOLS` (31 ferramentas ativas) e testes automatizados (`tests/test_system_telemetry.py`, `tests/test_system_audio.py`, `tests/test_system_tray.py`). Documentado em [docs/system_tray_and_telemetry.md](file:///c:/xampp/htdocs/amr/docs/system_tray_and_telemetry.md) e [docs/fase_6.md](file:///c:/xampp/htdocs/amr/docs/fase_6.md).
- [x] **Automação de Digitação & Documentos (Fase 7):** Digitação universal de texto com preservação de acentos e caracteres especiais via `pyperclip` e clipboard (`type_text_in_active_window`), criação e abertura direta de documentos Office formatados `.docx` Word e `.xlsx` Excel (`create_and_open_document`), atalhos de teclado do Windows (`send_keyboard_shortcut`), foco dinâmico de janelas (`focus_application_window`), agregação em `ALL_ATON_TOOLS` (35 ferramentas ativas) e testes automatizados (`tests/test_desktop_automation.py`). Documentado em [docs/desktop_automation.md](file:///c:/xampp/htdocs/amr/docs/desktop_automation.md) e [docs/fase_7.md](file:///c:/xampp/htdocs/amr/docs/fase_7.md).
- [x] **Segundo Cérebro Permanente com Supabase & pgvector (Fase 8):** Persistência na nuvem com PostgreSQL no Supabase, busca híbrida semântica vetorial HNSW 768d + Full-Text Search em português (`buscar_memoria_hibrida`), 18 tabelas relacionais com RLS total (perfil criador, clientes CRM, projetos, tarefas, agenda, conhecimento técnico, histórico e auditoria), Edge Functions TypeScript/Deno (`brain-api`, `consolidate-memory`), cliente desacoplado com fallback resiliente para SQLite local (`src/core/second_brain.py`), 6 ferramentas ativas integradas (`salvar_memoria`, `buscar_memoria`, `perguntar_ao_cerebro`, `criar_cliente_cerebro`, `criar_tarefa_cerebro`, `resumo_geral_cerebro`), agregação em `ALL_ATON_TOOLS` (41 ferramentas ativas) e suíte de testes completa (`tests/test_second_brain.py`). Documentado em [docs/second_brain.md](file:///c:/xampp/htdocs/amr/docs/second_brain.md) e [docs/supabase_setup_guide.md](file:///c:/xampp/htdocs/amr/docs/supabase_setup_guide.md).
- [x] **Módulo de Autoconhecimento do Aton & Changelog (Fase 8.1 - Migration 09):** Base estruturada e introspectada sobre a identidade do Aton, criador (dono de agência digital e canal Alta Restauração), arquitetura em 3 camadas, tecnologias reais (Python, Gemini Live voz Aoede, Supabase, pgvector), tabela de changelog com histórico de migrações e releases (`aton_autoconhecimento` e `aton_changelog`), módulo registrado em `modulos_sistema` (`slug = 'autoconhecimento'`), script de introspecção dinâmica (`scripts/sincronizar_autoconhecimento.py`), cache local para contingência offline (`data/aton_autoconhecimento_cache.json`), ferramenta integrada `consultar_autoconhecimento` em `ALL_ATON_TOOLS` (44 ferramentas ativas), diretrizes no prompt de sistema (`src/core/prompts.py`) com regra de honestidade absoluta ("isso não está registrado no meu autoconhecimento") e recusa estrita de senhas/chaves, documentado em [docs/aton_self_knowledge.md](file:///c:/xampp/htdocs/amr/docs/aton_self_knowledge.md) e suíte completa de testes (`tests/test_autoconhecimento.py`).
- [x] **Percepção Visual, Áudio e Interação com a Tela (Fase 9):** Motor de captura sob demanda da tela e janela ativa com metadados Win32 (`src/core/screen_perceiver.py`), compreensão visual multimodal via SDK `google-genai` com múltiplos modelos Flash resilientes (`gemini-3.5-flash`, `gemini-3.6-flash`) e contingência REST contra erros 404/503, Bounding Boxes normalizadas `[ymin, xmin, ymax, xmax]` mapeadas para coordenadas reais de tela, 5 ferramentas ativas (`descrever_tela`, `ler_conteudo_tela`, `localizar_e_clicar_elemento`, `preencher_campo_na_tela`, `rolar_tela`) em `src/tools/screen_perception.py`, portão de segurança para ações destrutivas/críticas, digitação universal via clipboard, agregação em `ALL_ATON_TOOLS` (49 ferramentas ativas), diretrizes de percepção visual no prompt (`src/core/prompts.py`), documentação em [docs/screen_perception.md](file:///c:/xampp/htdocs/amr/docs/screen_perception.md) e testes automatizados (`tests/test_screen_perception.py`).
- [x] **Inicialização Automática com o Windows e Detecção Exata "Aton" Offline (Fase 10):** Reconhecimento offline da palavra-chave exata "aton" em português via **Vosk** (`vosk-model-small-pt-0.3`) com **0% de falsos positivos por volume RMS**, rejeição contínua de sons ambientes/conversas normais sem acionar a nuvem, inicialização invisível em segundo plano sem janela de console via VBScript (`launch_aton_background.vbs`) e `pythonw.exe`, ícone dinâmico residente na bandeja do sistema (*System Tray*) com menu de clique para encerrar ou inspecionar status, scripts reversíveis de ativação/desativação no Windows (`scripts/ativar_inicializacao_windows.bat`, `scripts/desativar_inicializacao_windows.bat`, `run.bat bg/status/autostart-on/autostart-off/stop`), atalho nativo configurado na pasta de inicialização do usuário atual (`ATON.lnk`), documentação atualizada em [docs/wake_word.md](file:///c:/xampp/htdocs/amr/docs/wake_word.md) e suíte de testes completa aprovada (`tests/test_wake_word.py`).
- [x] **ATON em Rede e Dispositivos Autorizados (Fase 11):** Arquitetura Hub/Anfitrião multi-dispositivo para celulares, TVs e outros PCs com princípio de Zero Confiança Local; descoberta mDNS/DNS-SD com `AsyncZeroconf` (`_aton._tcp.local.`) e leitura de interfaces de rede ativas (Wi-Fi, Ethernet, Tailscale) via `psutil` (`src/core/network_discovery.py`); gerenciador de segurança e autorização (`src/core/device_manager.py`) com persistência SQLite em `aton_paired_devices`, pareamento seguro por código PIN descartável de 6 dígitos com expiração de 5 minutos, tokens Bearer de 256 bits com hash SHA-256 e controle de permissões granulares (`commands`, `audio`, `screen`, `files`, `control`); servidor HTTP gateway atualizado (`src/integrations/mobile_gateway.py`) com endpoints de pareamento, revogação e Web HUD SPA responsiva para celular e Smart TV (Modo TV D-Pad); 4 novas ferramentas do assistente (`get_network_info`, `list_network_devices`, `revoke_network_device`, `scan_network_devices`) totalizando 53 ferramentas ativas integradas (`src/tools/network_tools.py`), documentação em [docs/network_devices.md](file:///c:/xampp/htdocs/amr/docs/network_devices.md) e suíte de testes automatizados completa (`tests/test_network_devices.py`, `tests/test_mobile_gateway.py`).

---

## 6. Estrutura de Pastas Esperada

```text
amr/
├── .agents/                    # Customizações, regras e skills do agente
├── docs/                       # Documentação técnica em português
│   ├── ROADMAP.md              # Fases do projeto e critérios de pronto
│   ├── ARCHITECTURE.md         # Detalhes da arquitetura de duas camadas e MCP
│   └── SETUP_CHECKLIST.md      # Passos manuais do usuário (obtenção de chaves)
├── src/                        # Código-fonte principal do AMR
│   ├── core/                   # Cérebro: Conexão com Gemini Live, loop de áudio e VAD
│   ├── audio/                  # Captura do microfone, reprodução e wake word local ("AMR")
│   ├── tools/                  # Ferramentas e servidores MCP (Windows, Web, IoT)
│   ├── integrations/           # Integrações Google (Workspace, Maps)
│   └── config.py               # Configurações e variáveis de ambiente
├── tests/                      # Testes automatizados (pytest)
├── .env.example                # Modelo das variáveis de ambiente
├── .gitignore                  # Arquivos ignorados pelo git
├── pyproject.toml              # Dependências e empacotamento Python
└── run.bat                     # Script de execução rápida no Windows
```
