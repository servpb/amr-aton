# Status Operacional dos 23 Módulos do Assistente Aton (`módulos.md`)

**Última atualização:** 04/11/2026  
**Resumo Geral:** Dos **23 módulos** registrados no catálogo do Aton ([`src/core/module_registry.py`](file:///c:/xampp/htdocs/amr/src/core/module_registry.py)):
- **✅ 20 módulos estão FUNCIONANDO e prontos para uso imediato por voz.**
- **⚙️ 2 módulos NÃO estão ativos ainda porque precisam de configuração de hardware externo.**
- **🚫 1 módulo está DESATIVADO por design de segurança.**

---

## ✅ 1. MÓDULOS FUNCIONANDO E ATIVOS (20 de 23)

Estes módulos já estão configurados, autenticados e operacionais por voz:

| Nº | Módulo | Descrição | Status e Detalhes da Configuração Ativa |
| :-: | :--- | :--- | :--- |
| **1** | **Controle do Fire TV Stick** | Controle por voz do Amazon Fire TV Stick via rede local Wi-Fi, permitindo abrir aplicativos, navegar e pesquisar ou reproduzir vídeos no YouTube. | **🟢 FUNCIONANDO (Configurado)** — Pareado em [`data/fire_tv_state.json`](file:///c:/xampp/htdocs/amr/data/fire_tv_state.json) (IP `192.168.0.7`, Modelo `AFTSS`). Opera sempre que o Fire Stick estiver ligado no Wi-Fi. |
| **5** | **Aplicativos e Janelas do Windows** | Abertura de programas do PC, fechamento inteligente em 3 camadas e listagem de aplicativos em execução. | **🟢 FUNCIONANDO (100% Ativo)** — Execução nativa local no Windows ([`src/tools/windows_apps.py`](file:///c:/xampp/htdocs/amr/src/tools/windows_apps.py)). |
| **6** | **Navegação Web e Pesquisa** | Pesquisas na internet, abertura de páginas web e reprodução direta de vídeos no YouTube do computador. | **🟢 FUNCIONANDO (100% Ativo)** — Navegador padrão e Playwright ([`src/tools/web_browser.py`](file:///c:/xampp/htdocs/amr/src/tools/web_browser.py)). |
| **7** | **Automação de Digitação e Documentos** | Digitação de textos na janela ativa com preservação de acentos, envio de atalhos e criação de documentos Word (`.docx`) e Excel (`.xlsx`). | **🟢 FUNCIONANDO (100% Ativo)** — Operacional via área de transferência e `python-docx`/`openpyxl` ([`src/tools/desktop_automation.py`](file:///c:/xampp/htdocs/amr/src/tools/desktop_automation.py)). |
| **8** | **Volume e Multimídia do Windows** | Ajuste do volume mestre do computador (0 a 100%) e controle de mídia do PC (play, pause, mudo e faixas). | **🟢 FUNCIONANDO (100% Ativo)** — Operacional via `pycaw` e teclas virtuais do Windows ([`src/tools/system_audio.py`](file:///c:/xampp/htdocs/amr/src/tools/system_audio.py)). |
| **9** | **Telemetria e Diagnóstico de Hardware** | Diagnóstico em tempo real de uso de CPU, memória RAM, armazenamento em disco e nível de bateria. | **🟢 FUNCIONANDO (100% Ativo)** — Leitura local em tempo real via `psutil` ([`src/tools/system_telemetry.py`](file:///c:/xampp/htdocs/amr/src/tools/system_telemetry.py)). |
| **10** | **Rede e Dispositivos Autorizados** | Descoberta mDNS ZeroConf, pareamento seguro por PIN de 6 dígitos e controle de aparelhos autorizados no Mobile Gateway. | **🟢 FUNCIONANDO (100% Ativo)** — Operacional na rede local ([`src/tools/network_tools.py`](file:///c:/xampp/htdocs/amr/src/tools/network_tools.py)). |
| **11** | **Percepção Visual e Compreensão de Tela** | Análise visual do monitor com visão computacional multimodal, leitura de conteúdos e cliques baseados em tela. | **🟢 FUNCIONANDO (100% Ativo)** — Conectado ao Gemini Flash Multimodal via `GEMINI_API_KEY` ([`src/tools/screen_perception.py`](file:///c:/xampp/htdocs/amr/src/tools/screen_perception.py)). |
| **12** | **Canais e Vídeos do YouTube** | Consulta de canais, vídeos, comentários, estatísticas de inscritos/visualizações e gerenciamento seguro com confirmação em duas fases. | **🟢 FUNCIONANDO (Autenticado)** — Canal `Servpb` (`UC9dkQgEFbC33X-yLHKDhQpg`, `@servpb`, conta `servpb@gmail.com`) ativo em [`tokens/youtube_channels_index.json`](file:///c:/xampp/htdocs/amr/tokens/youtube_channels_index.json) ([`docs/youtube.md`](file:///c:/xampp/htdocs/amr/docs/youtube.md)). |
| **13** | **Gmail (Somente Leitura)** | Consulta de e-mails não lidos e leitura segura de mensagens das contas Google autorizadas. | **🟢 FUNCIONANDO (Autenticado)** — Conta `servpb@gmail.com` ativa em [`tokens/accounts_index.json`](file:///c:/xampp/htdocs/amr/tokens/accounts_index.json) ([`docs/gmail.md`](file:///c:/xampp/htdocs/amr/docs/gmail.md)). |
| **14** | **Google Agenda (Calendar)** | Consulta, agendamento, edição, exclusão segura, detecção automática de conflitos e gestão de agendas 100% por voz. | **🟢 FUNCIONANDO (Autenticado)** — Conta `servpb@gmail.com` (`America/Fortaleza`) ativa em [`tokens/calendar_accounts_index.json`](file:///c:/xampp/htdocs/amr/tokens/calendar_accounts_index.json) ([`docs/google_calendar.md`](file:///c:/xampp/htdocs/amr/docs/google_calendar.md)). |
| **15** | **Google Tarefas (Tasks)** | Criação, consulta e conclusão de afazeres na lista de tarefas do Google por comandos de voz. | **🟢 FUNCIONANDO (Autenticado)** — Conta `servpb@gmail.com` ativa com escopo `tasks` em `tokens/tasks_token.json` e `token.json` ([`docs/google_tasks.md`](file:///c:/xampp/htdocs/amr/docs/google_tasks.md)). |
| **16** | **Rotas e GPS (Google Maps)** | Cálculo de trajeto com trânsito em tempo real, busca de locais próximos e disparo de navegação passo a passo. | **🟢 FUNCIONANDO (100% Ativo)** — Opera a custo zero via *Android Intents* e URLs diretas ([`src/tools/google_maps.py`](file:///c:/xampp/htdocs/amr/src/tools/google_maps.py)). |
| **17** | **Timers e Lembretes** | Avisos locais persistentes com som e notificação do Windows, independentes da conversa de voz. | **🟢 FUNCIONANDO (100% Ativo)** — Persistência local em `data/reminders.sqlite3` ([`src/tools/reminders.py`](file:///c:/xampp/htdocs/amr/src/tools/reminders.py)). |
| **18** | **Segundo Cérebro e Memória Permanente** | Memória relacional e semântica de longo prazo no Supabase PostgreSQL + pgvector com contingência local. | **🟢 FUNCIONANDO (100% Ativo)** — Conectado ao Supabase e banco SQLite local ([`src/tools/second_brain_tools.py`](file:///c:/xampp/htdocs/amr/src/tools/second_brain_tools.py)). |
| **19** | **Memória Local e Briefing Diário** | Banco de memória rápida local (`amr_memory.db`) para fatos cotidianos e resumo executivo matinal. | **🟢 FUNCIONANDO (100% Ativo)** — Integrado ao Google Agenda e Gmail autenticados ([`src/core/memory.py`](file:///c:/xampp/htdocs/amr/src/core/memory.py)). |
| **20** | **Inferência Rápida Groq LPU** | Processamento de linguagem natural e inferência ultra-rápida (~300ms) na API oficial da Groq. | **🟢 FUNCIONANDO (Configurado)** — Modelo `openai/gpt-oss-20b` ativo via `GROQ_API_KEY` ([`docs/groq_integration.md`](file:///c:/xampp/htdocs/amr/docs/groq_integration.md)). |
| **21** | **Planejamento Avançado NVIDIA Nemotron** | Decomposição analítica e planejamento estruturado de tarefas complexas com NVIDIA Nemotron 70B. | **🟢 FUNCIONANDO (Configurado)** — Ativo via NVIDIA NIM / OpenRouter ([`docs/nemotron_planning.md`](file:///c:/xampp/htdocs/amr/docs/nemotron_planning.md)). |
| **22** | **Rotinas e Cenas Multi-Módulo Verificadas** | Execução coordenada de cenas (`bom_dia`, `modo_cinema`, `modo_foco`, `boa_noite`, `restaurar`) com isolamento de falhas por etapa, verificação em 3 níveis e restauração de volume e DND. | **🟢 FUNCIONANDO (100% Ativo)** — Motor ativo em [`src/tools/scenes.py`](file:///c:/xampp/htdocs/amr/src/tools/scenes.py) ([`docs/scenes.md`](file:///c:/xampp/htdocs/amr/docs/scenes.md)). |
| **23** | **Organizador Seguro de Arquivos Locais & Área de Trabalho** | Pesquisa, leitura segura, categorização automática por subpastas e movimentação entre pastas autorizadas com confirmação em duas fases e reversão completa (Undo). | **🟢 FUNCIONANDO (100% Ativo)** — Operacional com sandbox estrito em [`src/tools/local_files.py`](file:///c:/xampp/htdocs/amr/src/tools/local_files.py) ([`docs/local_files.md`](file:///c:/xampp/htdocs/amr/docs/local_files.md)). |

---

## ⚙️ 2. MÓDULOS QUE NÃO FUNCIONAM AINDA (PRECISAM DE CONFIGURAÇÃO DE HARDWARE — 2 de 23)

Estes módulos já possuem todo o código implementado e testado, mas **não executarão ações reais até que os dispositivos na rede sejam configurados**:

| Nº | Módulo | Por que não está funcionando agora? | Como Configurar / Ativar |
| :-: | :--- | :--- | :--- |
| **2** | **Localizador de Celular** | **🔴 AGUARDANDO CONFIGURAÇÃO** — A variável `ANDROID_PHONE_IP` (ou `PHONE_FINDER_WEBHOOK_URL`) está vazia no `.env`. | 1. Instale MacroDroid ou Tasker no celular Android (ou ative ADB Wi-Fi).<br>2. Preencha `ANDROID_PHONE_IP=192.168.0.X` no arquivo `.env`. |
| **3** | **Iluminação e Tomadas Inteligentes** | **🔴 AGUARDANDO CONFIGURAÇÃO** — A variável `SMART_LIGHTS_BRIDGE_IP` está vazia no `.env`. | Caso possua lâmpadas ou tomadas inteligentes Wi-Fi (Philips Hue, Sonoff, Shelly, Tuya), informe o IP local delas em `SMART_LIGHTS_BRIDGE_IP` no `.env`. |

---

## 🚫 3. MÓDULO DESATIVADO POR DESIGN (NÃO FUNCIONA NESTA VERSÃO — 1 de 21)

| Nº | Módulo | Status | Motivo Técnico |
| :-: | :--- | :--- | :--- |
| **4** | **Smart TV Convencional** | **⚪ INDISPONÍVEL POR DESIGN** | O controle direto de volume e energia física da televisão permanece intencionalmente bloqueado porque o controle de mídia/apps da sua TV é feito pelo **Fire TV Stick (Módulo 1)**. Isso evita que comandos de volume da TV alterem por engano o volume do computador Windows ou gerem falsas confirmações. |

