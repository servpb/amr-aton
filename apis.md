# Arquitetura e Guia das 3 APIs de Inteligência Artificial do Aton

Este documento consolida a arquitetura, modelos, objetivos e formas de uso das **três APIs de inteligência artificial** integradas ao ecossistema do assistente **Aton**:
1. **Google Gemini Live API** (Voz Bidirecional em Tempo Real & Visão Computacional)
2. **Groq LPU API** (Inferência Instantânea de Texto em Ultra-Baixa Latência)
3. **NVIDIA Nemotron via OpenRouter / NIM** (Planejamento Avançado & Raciocínio Profundo)

---

## 🎯 Visão Comparativa das 3 Inteligências

| Funcionalidade | **1. Google Gemini Live** | **2. Groq LPU** | **3. NVIDIA Nemotron** |
| :--- | :--- | :--- | :--- |
| **Papel Central** | **Conversação & Voz:** Áudio bidirecional fluído estilo Jarvis e percepção visual da tela. | **Execução Rápida:** Respostas ágeis a comandos, resumos instantâneos e fallback. | **Estratégia & Raciocínio:** Decomposição de tarefas complexas e análise de riscos. |
| **Latência Típica** | Streaming contínuo de áudio (~400ms) | **~300ms a 1.5s** | ~10s a 16s (Gera planos detalhados com 2.500+ tokens) |
| **Modelo Padrão** | `gemini-3.1-flash-live-preview` | `openai/gpt-oss-20b` | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` |
| **Voz / Áudio** | Voz nativa **Aoede** (24kHz) | Somente texto | Somente texto |
| **Custo** | Cota gratuita Google AI Studio | Camada gratuita oficial da Groq | Modelo `:free` gratuito no OpenRouter |

---

## 1. Google Gemini Live API (Voz, Áudio e Multimodalidade)

### Propósito
Atua como a presença vocal e auditiva primária do Aton. Ouve continuamente o microfone quando acordado pela palavra-chave local (*Vosk offline* `"Aton"`), responde por voz natural brasileira e é capaz de enxergar a tela do Windows.

### Configuração no `.env`
```env
GEMINI_API_KEY=sua_chave_google_ai_studio
GEMINI_LIVE_MODEL=gemini-3.1-flash-live-preview
GEMINI_VISION_MODEL=gemini-3-flash-preview
GEMINI_VOICE_NAME=Aoede
```

### Arquivos Principais no Projeto
- `src/core/live_client.py`: Cliente WebSocket assíncrono para streaming de áudio bidirecional PCM.
- `src/core/prompts.py`: Prompt de sistema com a personalidade Jarvis e diretrizes de acionamento das 85 ferramentas do Aton.
- `src/core/screen_perceiver.py`: Módulo de visão multimodal para leitura e localização de elementos na tela.

---

## 2. Groq LPU API (Inferência Ultra-Rápida)

### Propósito
Processamento de texto em tempo recorde utilizando unidades LPU (*Language Processing Units*). Ideal para comandos que exigem raciocínio ou formatação quase instantânea sem atrasar o fluxo de trabalho.

### Modelos Suportados na Conta
- `openai/gpt-oss-20b` (Padrão: resposta em ~300ms)
- `openai/gpt-oss-120b` (Modelo maior de alta precisão)
- `qwen/qwen3.8-27b` (Multilíngue)
- `whisper-large-v3-turbo` (Transcrição ultra-rápida de áudio)

### Configuração no `.env`
```env
GROQ_API_KEY=gsk_sua_chave_groq
GROQ_MODEL=openai/gpt-oss-20b
GROQ_ENABLED=true
GROQ_TIMEOUT_SECONDS=15
```

### Ferramentas Integradas do Assistente
- `query_groq_llm(prompt, system_prompt, model)`: Consulta de texto ultrarrápida.
- `check_groq_connection()`: Checagem instantânea de latência e saúde da API.

### Como Testar
- **Via Terminal:**
  ```powershell
  .\run.bat groq-test
  ```
- **Por Voz com o Aton:**
  > *"Aton, verifique a conexão com a Groq."*  
  > *"Aton, consulte a Groq e me explique o que é computação quântica."*

---

## 3. NVIDIA Nemotron (Planejamento & Raciocínio Profundo)

### Propósito
Modelo de raciocínio profundo alinhado pela NVIDIA para quebrar desafios complexos em planos estruturados de ação. Produz diagnósticos técnicos, matrizes de risco, pré-requisitos e passos ordenados.

### Arquitetura Híbrida e Custo Zero
O conector do Aton foi projetado com prioridade inteligente e trava de custo zero:
1. **OpenRouter (Ativo):** Rota comunitária sem custo utilizando modelos oficiais gratuitos `:free`. A trava `strict_free_tier=True` no código do Aton bloqueia qualquer chamada acidental para modelos pagos.
2. **NVIDIA NIM Direto (build.nvidia.com):** Conexão direta com clusters H100 oficiais da NVIDIA.

### Modelos Ativos e Suportados
- `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` (Padrão: modelo de raciocínio profundo com cadeia de pensamento interna).
- `nvidia/nemotron-3.5-lightning:free` (Versão rápida).
- `nvidia/nemotron-3-ultra-550b-a55b:free` (Modelo massivo de 550 bilhões de parâmetros).
- `nvidia/llama-3.1-nemotron-70b-instruct` (Endpoint direto NVIDIA NIM).

### Configuração no `.env`
```env
# OpenRouter (Custo Zero garantido com :free)
OPENROUTER_API_KEY=sk-or-v1-sua_chave_aqui
OPENROUTER_MODEL=nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free
OPENROUTER_ENABLED=true
OPENROUTER_TIMEOUT_SECONDS=25

# NVIDIA NIM Oficial (Opcional - Direto com clusters H100)
NVIDIA_API_KEY=nvapi-sua_chave_nvidia
```

### Ferramentas Integradas do Assistente
- `planejar_tarefa_complexa(objetivo, restricoes, contexto)`: Produz um plano executivo completo dividido em 5 seções fundamentais:
  1. *Objetivo Central*
  2. *Pré-requisitos e Dependências*
  3. *Plano Passo a Passo*
  4. *Riscos Identificados e Planos de Mitigação*
  5. *Critério de Pronto (Definição de Sucesso)*
- `consultar_nemotron(prompt)`: Consulta analítica profunda.
- `check_nemotron_connection()`: Verifica o status e a latência do endpoint.

### Como Testar
- **Via Terminal (Benchmark Comparativo):**
  ```powershell
  .\run.bat nemotron-test --compare
  ```
- **Por Voz com o Aton:**
  > *"Aton, verifique a conexão com a Nemotron."*  
  > *"Aton, planeje uma rotina de contingência para backup de arquivos."*

---

## 📁 Estrutura de Arquivos Criados / Modificados

```text
amr/
├── apis.md                            # Este documento consolidado
├── .env.example                       # Exemplo de configuração sem credenciais
├── run.bat                            # Comandos rápidos: groq-test e nemotron-test
├── scripts/
│   ├── testar_groq.py                 # Diagnóstico e teste de inferência Groq LPU
│   └── avaliar_nemotron.py            # Benchmark comparativo Nemotron vs Groq
├── src/
│   ├── config.py                      # Pydantic Settings com chaves mascaradas
│   ├── core/
│   │   ├── prompts.py                 # Diretrizes 16 (Groq) e 17 (Nemotron)
│   │   └── module_registry.py         # Registro e introspecção dos módulos
│   ├── integrations/
│   │   ├── groq_client.py             # Conector HTTPS Groq com urllib nativo
│   │   ├── openrouter_client.py       # Conector híbrido OpenRouter/NVIDIA NIM
│   │   └── mobile_gateway.py          # Roteamento dos comandos pelo celular
│   └── tools/
│       ├── __init__.py                # Agregação geral em ALL_ATON_TOOLS
│       ├── groq_service.py            # Ferramentas query_groq_llm e check_groq
│       └── nemotron_service.py        # Ferramentas de planejamento Nemotron
├── tests/
│   ├── test_groq_integration.py       # Testes unitários do conector Groq
│   └── test_nemotron_integration.py   # Testes unitários do conector Nemotron
└── docs/
    ├── groq_integration.md            # Documentação técnica individual Groq
    └── nemotron_planning.md           # Documentação técnica individual Nemotron
```

---

## 🔒 Segurança e Privacidade

1. **Zero Segredos no Código:** Todas as chaves (`GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `NVIDIA_API_KEY`) residem exclusivamente no `.env`, arquivo ignorado pelo `.gitignore`.
2. **Sanitização de Logs:** Respostas a erros de rede ou exceções HTTP nunca imprimem o cabeçalho `Authorization` ou o corpo que contenha tokens.
3. **Trava de Custo Zero:** O módulo OpenRouter rejeita em tempo de execução qualquer solicitação que não aponte para um modelo terminado em `:free`.

