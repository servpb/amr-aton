# Documentação: Ciclo de Vida de Inicialização Rápida, Prontidão Honesta e Calibração do Wake Word

## 1. Visão Geral
Esta documentação detalha a arquitetura de inicialização de alta performance do assistente **Aton** no Windows, a hierarquia de estados visuais na bandeja do sistema (*System Tray*), a eliminação de ativações indevidas por palavras comuns cotidianas e o protocolo de instrumentação métrica de tempo real.

O objetivo desta engenharia é resolver dois comportamentos críticos:
1. **Eliminar o atraso percebido ao entrar no Windows:** Subir a presença visual e a escuta local do microfone em poucos segundos pós-login, sem travar o interpretador com importações pesadas e síncronas.
2. **Eliminar despertares espontâneos:** Expurgar palavras do vocabulário cotidiano da lista de gatilhos do Vosk e restringir resultados parciais (*PartialResult*) para evitar disparos indevidos por conversas paralelas ou áudio de televisão.

---

## 2. Arquitetura em Dois Estágios (Fast Boot + Background Warm-up)

```
[Login do Windows / Execução]
              │
              ▼
    1. Subida Imediata (<1s)
       - setup_logging() UTF-8
       - _ensure_single_aton_instance() (prevenção de 2 vozes)
       - AtonSystemTray criado com estado 'initializing' (Âmbar)
              │
              ▼
    2. Ativação do Hardware Local (T1: ~1s a 3s)
       - AudioRecorder.start() (abertura do microfone PortAudio)
       - WakeWordDetector com Vosk local
       - Bandeja migra para 'local_listening' (Ciano)
       - Registro métrico: T1_local_listening_ready_ms
              │
              ▼
    3. Background Warm-up Desacoplado (T2: ~4s a 8s)
       - Thread nativa com prioridade reduzida (THREAD_PRIORITY_BELOW_NORMAL)
       - Carga tardia (lazy loading) das 68 ferramentas (src.tools)
       - Inicialização do cliente Gemini Live e Gateway
       - Bandeja migra para 'ready' (Cinza/Verde)
       - Registro métrico: T2_conversation_ready_ms
```

---

## 3. Estados Transparentes na Bandeja do Windows

A bandeja do sistema (`AtonSystemTray`) reflete com fidelidade técnica o estado real dos subsistemas:

| Estado Interno | Cor do Ícone | Tooltip na Barra de Tarefas | Significado Técnico |
| :--- | :--- | :--- | :--- |
| **`initializing`** | Âmbar / Amarelo | *"Aton: Inicializando processo e hardware..."* | Processo Python subindo; microfone e modelo acústico ainda não finalizaram a abertura. |
| **`local_listening`** | Ciano / Azul Claro | *"Aton: Escuta local ativa (carregando componentes)..."* | Microfone aberto e Vosk ouvindo ativamente. Se chamado aqui, dá o retorno breve de inicialização. |
| **`ready` / `sleeping`** | Verde / Cinza | *"Aton: Pronto para conversar (diga 'Aton')"* | Todos os componentes (Gemini Live, 68 ferramentas e Gateway) 100% carregados e disponíveis para conversa imediata. |
| **`mic_error`** | Vermelho Alerta | *"Aton: Falha no microfone (tentando reconectar...)"* | Watchdog detectou falta de entrega de áudio pelo driver do Windows pós-boot ou pós-suspensão. |
| **`init_error`** | Vermelho Escuro | *"Aton: Falha ao carregar componentes secundários"* | Erro no pré-aquecimento; menu de contexto libera a opção *"🔄 Tentar Recarregar Componentes"*. |

---

## 4. Comportamento de Chamada Durante a Inicialização (Intervalo entre T1 e T2)

Se o usuário pronunciar *"Aton"* enquanto as ferramentas ainda estiverem em fase de carga (`_is_warmup_complete == False`):
1. **Aviso Sonoro Local Imediato:** O assistente emite o chime harmônico de atenção imediatamente através do `player.play_wake_chime()`.
2. **Descarte Atômico e Contínuo de Backlog (`clear_backlog`):** O buffer de áudio do microfone é esvaziado (`recorder.clear_backlog(keep_latest=0)` e `recorder.flush()`), garantindo que nenhuma fala dita no passado seja acumulada para execução tardia.
3. **Prevenção de Sessões Duplicadas:** O Aton não abre conexão incompleta com o Gemini Live nem cria filas fantasmas. Ele aguarda a conclusão do warm-up para aceitar a próxima ativação limpa em tempo real.

---

## 5. Calibração Fonética e Supressão de Falsos Positivos

### Termos Removidos Definitivamente
Foram expurgados de `wake_tokens` e `wake_phrases` todos os vocábulos comuns que provocavam disparos acidentais comprovados no histórico de logs:
- `batom`, `adão`, `avon`, `o pão`, `a bom`, `a dom`, `o tom`, `o tão`, `átomo`, `atum`, `atuns`, `atam`, `a tomar escuta`, `a toma escuta`, `estava a escuta`.
- Termos ambíguos como `ayrton`, `eaton`, `atom` foram retirados da lista permissiva aberta.

### Tokens e Saudações Legítimas Preservadas
- **Tokens canônicos oficiais:** `"aton"`, `"áton"`, `"atón"`, `"atão"`, `"atao"`.
- **Saudações canônicas completas:** `"oi aton"`, `"olá aton"`, `"ei aton"`, `"ok aton"`, `"opa aton"`, `"alô aton"`.

### Variantes Fonéticas Secundárias ('tom', 'atom', 'átom')
Devido à fonética nasal do português brasileiro e às limitações léxicas do modelo pequeno do Vosk (`vosk-model-small-pt-0.3`), locuções de "Aton" podem ser transcritas como `'tom'` ou `'atom'` (com **M**).
Para garantir atendimento sem abrir brechas para falsos positivos em conversas ou televisão:
- **No `PartialResult` (resultado transitório):** As variantes `'tom'`, `'atom'` e `'átom'` são **100% rejeitadas** (nunca avaliadas em parciais), evitando qualquer disparo antecipado no início de locuções cotidianas como *"tom de voz"* ou *"tomara"*.
- **No `Result` final (`AcceptWaveform` consolidado):** Aceitas **única e exclusivamente por correspondência exata da locução completa** com a palavra isolada ou saudação explícita permitida:
  - Palavras isoladas exatas: `"tom"`, `"atom"`, `"átom"`.
  - Saudações explícitas exatas: `"oi tom"`, `"ei tom"`, `"olá tom"`, `"ok tom"`, `"opa tom"`, `"alô tom"`, `"oi atom"`, `"olá atom"`, etc.
  - Frases conversacionais com artigos ou complementos (ex.: *"o tom de voz"*, *"no tom certo"*, *"não eram as habilidades atom"*) são **100% rejeitadas** por não coincidirem com as saudações exatas.

### Critério Determinístico entre Parciais e Finais
- **No `PartialResult` (resultado transitório a cada 80ms):**
  Só dispara se o texto transcrito parcial for **exclusivamente e estritamente** a palavra-chave isolada (`text in strict_wake_tokens` ou `text in strict_direct_phrases`). Fragmentos de frases de conversas cotidianas ouvidos na sala **nunca** acionam o Aton em modo parcial.
- **No `Result` final (`AcceptWaveform` consolidado):**
  Dispara se contiver a palavra isolada dentro de uma locução curta ($\le 6$ palavras), descartando discursos longos de TV, rádio ou conversas com terceiros.

---

## 6. Métricas de Performance Registradas nos Logs

O assistente cronometra quatro marcos com precisão de milissegundos via `time.perf_counter()`:

1. **`T1 (Escuta Local):`** Registrado como `[BOOT_METRIC] T1_local_listening_ready_ms`. Tempo até o microfone estar gravando e o Vosk ouvindo.
2. **`T2 (Conversa Pronta):`** Registrado como `[BOOT_METRIC] T2_conversation_ready_ms`. Tempo até as 68 ferramentas e o cliente Gemini Live estarem 100% instanciados.
3. **`T3 (Primeira Resposta Falada):`** Registrado como `[PERF_METRIC] T3_first_spoken_response_ms`. Intervalo entre a chamada do usuário e o primeiro chunk de áudio da voz do Aton emitido.
4. **`T4 (Conclusão da Primeira Ferramenta):`** Registrado como `[PERF_METRIC] T4_first_tool_completed_ms`. Intervalo entre a chamada e a conclusão de execução da ferramenta solicitada.

---

## 7. Como Validar e Testar

### A. Executar Testes Automatizados
```cmd
.\.venv\Scripts\pytest.exe tests/test_wake_word.py tests/test_boot_lifecycle.py tests/test_assistant.py tests/test_system_tray.py -v
```

### B. Procedimento de Teste Real no Windows
1. **Reinicialização do Sistema:**
   - Reinicie o Windows ou faça Logoff/Login.
   - Observe a bandeja do sistema perto do relógio: o ícone deve surgir em poucos segundos na cor **âmbar** (*Inicializando*), migrar rapidamente para **ciano** (*Escuta local ativa*) e em seguida para **verde/cinza** (*Pronto para conversar*).
2. **Auditoria de Logs:**
   - Abra `logs/aton.log` e confira as linhas `[BOOT_METRIC] T1_...` e `[BOOT_METRIC] T2_...`.
3. **Teste de Sensibilidade:**
   - Fale *"Aton"* ou *"Oi Aton"* em tom de voz natural e confirme a saudação imediata.
4. **Amostra de Rejeição de Ruído:**
   - Deixe televisão ou conversa ambiente rodando por 10 a 15 minutos sem pronunciar *"Aton"* e verifique se o assistente permanece repousado sem acordar sozinho.
5. **Teste pós-suspensão:**
   - Suspenda o computador (Sleep), reative-o e fale *"Aton"* para validar a recuperação automática do microfone pelo watchdog.

