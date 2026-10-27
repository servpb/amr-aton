# Documentação: Palavra de Ativação e Push-to-Talk (wake_word)

## 1. Objetivo
O módulo **wake_word** é responsável por manter o assistente AMR em repouso com custo zero de internet/API, acordando-o instantaneamente assim que detectar a palavra-chave **"AMR"** no microfone ou quando o usuário acionar um atalho de emergência no teclado (*Push-to-Talk*).

---

## 2. Componentes

| Módulo | Arquivo | Responsabilidade |
| :--- | :--- | :--- |
| **Detector de Wake Word** | `src/audio/wake_word.py` | Executa inferência local offline em blocos de 80ms de áudio usando redes neurais ultraleves (`openWakeWord`). |
| **Push-to-Talk** | `src/audio/push_to_talk.py` | Fornece disparo manual via tecla de atalho configurável (`Ctrl + Espaço`), ignorando ruídos externos da sala. |

---

## 3. Características Técnicas

- **Custo de Operação:** 0% de chamadas de API do Google enquanto o assistente dorme. O áudio do microfone não sai da sua máquina.
- **Tamanho dos Blocos:** 1280 amostras PCM 16-bit (80ms a 16kHz).
- **Período de Cooldown (Anti-Repetição):** Padrão de 2 segundos após a palavra ser detectada, evitando que o assistente acerte múltiplos disparos para a mesma fala.
- **Limiar de Confiança (Threshold):** Padrão em 0.50 (ajustável para maior ou menor sensibilidade).

---

## 4. Como Testar

Para rodar os testes automatizados da palavra de ativação e push-to-talk:
```cmd
run.bat test
```
Ou diretamente:
```bash
pytest tests/test_wake_word.py
```
