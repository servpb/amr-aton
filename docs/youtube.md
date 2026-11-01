# Integração Multi-Contas e Multi-Canais com YouTube (YouTube Data API v3 & YouTube Analytics API v2)

## 1. Objetivo
O módulo de integração com o YouTube permite que o assistente **Aton** conecte e gerencie múltiplos canais do YouTube associados a múltiplas contas Google (como `cursopb@gmail.com` e `servpb@gmail.com`, além da verificação explícita do canal **`UCYCmXtIR-tbWCyrwbLdczyA`**), usando **OAuth 2.0 para Aplicativo Desktop**.

O módulo oferece:
- **Isolamento total das credenciais do Gmail:** Os tokens do YouTube são armazenados em arquivos próprios (`tokens/youtube_acct_<sha256_64>.json`) e indexados em `tokens/youtube_channels_index.json`, sem tocar em `tokens/gmail_acct_*.json` ou `tokens/accounts_index.json`.
- **Identificação composta por `(conta, canal)`:** Permite autenticar múltiplos canais/Contas de Marca (*Brand Accounts*) sob o mesmo endereço de e-mail Google sem sobrescrever tokens anteriores.
- **Consultas completas:** Listagem de canais, estatísticas separadas entre **YouTube Data API v3** (totais acumulados) e **YouTube Analytics API v2** (relatórios de período com fuso `America/Sao_Paulo` e aviso de latência variável), listagem de vídeos e detalhes, e leitura de comentários públicos compatível com escopo somente leitura (`youtube.readonly`).
- **Gerenciamento com confirmação estrita em 2 etapas no servidor (`YouTubeConfirmationManager`):** Resposta a comentários, edição de metadados de vídeo, upload resumível de vídeo e exclusão unitária permanente.

---

## 2. Arquitetura e Arquivos do Módulo

| Arquivo | Responsabilidade |
| :--- | :--- |
| [youtube_service.py](file:///c:/xampp/htdocs/amr/src/integrations/youtube_service.py) | Serviço `YouTubeConnectionService`, máquina de estados `YouTubeConfirmationManager`, armazenamento seguro por `(account_email, channel_id)`, descoberta de canais via `channels.list(mine=True)`, checagem explícita de `UCYCmXtIR-tbWCyrwbLdczyA` e classificação granular de erros HTTP. |
| [youtube.py](file:///c:/xampp/htdocs/amr/src/tools/youtube.py) | 12 ferramentas expostas ao Gemini Live (`YOUTUBE_FUNCTION_DECLARATIONS`) e despachante `dispatch_youtube_tool`, incluindo verificação de propriedade do vídeo (`channel_mismatch` e `ambiguous_channel`). |
| [autenticar_youtube.py](file:///c:/xampp/htdocs/amr/scripts/autenticar_youtube.py) | Utilitário de linha de comando (CLI) integrado ao `run.bat` (`youtube-auth`, `youtube-status`, `youtube-channels`, `youtube-remove`). |
| [test_youtube.py](file:///c:/xampp/htdocs/amr/tests/test_youtube.py) | Suíte de testes cobrindo multi-contas/multi-canais, transição de modos sem revogação destrutiva, separação Data API vs Analytics API e máquina de estados de confirmação. |

---

## 3. Perfis de Escopo OAuth 2.0 e Requisitos por Método

O Aton suporta dois modos de autorização (`--mode readonly` e `--mode manage`):

### A. Modo Somente Leitura (`--mode readonly`)
Solicita apenas os escopos mínimos de leitura:
- `https://www.googleapis.com/auth/youtube.readonly`
- `https://www.googleapis.com/auth/yt-analytics.readonly`
- `https://www.googleapis.com/auth/userinfo.email`

### B. Modo de Gerenciamento e Publicação (`--mode manage` — padrão)
Solicita apenas os escopos necessários (sem duplicar o escopo amplo `youtube` junto com `youtube.force-ssl`):
- `https://www.googleapis.com/auth/youtube.force-ssl`
- `https://www.googleapis.com/auth/youtube.upload`
- `https://www.googleapis.com/auth/yt-analytics.readonly`
- `https://www.googleapis.com/auth/userinfo.email`

### C. Mapeamento Oficial de Escopos e Custos de Cota

| Operação / Ferramenta | Método da API | Escopos Aceitos | Custo de Cota (Padrão: 10.000/dia) |
| :--- | :--- | :--- | :--- |
| `list_youtube_channels` / `check_youtube_connection` | `channels.list` (`mine=True` / `id=...`) | `youtube.readonly` ou `youtube.force-ssl` | **1 unidade** |
| `get_youtube_channel_stats` | `channels.list` + `youtubeAnalytics.reports.query` | `youtube.readonly` + `yt-analytics.readonly` | **1 unidade** (Data API v3) |
| `list_youtube_videos` (sem `query`) | `playlistItems.list` + `videos.list` | `youtube.readonly` ou `youtube.force-ssl` | **2 unidades** |
| `list_youtube_videos` (com `query`) | `search.list` + `videos.list` | `youtube.readonly` ou `youtube.force-ssl` | **101 unidades** |
| `get_youtube_video_details` | `videos.list` | `youtube.readonly` ou `youtube.force-ssl` | **1 unidade** |
| `list_youtube_comments` | `commentThreads.list` | `youtube.readonly` (vídeos públicos) ou `youtube.force-ssl` | **1 unidade** |
| `reply_to_youtube_comment` | `comments.insert` | `youtube.force-ssl` | **50 unidades** |
| `update_youtube_video_metadata` | `videos.list` + `videos.update` | `youtube.force-ssl` | **51 unidades** |
| `upload_youtube_video` | `videos.insert` (resumable) | `youtube.upload` ou `youtube.force-ssl` | **1600 unidades** |
| `delete_youtube_video` | `videos.list` + `videos.delete` | `youtube.force-ssl` | **51 unidades** |

> [!IMPORTANT]
> **Transição Segura de Modo (`manage` $\leftrightarrow$ `readonly`):**
> O token existente em disco é preservado até que a nova autorização e a validação de escopos terminem com sucesso. No downgrade de `manage` para `readonly`, o Aton substitui o token local pelo novo token de leitura **sem acionar revogação remota automática** (pois revogar nos servidores do Google pode invalidar toda a concessão recém-emitida para o mesmo cliente/usuário). Para revogar concessões remotas no Google, use explicitamente `run.bat youtube-remove <alvo> --revoke`.

---

## 4. Como Conectar Contas e Contas de Marca (Brand Accounts)

### Passo 1: Ativar as APIs no Google Cloud Console
No mesmo projeto Google Cloud do seu arquivo `credentials.json`, certifique-se de ativar:
1. **YouTube Data API v3**
2. **YouTube Analytics API**
3. **Google+ / Google Identity UserInfo** (para confirmação de `userinfo.email`)

Além disso, na **Tela de Permissão OAuth (OAuth Consent Screen)**, adicione `cursopb@gmail.com` e `servpb@gmail.com` na lista de **Usuários de teste (Test users)** caso o aplicativo esteja em modo **"Testando" (Externo)**.

### Passo 2: Autenticar cada conta e cada Conta de Marca
A chamada `channels.list(mine=True)` retorna o canal associado à identidade selecionada na tela de consentimento do Google. Quando uma mesma conta Google administra mais de um canal (via **Conta de Marca / Brand Account**), o Google exibe um seletor de identidade no navegador:

```powershell
# 1. Autenticar a conta cursopb@gmail.com (canal principal ou 1ª Conta de Marca)
.\run.bat youtube-auth cursopb@gmail.com

# Se cursopb@gmail.com administrar outro canal (Conta de Marca), repita o comando
# e selecione a segunda identidade de canal na tela do Google:
.\run.bat youtube-auth cursopb@gmail.com

# 2. Autenticar a conta servpb@gmail.com (e repetir para cada Conta de Marca adicional)
.\run.bat youtube-auth servpb@gmail.com
```

Como o identificador do arquivo de token é derivado do par `(account_email, channel_id)`, cada canal autorizado pela mesma conta Google recebe seu próprio arquivo `tokens/youtube_acct_<sha256_64>.json`, sem sobrescrever os canais anteriores.

### Passo 3: Verificar os canais conectados e o canal `UCYCmXtIR-tbWCyrwbLdczyA`
```powershell
.\run.bat youtube-channels
# ou
.\run.bat youtube-status
```

---

## 5. Máquina de Estados de Confirmação (`YouTubeConfirmationManager`)

Todas as operações de escrita e exclusão (`reply_to_youtube_comment`, `update_youtube_video_metadata`, `upload_youtube_video`, `delete_youtube_video`) são protegidas no servidor por `YouTubeConfirmationManager`:

1. **1ª Etapa (`PENDING_SUMMARY`):** Gera o resumo claro em português e um `confirmation_token` de uso único (TTL de 5 minutos, vinculado ao `service_instance_id` do processo e ao hash SHA-256 dos parâmetros). Qualquer proposta anterior é imediatamente marcada como `SUPERSEDED`.
2. **Apresentação do Resumo (`SUMMARY_PRESENTED`):** No modo de voz, o resumo só passa para `SUMMARY_PRESENTED` quando a reprodução de áudio termina sem interrupção (`server_content.interrupted`). Se a fala for interrompida, o token entra no estado terminal `SPEECH_INTERRUPTED`.
3. **Confirmação do Usuário Fora da Banda (`USER_AFFIRMED`):** Uma resposta afirmativa real do usuário posterior ao término da leitura do resumo transiciona o token para `USER_AFFIRMED`. Um *"Não"* ou *"Cancelar"* transiciona imediatamente para `CANCELLED`.
4. **2ª Etapa (`CONSUMED`):** Verifica `service_instance_id`, validade temporal, igualdade do digest SHA-256 dos parâmetros e estado `USER_AFFIRMED`. Para `delete_youtube_video`, exige adicionalmente correspondência exata de `confirm_channel_name` e `confirm_video_title`.

---

## 6. Como Executar os Testes Automatizados

```powershell
.\.venv\Scripts\pytest.exe tests/test_youtube.py -v
```

