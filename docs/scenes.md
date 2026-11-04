# Rotinas e Cenas Multi-Módulo Verificadas e Personalizadas por Voz (`src/tools/scenes.py`)

## 1. Objetivo
O módulo **Rotinas e Cenas Multi-Módulo Verificadas e Personalizadas por Voz** permite que o **Aton** execute ações coordenadas entre diversos módulos do assistente (Google Agenda, Google Tasks, Gmail, YouTube, Telemetria/Áudio/Apps do Windows, Monitor Proativo, Timers e Fire TV Stick) a partir de um único comando de voz, além de permitir que o usuário **crie, armazene e exclua novas rotinas personalizadas por voz** com confirmação obrigatória em duas fases e verificação real do resultado de cada etapa.

---

## 2. Garantias Arquiteturais e de Segurança Implementadas

1. **Execução Independente por Etapa (*Fault Isolation*):**
   - Cada etapa da cena roda de forma isolada em `_run_step_isolated()`. Uma falha no Fire TV Stick, no Gmail ou em qualquer outro serviço externo **nunca interrompe** as demais ações da cena.
2. **Verificação Real em 3 Níveis (`confirmed`, `sent_unverified`, `failed`):**
   - `confirmed`: Ação executada **e confirmada por leitura de estado** (ex.: leitura do volume do Windows via `pycaw` batendo com o alvo; flag `dnd_mute_sound` lida do SQLite; pacote do YouTube confirmado em primeiro plano via ADB `dumpsys window windows` no Fire TV Stick; ou retorno validado das APIs Google).
   - `sent_unverified`: Comando enviado ou dispositivo conectado, mas **sem confirmação final do estado** (ex.: `launch_fire_tv_app` retornou `inconclusive` / `confirmed=False` com `action_sent=True`; envio de tecla virtual multimídia `VK_MEDIA_STOP` ao Windows; ou `close_application` enviou `WM_CLOSE`, mas o processo permaneceu aberto aguardando salvamento de documento).
   - `failed`: Dispositivo desconectado, erro de API ou tempo limite excedido.
3. **Confirmação em Duas Fases Vinculada à Proposta (`SceneConfirmationManager`):**
   - Criar (`propor_cena_personalizada`), excluir (`remover_cena_personalizada`) ou executar uma rotina personalizada com ação sensível (`fechar_app_pc`) gera um `proposal_id` vinculado à sessão de voz atual com validade estrita de **60 segundos** (`PROPOSAL_TTL_SECONDS = 60.0`).
   - O token é de **uso único** (confirmações duplicadas retornam `duplicate_confirmation`) e novas propostas na mesma sessão invalidam propostas anteriores (`proposal_superseded`).
4. **Catálogo Autorizado e Proteção de Aplicativos (`ALLOWED_CUSTOM_STEP_TYPES` & `ALLOWED_APP_IDENTIFIERS`):**
   - Nenhuma rotina personalizada pode executar comandos arbitrários do sistema operacional, scripts shell ou caminhos de arquivos.
   - Abertura e fechamento de programas no Windows são restritos aos identificadores autorizados (`chrome`, `edge`, `firefox`, `brave`, `notepad`, `calculadora`, `paint`, `vscode`, `spotify`, etc.), bloqueando terminais (`cmd`, `powershell`, `regedit`, `taskmgr`) e impedindo o fechamento do `explorer` (shell do Windows).
   - A ação `fechar_app_pc` é classificada como **sensível (`is_sensitive = True`)**, emite alerta explícito sobre o **risco de perda de documentos não salvos** e exige confirmação específica antes da execução.
5. **Persistência Transacional Confiável em SQLite (`custom_scenes`):**
   - Uso de transações SQLite (`with conn:`), `slug` único normalizado (`slug TEXT PRIMARY KEY`) e proteção estrita das 5 cenas nativas (`bom_dia`, `modo_cinema`, `modo_foco`, `boa_noite`, `restaurar`) contra sobrescrita ou exclusão.
   - Os timers criados pelas rotinas utilizam o `ReminderStore` persistente em `data/reminders.sqlite3`, sobrevivendo à reinicialização do Aton.
6. **Preservação e Restauração de Estado (`scene_state_snapshots`):**
   - Antes de qualquer cena nativa ou personalizada alterar o volume do PC ou o som dos avisos proativos, o estado original é salvo no SQLite sem alterar o horário de silêncio permanente (`23:00–07:00`).
   - `restaurar_cena` restaura o volume e os avisos anteriores com confirmação de leitura.

---

## 3. Cenas Nativas Protegidas

| Cena (`nome_cena`) | Apelidos de Voz | Etapas Executadas |
| :--- | :--- | :--- |
| **`bom_dia`** | `iniciar_expediente`, `resumo_da_manha` | 1. Compromissos de hoje no Google Agenda<br>2. Tarefas pendentes no Google Tasks<br>3. E-mails não lidos no Gmail<br>4. Telemetria de CPU, RAM e bateria do Windows |
| **`modo_cinema`** | `cinema`, `filme` | 1. Salva snapshot SQLite do estado anterior<br>2. Silencia som dos avisos proativos da agenda<br>3. Reduz volume do Windows para 20% (com confirmação de leitura)<br>4. Abre YouTube no Fire TV Stick (verificando pacote em 1º plano) |
| **`modo_foco`** | `foco`, `concentracao`, `modo_trabalho` | 1. Salva snapshot SQLite do estado anterior<br>2. Silencia som dos avisos proativos da agenda<br>3. Envia parada de mídia ao Windows (`VK_MEDIA_STOP`)<br>4. Cria timer persistente de foco (padrão: 45 min) |
| **`boa_noite`** | `encerrar_expediente`, `encerrar_dia` | 1. Salva snapshot SQLite do estado anterior<br>2. Silencia som dos avisos proativos da agenda<br>3. Envia parada de mídia ao Windows<br>4. Consulta compromissos de amanhã no Google Agenda |
| **`restaurar`** | `restaurar_cena`, `sair_modo`, `normal` | 1. Restaura configuração anterior dos avisos proativos<br>2. Restaura volume anterior do Windows a partir do snapshot SQLite |

---

## 4. Ações Autorizadas para Rotinas Personalizadas (`ALLOWED_CUSTOM_STEP_TYPES`)

- `silenciar_avisos` / `ativar_avisos`
- `ajustar_volume_pc` (`nivel`: `0` a `100`)
- `pausar_midia_pc`
- `abrir_app_pc` (`aplicativo` autorizado)
- `fechar_app_pc` (`aplicativo` autorizado — **ação sensível com confirmação e aviso de documentos não salvos**)
- `abrir_app_fire_tv` (`aplicativo`: `youtube`, `netflix`, `prime_video`, `disney`, `spotify`, `globoplay`, `max`, `crunchyroll`)
- `criar_timer` (`minutos`: `1` a `720`, `titulo` opcional)
- `consultar_agenda_hoje` / `consultar_agenda_amanha`
- `consultar_tarefas` / `consultar_emails` / `consultar_telemetria_pc` / `consultar_canal_youtube`

---

## 5. Ferramentas de Voz (*Tool Calling* — 6 ferramentas)
- `executar_cena(nome_cena, duracao_foco_minutos=45, app_tv="youtube", volume_cinema=20)`
- `restaurar_cena()`
- `listar_cenas()`
- `propor_cena_personalizada(nome_cena, etapas, descricao=None)`
- `confirmar_rotina_personalizada(proposal_id)`
- `remover_cena_personalizada(nome_cena)`

---

## 6. Como Testar (12 Testes Automatizados Sem Dispositivos Reais)
```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_scenes.py -v
```
