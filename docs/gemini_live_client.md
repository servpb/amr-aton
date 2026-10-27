# Documentação: Cliente Gemini Live em Tempo Real (gemini_live_client)

## 1. Objetivo
O módulo **gemini_live_client** estabelece a conexão WebSocket bidirecional em tempo real com a **Gemini Multimodal Live API** do Google (via SDK oficial `google-genai`), permitindo conversação por voz de ultrabaixa latência, interrupção natural e emissão de chamadas de ferramentas (*Tool Calling*).

---

## 2. Componentes

| Módulo | Arquivo | Responsabilidade |
| :--- | :--- | :--- |
| **Instruções do Sistema (Prompt)** | `src/core/prompts.py` | Define a personalidade do AMR em Português do Brasil: prestativo, polido, conciso, formatado para áudio natural (sem markdown visual). |
| **Cliente Gemini Live** | `src/core/live_client.py` | Gerencia a sessão WebSocket bidirecional, envio de PCM do microfone e streaming de áudio de resposta. |

---

## 3. Especificações da Sessão Gemini Live

- **SDK Utilizado:** `google-genai` (SDK oficial unificado do Google).
- **Modelo:** `gemini-3.1-flash-live-preview` (ou configurável via variável de ambiente `GEMINI_LIVE_MODEL`).
- **Modalidade:** Áudio de entrada (`audio/pcm;rate=16000` mono 16.000 Hz) e áudio de saída em tempo real (`audio/pcm` mono 24.000 Hz).
- **Voz Pré-Construída:** `Aoede` (ou configurável via `GEMINI_VOICE_NAME`, voz fluente em pt-BR).
- **Streaming Contínuo Multiturnos:** Utiliza `session.send_realtime_input(audio=Blob(data=..., mime_type="audio/pcm;rate=16000"))` com laço persistente `while self._is_connected:` em `receive_stream()`, garantindo que todas as perguntas faladas em turnos sucessivos sejam processadas e respondidas por áudio.
- **Transcrição Falada:** Captura opcional de `part.text` para exibir no console a transcrição em tempo real do que o Aton está dizendo por voz.
- **Manipulação de Ferramentas:** Intercepta eventos `tool_call` enviados pelo modelo e dispara callbacks assíncronos para o worker em segundo plano sem travar a fala.

---

## 4. Como Testar

Para rodar os testes automatizados do cliente Gemini Live:
```cmd
run.bat test
```
Ou diretamente:
```bash
pytest tests/test_live_client.py
```
