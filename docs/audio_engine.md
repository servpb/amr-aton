# Documentação: Motor de Áudio (audio_engine)

## 1. Objetivo
O módulo de áudio do **Aton** é responsável por estabelecer a comunicação de som bidirecional em tempo real no Windows: capturar a fala do usuário através do microfone em blocos PCM com latência ultrabaixa e reproduzir respostas de voz do Gemini e bipes do sistema nos alto-falantes com recuperação automática e segura de falhas.

---

## 2. Componentes

| Módulo | Arquivo | Responsabilidade |
| :--- | :--- | :--- |
| **Gerenciador de Dispositivos** | `src/audio/device_manager.py` | Detecta, lista e seleciona os microfones e alto-falantes padrão do Windows. |
| **Reprodutor de Áudio** | `src/audio/player.py` | Executa fluxos de áudio PCM (respostas do Gemini Live), sintetiza bipes de acordar/dormir, gerencia concorrência com travas reentrantes (`_stream_lock`), detecta ponteiro de stream inválido (`PaErrorCode -9988`), purga filas antigas em falha e executa recuperação com cooldown delimitado. |
| **Gravador de Áudio** | `src/audio/recorder.py` | Captura o microfone continuamente em blocos PCM 16-bit (16 kHz mono) em segundo plano, com suporte a reinício suave (`reinit_portaudio=False`) sem derrubar streams de saída. |
| **Orquestrador de Áudio** | `src/core/assistant.py` | Propaga índices configurados de hardware (`AUDIO_INPUT_DEVICE_INDEX`, `AUDIO_OUTPUT_DEVICE_INDEX`), coordena reinicialização global segura (`recover_audio_subsystem`) e evita falso positivo de estado "falando" na bandeja quando a saída falhar. |

---

## 3. Especificações Técnicas de Áudio

- **Taxa de Amostragem (Entrada):** 16.000 Hz (padrão otimizado para o Gemini Live e para modelos de Wake Word).
- **Taxa de Amostragem (Saída):** 24.000 Hz (padrão de alta fidelidade para as vozes do Gemini Live).
- **Canais:** Mono (1 canal), reduzindo pela metade o consumo de banda e processamento.
- **Formato:** PCM linear 16-bit com sinal (`int16` / `float32`).
- **Tamanho do Bloco (Chunk Size):** 1280 amostras (80 ms de áudio), garantindo que o assistente reaja à fala humana sem atrasos perceptíveis.

---

## 4. Recursos Avançados e Resiliência de Áudio

### 4.1. Proteção Anti-Eco Acústico Estrita e Drenagem em Tempo Real (`drain_available_chunks`)
- A propriedade `player.is_playing` indica se áudio está sendo ativamente executado nos alto-falantes ou enfileirado na thread de reprodução contínua.
- Enquanto o Aton fala (`player.is_playing == True`) e durante a janela de reverberação de `0,45s` após o término da fala, o envio de áudio do microfone para o Gemini Live é totalmente bloqueado e o buffer gravado é descartado (`recorder.flush()` + `wake_detector.reset()`), impedindo que o alto-falante do notebook (RMS 2000–3200) auto-interrompa a resposta do Aton, mantendo apenas a escuta local do comando `"Pare"`.
- No turno do usuário, `recorder.drain_available_chunks()` agrupa imediatamente os blocos disponíveis na fila do microfone sem `asyncio.sleep(0.01)`, eliminando qualquer acúmulo de atraso na fila de captura.
- No acordar (`_wake_up`), o assistente aguarda fisicamente o término da execução do bipe e da saudação local antes de abrir o microfone para o Gemini Live, e executa `recorder.flush()` para descartar qualquer eco capturado durante a saudação.

### 4.2. Saudação Falada Instantânea da Voz Aoede (`play_greeting`)
- O arquivo `src/audio/assets/greeting_aoede.pcm` contém o áudio nativo em PCM 24.000 Hz da voz Aoede falando: *"Às suas ordens, senhor. Como posso ajudar?"*.
- O método `player.play_greeting()` reproduz essa frase instantaneamente com latência zero ao acordar, mantendo o canal do Gemini Live 100% puro para áudio bidirecional em tempo real.

### 4.3. Recuperação Segura de Áudio e Tratamento de Stream Inválido (`PaErrorCode -9988`)
- **Sincronização contra Concorrência:** O `AudioPlayer` utiliza trava reentrante (`self._stream_lock`) para sincronizar a escrita no worker (`_playback_worker`) com interrupções imediatas (`stop()`) e expirações de stream, impedindo que o fluxo seja fechado no meio de uma escrita.
- **Detecção e Descarte Imediato de Stream Inválido:** Ao encontrar `PaErrorCode -9988` (`Invalid stream pointer`), o ponteiro de stream é imediatamente descartado (`_discard_stream_unlocked()`), o estado de erro é registrado e o worker permanece vivo.
- **Recuperação Delimitada com Cooldown:** Em caso de falhas persistentes na saída, o reprodutor entra em cooldown de 5 segundos após 3 tentativas consecutivas (`MAX_CONSECUTIVE_WRITE_FAILURES = 3`), evitando repetições infinitas em logs.
- **Descarte de Áudio Antigo (Sem Replay Acumulado):** Ao detectar falha no stream, a fila de blocos pendentes é purgada (`clear_queue()`) e marcada como incerta (`_uncertain_chunk_dropped = True`), garantindo que respostas antigas interrompidas nunca sejam reexecutadas após a reconexão.
- **Watchdog Suave do Microfone:** O reinício periódico do microfone por inatividade (`recorder.restart(reinit_portaudio=False)`) atua de forma suave sem chamar `sd._terminate()`, preservando intactos os streams de reprodução do processo.
- **Recuperação Coordenada (`recover_audio_subsystem`):** Quando uma reinicialização global do PortAudio for estritamente necessária, o assistente drena e fecha ordenadamente o player (`prepare_for_subsystem_reinit`), para o gravador, reinicializa o subsistema e notifica o player (`on_subsystem_reinitialized`), evitando geração de ponteiros órfãos.
- **Propagação de Dispositivos de Hardware:** `AUDIO_INPUT_DEVICE_INDEX` e `AUDIO_OUTPUT_DEVICE_INDEX` configurados no `.env` são repassados aos construtores de `AudioRecorder` e `AudioPlayer`.
- **Fidelidade de Estado na Bandeja:** Se a saída de áudio falhar, o ícone da bandeja exibe estado de erro/recuperação (`audio_error`), jamais anunciando falsamente "Aton falando...".

---

## 5. Status de Validação e Homologação (Fase 17)

- **Conversação normal confirmada pelo usuário:** Teste de voz ao vivo realizado com sucesso, com áudio de resposta do Gemini Live reproduzido audivelmente e compreendido com clareza.
- **Comando "Pare" registrado nos logs:** Interrupção voluntária durante a fala registrada com sucesso em `logs/aton.log` (`Stop command detected, returning to SLEEPING`), encerrando o fluxo e retornando o assistente ao repouso.
- **Ausência de erro `-9988`:** Durante todo o episódio de teste e interação observado, não houve ocorrência de `PaErrorCode -9988` (`Invalid stream pointer`) nem travamento de worker.
- **Recuperação após falha coberta por testes simulados:** As rotinas de descarte de stream corrompido, cooldown de escrita, expurgo de chunks residuais sem repetição e reinício suave/coordenado foram validadas via testes unitários e de integração mockados (`tests/test_audio_recovery.py`), permanecendo **pendente de validação em hardware real** sob condições de falha física/desconexão induzida.
- **Ressalvas de Operação e Medição:**
  - Configurações e dispositivos de microfone do Windows mantidos inalterados conforme diretriz do usuário.
  - Não se classifica a interrupção como "instantânea" nem a concorrência entre threads como "comprovadamente perfeita" apenas com base nos carimbos de data/hora dos logs de eventos; uma caracterização definitiva exigiria medições específicas com instrumentação acústica e de estresse de hardware.

---

## 6. Como Testar

Para executar a bateria completa de testes automatizados do motor de áudio e recuperação:
```powershell
.venv\Scripts\python.exe -m pytest tests/test_audio_recovery.py tests/test_audio.py tests/test_system_audio.py -v
```
