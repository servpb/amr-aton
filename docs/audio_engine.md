# Documentação: Motor de Áudio (audio_engine)

## 1. Objetivo
O módulo de áudio do **AMR** é responsável por estabelecer a comunicação de som bidirecional em tempo real no Windows: capturar a fala do usuário através do microfone em blocos PCM com latência ultrabaixa e reproduzir respostas de voz do Gemini e bipes do sistema nos alto-falantes.

---

## 2. Componentes

| Módulo | Arquivo | Responsabilidade |
| :--- | :--- | :--- |
| **Gerenciador de Dispositivos** | `src/audio/device_manager.py` | Detecta, lista e seleciona os microfones e alto-falantes padrão do Windows. |
| **Reprodutor de Áudio** | `src/audio/player.py` | Executa fluxos de áudio PCM (respostas do Gemini Live), sintetiza bipes de acordar/dormir e suporta interrupção imediata. |
| **Gravador de Áudio** | `src/audio/recorder.py` | Captura o microfone continuamente em blocos PCM 16-bit (16 kHz mono) em segundo plano. |

---

## 3. Especificações Técnicas de Áudio

- **Taxa de Amostragem (Entrada):** 16.000 Hz (padrão otimizado para o Gemini Live e para modelos de Wake Word).
- **Taxa de Amostragem (Saída):** 24.000 Hz (padrão de alta fidelidade para as vozes do Gemini Live).
- **Canais:** Mono (1 canal), reduzindo pela metade o consumo de banda e processamento.
- **Formato:** PCM linear 16-bit com sinal (`int16` / `float32`).
- **Tamanho do Bloco (Chunk Size):** 1280 amostras (80 ms de áudio), garantindo que o assistente reaja à fala humana sem atrasos perceptíveis.

---

## 4. Bipes de Confirmação Sintetizados (Sem arquivos externos)

Para evitar dependência de arquivos `.wav` ou `.mp3` no disco que poderiam ser perdidos ou corrompidos, o `AudioPlayer` sintetiza bipes harmônicos via matemática (`numpy`):
- **Bipe de Acordar (`play_wake_chime`):** Dois tons ascendentes suaves (660 Hz seguido de 880 Hz) com envelope trapezoidal que elimina ruídos de clique.
- **Bipe de Dormir (`play_sleep_chime`):** Dois tons descendentes suaves (880 Hz seguido de 587 Hz) avisando que o assistente voltou ao modo de repouso.

### 4.1. Proteção Anti-Eco Acústico (Acoustic Echo Suppression)
- A propriedade `player.is_playing` indica se áudio está sendo ativamente executado nos alto-falantes ou enfileirado na thread de reprodução contínua.
- Enquanto o Aton fala, a transmissão do microfone é temporariamente suprimida (a menos que o usuário eleve o volume para RMS >= 2000, indicando interrupção deliberada), evitando que o microfone capture o som do alto-falante e corte a fala do modelo precocemente.
- No acordar (`_wake_up`), o assistente aguarda fisicamente o término da execução do bipe e da saudação local antes de abrir o microfone para o Gemini Live, e executa `recorder.flush()` para descartar qualquer eco capturado durante a saudação.

### 4.2. Saudação Falada Instantânea da Voz Aoede (`play_greeting`)
- O arquivo `src/audio/assets/greeting_aoede.pcm` contém o áudio nativo em PCM 24.000 Hz da voz Aoede falando: *"Às suas ordens, senhor. Como posso ajudar?"*.
- O método `player.play_greeting()` reproduz essa frase instantaneamente com latência zero ao acordar, mantendo o canal do Gemini Live 100% puro para áudio bidirecional em tempo real.

---

## 5. Como Testar

Para executar a bateria de testes automatizados do motor de áudio:
```cmd
run.bat test
```
Ou diretamente:
```bash
pytest tests/test_audio.py
```
