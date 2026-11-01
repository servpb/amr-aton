# Documentação: Palavra de Ativação ("Aton"), Push-to-Talk e Inicialização Automática

## 1. Objetivo
O módulo **wake_word** é responsável por manter o assistente ATON em repouso permanente no Windows com **custo zero de nuvem e mínimo consumo de CPU**, acordando-o instantaneamente apenas quando o usuário pronunciar claramente a palavra-chave **"Aton"** ou acionar o atalho global (*Push-to-Talk*).

Antes de ouvir "Aton", a aplicação **rejeita conversas normais de ambiente, ruídos, músicas, vídeos e sons aleatórios**, permanecendo silenciosa e passiva na bandeja do sistema (*System Tray*).

---

## 2. Componentes e Arquivos

| Módulo | Arquivo | Responsabilidade |
| :--- | :--- | :--- |
| **Detector de Wake Word** | `src/audio/wake_word.py` | Executa inferência local offline em blocos de 80ms PCM 16kHz utilizando **Vosk** (`vosk-model-small-pt-0.3`) e **openWakeWord**. Identifica especificamente o token *"aton"* (e variações fonéticas como *"áton"*). |
| **Push-to-Talk** | `src/audio/push_to_talk.py` | Disparo manual imediato via tecla de atalho (`Ctrl + Espaço`), ignorando ruídos externos da sala. |
| **Launcher Silencioso** | `launch_aton_background.vbs` | Script VBScript que inicia `pythonw.exe -m src.main` com `WindowStyle = 0` (invisível, sem janelas pretas de terminal). |
| **Ativador de Inicialização** | `scripts/ativar_inicializacao_windows.bat` | Cria atalho `.lnk` na pasta de Inicialização do Windows do usuário atual (`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`), 100% reversível e sem necessidade de permissões de administrador. |
| **Desativador de Inicialização** | `scripts/desativar_inicializacao_windows.bat` | Remove com um clique o atalho `ATON.lnk` da pasta de inicialização do Windows. |
| **Gerenciador de Execução** | `run.bat` | Comandos rápidos: `run.bat bg` (inicia em segundo plano), `run.bat autostart-on` (ativa autostart), `run.bat autostart-off` (desativa autostart), `run.bat status` (diagnóstico do processo e autostart), `run.bat stop` (encerra processos). |

---

## 3. Características Técnicas

- **Custo de Operação:** 0% de chamadas de API ou rede enquanto o assistente dorme. O áudio do microfone não sai da máquina local.
- **Reconhecimento Offline Exato (Vosk):** Modelo local em português de 30.9 MB (`vosk-model-small-pt-0.3`) cacheado em disco. O motor transcreve continuamente pequenos blocos de áudio e busca estritamente pela pronúncia canônica de *"Aton"* (`aton`, `áton`, `atón`, `atão`, `atao`) ou saudações diretas (`oi aton`, `olá aton`, `ei aton`, `ok aton`, `opa aton`, `alô aton`). Variantes acústicas secundárias com nasalização brasileira (`tom`, `atom`, `átom` e respectivas saudações) são aceitas **exclusivamente em resultado final consolidado por correspondência exata de frase completa**, sendo 100% rejeitadas em parciais e em frases conversacionais (`o tom de voz`). Vocábulos cotidianos como `batom`, `adão`, `avon`, `o pão`, `a bom` foram expurgados para evitar ativações indevidas. Modelos genéricos em inglês do `openWakeWord` são mantidos desativados.
- **Comando de Parada Imediata ("Pare"):** Enquanto o Aton está no estado `CONVERSING` (ouvindo ou falando), o método `detect_stop_command(pcm_bytes)` monitora localmente a palavra **"Pare"** (ou *"Parar"* / *"Aton, pare"*). Ao detectar **"Pare"**, o Aton interrompe imediatamente qualquer fala em andamento (`player.stop()`), fecha a sessão ativa do Gemini Live, emite o bipe de repouso e retorna ao estado `SLEEPING`.
- **Estabilidade no Boot do Windows:**
  - O launcher `launch_aton_background.vbs --boot` aguarda 3 segundos no login para estabilização do serviço de áudio do Windows e da barra de tarefas (`explorer.exe`), além de evitar processos duplicados.
  - Caso o driver de microfone demore a subir no boot, o loop principal tenta reconectar o microfone automaticamente a cada 5 segundos.
  - Todos os eventos em segundo plano são registrados em UTF-8 no arquivo `logs/aton.log`, evitando falhas de `stdout`/`stderr` no `pythonw.exe`.
  - O Aton inicia 100% silencioso em repouso e só entra em operação quando o usuário pronuncia **"Aton"**.
- **Tamanho dos Blocos:** 1280 amostras PCM 16-bit (80ms a 16kHz).
- **Período de Cooldown (Anti-Eco/Repetição):** Padrão de 2.0 segundos após o despertar, evitando disparos repetidos para a mesma fala.
- **Modo Residente no Windows:**
  - O ATON roda com `pythonw.exe` e posiciona um ícone na bandeja do sistema (perto do relógio).
  - Ícone azul/verde indica status "Em repouso (Aguardando 'Aton')".
  - Clique com botão direito exibe menu de contexto: "Status", "Ativar por Voz" e "Encerrar Aton".
- **Fluxo de Conversação Contínua:**
  1. Ao ouvir "Aton", o assistente emite uma saudação e abre o canal de conversação em tempo real (Gemini Live).
  2. O usuário faz perguntas e comandos sem precisar repetir "Aton".
  3. Após concluir a tarefa ou silêncio prolongado, o Aton fecha a sessão do Gemini Live e volta automaticamente ao modo de espera na bandeja.

---

## 4. Comandos de Gerenciamento

### Iniciar Silenciosamente em Segundo Plano (Manual)
```cmd
run.bat bg
```

### Ativar Inicialização Automática com o Windows
```cmd
run.bat autostart-on
```
*(Ou execute com duplo clique: `scripts\ativar_inicializacao_windows.bat`)*

### Desativar Inicialização Automática com o Windows
```cmd
run.bat autostart-off
```
*(Ou execute com duplo clique: `scripts\desativar_inicializacao_windows.bat`)*

### Verificar Status
```cmd
run.bat status
```

### Encerrar o Aton
- Opção 1: Clique com o botão direito no ícone do ATON na bandeja do sistema e selecione **"Encerrar Aton"**.
- Opção 2: Execute no terminal:
  ```cmd
  run.bat stop
  ```

---

## 5. Como Testar os Testes Unitários

Para validar a suíte de testes do wake word (incluindo rejeição de ruído ambiente e disparo por fala):
```cmd
.\.venv\Scripts\pytest.exe tests/test_wake_word.py
```
