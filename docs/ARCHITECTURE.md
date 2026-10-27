# ARCHITECTURE.md - Arquitetura Técnica do AMR

Este documento detalha o funcionamento interno, o fluxo de dados e os princípios de engenharia por trás do **AMR**.

---

## 1. Visão Geral da Arquitetura

O AMR opera como um **assistente headless** (sem interface gráfica pesada) residente no Windows, estruturado no padrão de **Duas Camadas Desacopladas**:

```
                       [MICROFONE DO PC]
                              │
                              ▼
                ┌──────────────────────────┐
                │   Módulo de Wake Word    │  (openWakeWord - Offline / 0% CPU)
                │      Detecta "AMR"       │
                └─────────────┬────────────┘
                              │ Palavra detectada
                              ▼
       ┌──────────────────────────────────────────────┐
       │     CAMADA 1: CONVERSAÇÃO RÁPIDA (Voz)       │
       │        (Gemini Live API via WebSocket)       │
       │                                              │
       │  - Streaming de áudio PCM bidirecional       │
       │  - Interrupção natural de fala               │
       │  - Resposta verbal imediata ("Já estou nisso")│
       └──────────────────────┬───────────────────────┘
                              │
                              │ Dispara Tool Call Assíncrono
                              ▼
       ┌──────────────────────────────────────────────┐
       │     CAMADA 2: EXECUÇÃO & TRABALHO (Worker)   │
       │        (Background Async Task Queue)         │
       │                                              │
       │  - Automação Windows (Win32 / Processos)     │
       │  - Navegação Web (Playwright)                │
       │  - Dispositivos Wi-Fi (TVs, Lâmpadas)        │
       │  - Integrações Google (Maps, Workspace)      │
       └──────────────────────────────────────────────┘
                              │
                              ▼
                      [ALTO-FALANTE DO PC]
                (Áudio contínuo de resposta)
```

---

## 2. Camada 1: Voz Rápida (Conversacional)

- **Objetivo:** Garantir tempo de resposta inferior a 1 segundo ao falar com o AMR.
- **Protocolo:** WebSocket bidirecional conectado à API **Gemini Multimodal Live** (Google GenAI SDK).
- **Formato de Áudio:** PCM 16-bit linear a 16.000 Hz ou 24.000 Hz (mono), permitindo baixa largura de banda e latência mínima.
- **Ciclo de Vida:**
  1. **Estado DORMIR (Sleep):** O microfone passa apenas pelo detector de wake word local. Nenhuma conexão de internet ou API é consumida.
  2. **Estado ATIVO (Active):** Ao ouvir *"AMR"*, o sistema acorda, emite um bip sutil de confirmação e estabelece o canal de streaming de voz com o Gemini.
  3. **Modo Conversacional Contínuo:** O assistente permanece ouvindo por até `CONVERSATION_TIMEOUT_SECONDS` (padrão: 7s). Se o usuário fizer novas perguntas, ele responde imediatamente sem necessidade de repetir o nome "AMR".

---

## 3. Camada 2: Execução de Tarefas (Worker Assíncrono)

- **Objetivo:** Evitar que o assistente fique mudo ou congele enquanto tarefas demoradas (abrir programas pesados, navegar em sites, renderizar vídeos) são executadas.
- **Mecanismo:** 
  - Quando o Gemini Live detecta uma intenção de ação (ex: *"abra o navegador e pesquise X"*), ele emite um evento de **Tool Call**.
  - O loop de voz despacha a função para a fila de background assíncrona (`asyncio.create_task`).
  - O Gemini responde verbalmente em frações de segundo (*"Abrindo a pesquisa para o senhor..."*).
  - A tarefa é executada pelo worker e, ao finalizar, pode notificar o usuário com um aviso sonoro ou fala conclusiva.

---

## 4. Segurança e Isolamento

1. **Portão de Confirmação:** Funções classificadas como destrutivas (apagar arquivos, compras, envio de e-mails) mudam o estado para `NEEDS_CONFIRMATION` e exigem resposta verbal explícita (*"Tem certeza de que deseja excluir o arquivo X?"*).
2. **Sem Exposição de Portas de Rede:** A comunicação de rede utiliza conexões exclusivamente de saída (*outbound*), sem necessidade de abrir portas no firewall ou roteador.
3. **Credenciais Seguras:** Todas as chaves ficam estritamente em variáveis de ambiente carregadas via `.env`.
