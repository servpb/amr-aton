# Integração Groq LPU (Inferência Ultra-Rápida)

Este documento detalha a implementação e integração da API Groq LPU no assistente **Aton**, permitindo inferência de texto com ultra-baixa latência (300ms a 1.5s), geração de respostas, raciocínio e fallback inteligente a custo zero na camada gratuita oficial da Groq.

---

## 1. Visão Geral e Arquitetura

A Groq utiliza unidades de processamento de linguagem (LPUs - Language Processing Units) especializadas em inferência em tempo recorde. No Aton, essa integração atua como:
- **Motor de Raciocínio & Respostas Rápidas:** Processamento de instruções de texto, resumos, formatações e respostas conversacionais com velocidade extrema.
- **Fallback Inteligente:** Contingência pronta para quando serviços externos estiverem em limite de requisições ou indisponíveis.
- **Transparência e Custo Zero:** Uso exclusivo dos modelos e limites gratuitos oficiais oferecidos pela Groq, sem bibliotecas pesadas e sem dependências externas adicionais (usando biblioteca padrão `urllib.request`).

---

## 2. Modelos Disponíveis e Suportados

Os modelos oficiais ativos na conta Groq:
- `openai/gpt-oss-20b` (Padrão e Ultra-rápido: balanceamento ideal entre inteligência e velocidade de resposta na LPU).
- `openai/gpt-oss-120b` (Raciocínio Avançado: modelo maior para análises e tarefas complexas).
- `qwen/qwen3.8-27b` (Multilíngue: excelente suporte textual e conhecimento geral).
- `whisper-large-v3` e `whisper-large-v3-turbo` (Transcrição de áudio em tempo real).

---

## 3. Configuração Local (`.env`)

A chave de API fica armazenada com segurança estrita no `.env` (nunca versionada no Git):

```env
# Groq LPU API Configuration
GROQ_API_KEY=gsk_...
GROQ_MODEL=openai/gpt-oss-20b
GROQ_ENABLED=true
GROQ_TIMEOUT_SECONDS=15
```

---

## 4. Ferramentas Integradas (Tool Calling)

### A. `query_groq_llm`
Executa consultas de inteligência artificial de alta velocidade.
- **Parâmetros:**
  - `prompt` (*string, obrigatório*): Instrução, pergunta ou texto a processar.
  - `system_prompt` (*string, opcional*): Persona ou instruções específicas de comportamento.
  - `model` (*string, opcional*): Modelo Groq desejado (padrão: `openai/gpt-oss-20b`).
- **Retorno:**
  - `status`: `"success"` ou `"error"`
  - `content`: Texto gerado pelo modelo.
  - `model`: Modelo utilizado.
  - `elapsed_ms`: Tempo de resposta em milissegundos.
  - `usage`: Contagem de tokens (prompt, completion, total).

### B. `check_groq_connection`
Verifica a saúde da API, latência de rede e status da chave.
- **Retorno:**
  - `status`: `"connected"`, `"unconfigured"` ou `"failed"`
  - `elapsed_ms`: Latência do ping em milissegundos.
  - `model`: Modelo respondente.

---

## 5. Como Testar e Diagnosticar

### A. Via Linha de Comando (CLI)
Para executar o teste em tempo real com sua chave do `.env`:

```bash
run.bat groq-test
```
Ou diretamente pelo Python da virtualenv:
```bash
.venv\Scripts\python.exe scripts\testar_groq.py
```

### B. Suíte de Testes Automatizados (Pytest)
Para rodar a suíte completa com mocks de rede e isolamento de falhas:

```bash
.venv\Scripts\python.exe -m pytest tests/test_groq_integration.py tests/test_groq_pilot.py tests/test_config.py -v
```

---

## 6. Tratamento de Erros e Proteções
1. **Rate Limiting (HTTP 429):** Cooldown automático mínimo de 60 segundos respeitando o cabeçalho `Retry-After`.
2. **Sanitização de Chaves:** Em caso de erro HTTP (ex: 401/403/500) ou timeout, o corpo da requisição e a chave nunca são expostos em logs ou mensagens ao usuário.
3. **Redirecionamento Bloqueado:** Proteção estrita contra redirects não autorizados (`NoRedirect`).
4. **Isolamento de Falha:** Erros na API Groq não afetam o loop de voz ou outras ferramentas do assistente.

