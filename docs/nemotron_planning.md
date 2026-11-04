# Planejamento Avançado com NVIDIA Nemotron (NVIDIA NIM Direto & OpenRouter)

Este documento descreve a integração do modelo **NVIDIA Nemotron 70B** (`nvidia/llama-3.1-nemotron-70b-instruct`), operando como o motor analítico do assistente **Aton** para tarefas complexas, arquitetura de sistemas e decomposição de passos a **custo zero**.

O conector suporta arquitetura híbrida de ponta:
1. **NVIDIA NIM Direto Oficial (`build.nvidia.com` - Recomendado):** Conecta diretamente nos clusters H100 da NVIDIA com aceleração TensorRT-LLM, latência mínima e 1.000 chamadas gratuitas por conta de desenvolvedor.
2. **OpenRouter (`openrouter.ai`):** Rota comunitária com modelos gratuitos (`:free`).

---

## 1. Visão Geral e Propósito

Enquanto o **Gemini Live** cuida da conversação de áudio em tempo real e a **Groq LPU** provê inferência instantânea (~300ms) para comandos rápidos, o modelo **NVIDIA Nemotron 70B** atua na camada de raciocínio profundo (*Deep Planning & Reasoning*):
- **Decomposição Estruturada:** Quebra problemas complexos em fases ordenadas, identificando pré-requisitos, riscos e critérios de sucesso.
- **Rigor Lógico:** Modelo alinhado pela NVIDIA com alta capacidade para regras estritas, limites de sistema e processos detalhados.
- **Detecção Automática de Provedor:** Se a chave começar com `nvapi-...` ou `NVIDIA_API_KEY` estiver definida, usa a API direta da NVIDIA; caso contrário, utiliza a rota do OpenRouter.
- **Custo Zero Garantido:** Exige obrigatoriamente modelos com o sufixo `:free` no OpenRouter, ou os 1.000 créditos gratuitos do NVIDIA NIM.

---

## 2. Configuração Local (`.env`)

### Opção 1: NVIDIA NIM Direto (Recomendado - Máxima Velocidade)
Crie uma conta gratuita em [build.nvidia.com](https://build.nvidia.com/nvidia/llama-3_1-nemotron-70b-instruct) e gere uma chave de API:

```env
# NVIDIA NIM Oficial (build.nvidia.com) - Direto com clusters H100
NVIDIA_API_KEY=nvapi-...
NVIDIA_MODEL=nvidia/llama-3.1-nemotron-70b-instruct
NVIDIA_ENDPOINT=https://integrate.api.nvidia.com/v1/chat/completions
```

### Opção 2: OpenRouter (Custo Zero com :free)
Crie uma conta gratuita em [openrouter.ai](https://openrouter.ai/):

```env
# OpenRouter & NVIDIA Nemotron (Custo Zero com :free)
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=nvidia/llama-3.1-nemotron-70b-instruct:free
OPENROUTER_ENABLED=true
OPENROUTER_TIMEOUT_SECONDS=25
```

---

## 3. Ferramentas Integradas do Assistente

### A. `planejar_tarefa_complexa`
Executa a decomposição analítica e gera um plano executivo estruturado.
- **Parâmetros:**
  - `objetivo` (*string, obrigatório*): Meta ou projeto complexo a ser planejado.
  - `restricoes` (*string, opcional*): Regras, prazos ou tecnologias mandatórias.
  - `contexto` (*string, opcional*): Informações de ambiente adicionais.
- **Retorno:**
  - `status`: `"success"` ou `"error"`
  - `plano`: Texto com o plano em 5 seções (Objetivo Central, Pré-requisitos, Passo a Passo, Riscos/Mitigação e Critério de Sucesso).
  - `provider`: Provedor ativo (`nvidia_nim` ou `openrouter`).
  - `model`: Modelo utilizado.
  - `elapsed_ms`: Tempo de resposta em milissegundos.
  - `usage`: Contagem de tokens consumidos.

### B. `consultar_nemotron`
Consulta direta ao modelo NVIDIA para raciocínio lógico avançado ou análise técnica.
- **Parâmetros:**
  - `prompt` (*string, obrigatório*): Pergunta analítica ou desafio lógico.

### C. `check_nemotron_connection`
Verifica a conectividade e latência do endpoint ativo (NVIDIA NIM ou OpenRouter).
- **Retorno:**
  - `status`: `"connected"`, `"unconfigured"` ou `"failed"`
  - `provider`: `"nvidia_nim"` ou `"openrouter"`
  - `elapsed_ms`: Latência do ping em milissegundos.

---

## 4. Como Testar e Avaliar

### A. Via Terminal com Script de Avaliação / Benchmark
Execute o comando dedicado pelo prompt:
```cmd
run.bat nemotron-test
```
Ou com comparação lado a lado com a Groq LPU:
```cmd
run.bat nemotron-test --compare
```

### B. Por Voz no Aton
Com o Aton ativo no terminal ou em segundo plano:
- *"Aton, verifique a conexão com a Nemotron."*
- *"Aton, planeje uma rotina de contingência para backup de arquivos."*
- *"Aton, consulte a Nemotron sobre como estruturar este projeto."*

### C. Suíte de Testes Automatizados (Pytest)
```cmd
.venv\Scripts\python.exe -m pytest tests/test_nemotron_integration.py -v
```

---

## 5. Proteções de Segurança Implementadas
1. **Filtro de Gratuidade (`strict_free_tier`):** Bloqueio instantâneo caso um modelo pago sem `:free` seja requisitado no OpenRouter.
2. **Rate Limit com Cooldown (HTTP 429):** Espera mínima de 60 segundos respeitando o cabeçalho `Retry-After`.
3. **Sem Redirecionamento (`NoRedirect`):** Prevenção estrita contra man-in-the-middle e redirects HTTPS/HTTP.
4. **Sanitização de Credenciais:** Mensagens de erro e logs nunca expõem chaves de API.
