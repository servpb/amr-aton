# Aton - Assistente Pessoal Inteligente de Alta Performance

O **Aton** é um assistente pessoal inteligente operado prioritariamente por voz (áudio bidirecional em tempo real), sem necessidade de interface gráfica pesada, inspirado na arquitetura de assistentes de alta performance como o J.A.R.V.I.S.

Desenvolvido para ambiente **Windows** com foco no ecossistema Google (Google GenAI, Gemini Live, Google Maps, Google Workspace), começando com custo zero (camadas gratuitas) e preparado para rodar localmente com máxima fluidez e baixa latência.

---

## ⚡ Principais Características

- 🎙️ **Conversação Contínua em Tempo Real:** Conexão de áudio bidirecional de baixa latência com a API **Gemini Live** (SDK `google-genai`).
- 👂 **Ativação Offline por Palavra-Chave ("Aton"):** Detecção local ultraleve sem consumo de API ou banda de rede.
- 🎛️ **Push-to-Talk de Emergência:** Atalho rápido no teclado para ambientes ruidosos.
- 💻 **Controle do Windows:** Abertura, fechamento e listagem de processos e aplicativos locais.
- 🌐 **Navegação Web Automatizada:** Pesquisas no Google, YouTube e automação web com Playwright.
- 📺 **Automação Residencial (Wi-Fi):** Controle de Smart TVs (WoL, DIAL, volume, mudo, aplicativos), lâmpadas e tomadas inteligentes locais.
- 📱 **Localizador de Smartphone:** Disparo de alarme sonoro de alto volume no celular Android conectado na rede.
- 🚗 **Mobilidade & GPS:** Traçado de rotas ponto a ponto com Google Maps e cálculo de trânsito em tempo real.
- 🔒 **Mobile Gateway & VPN Tailscale:** Acesso remoto seguro de qualquer lugar pelo celular ou carro com painel Web HUD PWA e comando por voz.
- 📅 **Google Workspace Integrado:** Leitura e agendamento de compromissos no Google Agenda, consulta a e-mails importantes no Gmail (somente leitura) e gestão de afazeres no Google Tasks.
- 🧠 **Memória Semântica de Longo Prazo:** Persistência em SQLite (`amr_memory.db`) de preferências, regras de trabalho e fatos do usuário, além de Resumo Executivo Diário (*Daily Briefing*).
- 🖥️ **Residente na Bandeja do Windows (System Tray):** Ícone dinâmico com 4 estados visuais na barra de tarefas, menu de contexto com mudo de microfone, telemetria de hardware (bateria, CPU, RAM e disco) e controle de volume e multimídia do Windows.

---

## 🏗️ Arquitetura em Duas Camadas

```
                       [MICROFONE DO PC]
                              │
                              ▼
                ┌──────────────────────────┐
                │   Módulo de Wake Word    │  (openWakeWord - Offline / 0% CPU)
                │      Detecta "Aton"      │
                └─────────────┬────────────┘
                              │ Palavra detectada
                              ▼
       ┌──────────────────────────────────────────────┐
       │     CAMADA 1: CONVERSAÇÃO RÁPIDA (Voz)       │
       │        (Gemini Live API via WebSocket)       │
       │                                              │
       │  - Streaming de áudio PCM bidirecional       │
       │  - Resposta instantânea e interrupção fluida │
       └──────────────────────┬───────────────────────┘
                              │ Dispara Tool Call Assíncrono (31 ferramentas ativas)
                              ▼
       ┌──────────────────────────────────────────────┐
       │     CAMADA 2: EXECUÇÃO & TRABALHO (Worker)   │
       │        (Fila Assíncrona em Segundo Plano)    │
       │                                              │
       │  - Automação Windows, Apps & Mídia           │
       │  - Smart TV, IoT e Redes Wi-Fi               │
       │  - Google Workspace & Google Maps            │
       │  - Memória Semântica & SQLite                │
       └──────────────────────────────────────────────┘
                              │
                              ▼
                      [ALTO-FALANTE DO PC]
```

---

## 🚀 Instalação e Configuração

### Pré-requisitos
- **Windows 10 ou 11** (64-bit)
- **Python 3.10+** (Recomendado: Python 3.11)
- Microfone e alto-falantes funcionais
- Chave de API gratuita do [Google AI Studio](https://aistudio.google.com/)

### 1. Clonar o Repositório
```bash
git clone https://github.com/profsebastiao/amr.git
cd amr
```

### 2. Configurar o Ambiente Virtual
```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -e .
```

### 3. Configurar Variáveis de Ambiente
Copie o arquivo de exemplo e insira sua chave da API Gemini:
```powershell
copy .env.example .env
```
Edite o arquivo `.env`:
```env
GEMINI_API_KEY=sua_chave_aqui
GEMINI_LIVE_MODEL=gemini-2.0-flash-exp
GEMINI_VOICE_NAME=Aoede
AMR_WAKE_WORD=aton
```

---

## 🎮 Como Executar

Execute o script de inicialização rápida no Windows:
```cmd
run.bat
```
Ou via terminal:
```powershell
.\.venv\Scripts\python.exe src/main.py
```

### Comandos de Exemplo
- *"Aton"* -> Ele responde imediatamente *"Sim, senhor?"*.
- *"Aton, como está o desempenho do PC?"* -> Ele reporta bateria, CPU, RAM e disco.
- *"Aton, coloque o volume do computador em 40%"*.
- *"Aton, quais são os meus compromissos de hoje?"*.
- *"Aton, lembre-se de que eu prefiro exportar vídeos sempre em 4K 60fps"*.
- *"Aton, qual o resumo do dia?"*.

---

## 🧪 Testes Automatizados

Para rodar toda a suíte de testes unitários:
```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -v
```

---

## 📄 Licença
Distribuído sob a licença MIT. Consulte o arquivo `LICENSE` para mais detalhes.
