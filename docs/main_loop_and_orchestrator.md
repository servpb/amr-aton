# Documentação: Loop Principal e Orquestrador (main_loop_and_orchestrator)

## 1. Objetivo
O **orquestrador principal** (`src/core/assistant.py`) é o maestro do assistente **AMR**. Ele integra todos os subsistemas de áudio (microfone e alto-falante), a detecção da palavra de ativação offline ("AMR") e a conexão WebSocket em tempo real com o Gemini Live, operando como uma máquina de estados robusta.

---

## 2. Máquina de Estados do AMR

```
       ┌──────────────┐
       │   SLEEPING   │ ◀────── Silêncio > CONVERSATION_TIMEOUT_SECONDS
       └──────┬───────┘
              │ Palavra "AMR" detectada (ou Push-to-Talk)
              ▼
       ┌──────────────┐
       │    WAKING    │  (Toca Bipe de Acordar, Conecta ao Gemini Live)
       └──────┬───────┘
              │ Conectado com sucesso
              ▼
       ┌──────────────┐
       │  CONVERSING  │ ──▶ Microfone envia áudio contínuo
       └──────┬───────┘ ◀── Alto-falante reproduz resposta do Gemini
              │
              │ Ctrl + C ou Shutdown
              ▼
       ┌──────────────┐
       │   SHUTDOWN   │  (Libera microfone, fecha conexões graciosamente)
       └──────────────┘
```

---

## 3. Componentes

| Módulo | Arquivo | Responsabilidade |
| :--- | :--- | :--- |
| **Orquestrador** | `src/core/assistant.py` | Gerencia os estados, o temporizador de silêncio contínuo e a troca entre escuta passiva e sessão Gemini Live. |
| **Ponto de Entrada** | `src/main.py` | Inicializa configurações, exibe o painel informativo no terminal e trata encerramentos com segurança (`Ctrl + C`). |
| **Testes de Ciclo de Vida** | `tests/test_assistant.py` | Valida transições de estado entre acordar, conversar, dormir e desligar. |

---

## 4. Como Executar no Windows

1. Certifique-se de que configurou sua chave no arquivo `.env` (conforme [docs/SETUP_CHECKLIST.md](file:///c:/xampp/htdocs/amr/docs/SETUP_CHECKLIST.md)).
2. Na pasta raiz do projeto, execute o script:
   ```cmd
   run.bat
   ```
3. O terminal exibirá:
   ```text
   ============================================================
            AMR - Assistente Pessoal Inteligente
   ============================================================
    [Voz]: Aoede
    [Modelo Live]: gemini-2.0-flash-exp
    [Palavra-Chave]: 'amr'
    [Tempo de Conversa]: 7s de silencio
   ------------------------------------------------------------
    >> Diga 'AMR' no microfone para conversar.
    >> Pressione Ctrl + C para encerrar.
   ============================================================
   ```
4. Fale *"AMR"* no microfone. Você ouvirá o bipe harmônico de ativação e poderá conversar diretamente com ele.

---

## 5. Como Testar

Para rodar os testes automatizados do orquestrador:
```cmd
run.bat test
```
Ou diretamente:
```bash
pytest tests/test_assistant.py
```
