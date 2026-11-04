# Documentação: Integração Google Agenda 100% por Voz (Google Calendar API v3)

## 1. Visão Geral
O módulo **Google Agenda** ([`src/tools/google_calendar.py`](file:///c:/xampp/htdocs/amr/src/tools/google_calendar.py) e [`src/integrations/calendar_service.py`](file:///c:/xampp/htdocs/amr/src/integrations/calendar_service.py)) transforma comandos em linguagem natural falada em ações precisas no Google Calendar do usuário, projetado especificamente para operação **100% por voz** no assistente **Aton**.

---

## 2. Passo a Passo Completo de Configuração e Autenticação (Do Zero à Conexão Ativa)

Abaixo estão documentados todos os passos reais executados para configurar, autorizar e ativar o **Google Agenda** no **Aton**:

### Passo 1: Preparar as Credenciais OAuth 2.0 (`credentials.json`)
1. No [Google Cloud Console](https://console.cloud.google.com/), selecione o projeto **`aton`**.
2. Em **APIs e Serviços > Credenciais**, utilize (ou crie) um **ID do cliente OAuth 2.0** do tipo **Aplicativo para Computador (Desktop App)**.
3. Baixe o arquivo JSON de credenciais e salve na raiz do projeto como:
   `c:\xampp\htdocs\amr\credentials.json`
4. Na **Tela de permissão OAuth (OAuth consent screen)**, certifique-se de que o seu e-mail (ex.: `servpb@gmail.com`) consta na lista de **Usuários de teste (Test users)** caso o aplicativo esteja em modo *Testing*.

### Passo 2: Ativar a Google Calendar API no Google Cloud Console
> **Importante:** Mesmo com o `credentials.json` configurado para Gmail ou YouTube, a API específica do Google Calendar precisa estar ativada no mesmo projeto do Google Cloud.

1. Acesse diretamente a biblioteca da API do Google Calendar logado com a conta do projeto:
   - https://console.cloud.google.com/apis/library/calendar-json.googleapis.com
2. Confirme no topo da página se o projeto **`aton`** está selecionado.
3. Clique no botão azul **`Ativar`** (*Enable*).
4. Verifique se o status mudou para **Ativado** (`calendar-json.googleapis.com`).

### Passo 3: Executar a Autenticação OAuth 2.0 pelo Terminal (`calendar-auth`)
1. No terminal (PowerShell ou CMD), dentro da pasta `c:\xampp\htdocs\amr`, execute:
   ```powershell
   .\run.bat calendar-auth
   ```
   *(Opcionalmente passando o e-mail específico: `.\run.bat calendar-auth servpb@gmail.com`)*
2. O navegador abrirá automaticamente na tela de login do Google.

### Passo 4: Autorizar o Aplicativo Não Verificado no Navegador
Como o aplicativo **Aton** é de uso pessoal no seu próprio projeto do Google Cloud e não foi submetido à loja pública do Google, o navegador exibirá um aviso padrão de segurança. Siga exatamente esta sequência:

1. **Escolha a sua conta Google** (ex.: `servpb@gmail.com`).
2. Na tela **"O Google não verificou este app"**:
   - Clique no link **`Avançado`** (no canto inferior esquerdo, ao lado do botão azul *"Voltar à segurança"*).
   - Clique no link que aparece logo abaixo: **`Acessar Aton (não seguro)`**.
3. Na tela **"O app Aton quer acessar sua Conta do Google"**:
   - Clique no botão **`Continuar`** (no canto inferior direito).
   - Caso apareça a caixa de seleção de escopos do Google Agenda (*"Ver, editar, compartilhar e excluir permanentemente todas as agendas..."*), marque a caixa (ou **Selecionar tudo**) e clique em **`Continuar`**.
4. O navegador exibirá a confirmação final:
   ```text
   The authentication flow has completed. You may close this window.
   ```

### Passo 5: Salvamento Automático e Protegido dos Tokens
Assim que o navegador conclui o fluxo OAuth:
- O serviço [`CalendarConnectionService`](file:///c:/xampp/htdocs/amr/src/integrations/calendar_service.py) grava o token **imediatamente** com escrita atômica e permissões restritas ao proprietário (`chmod 600` / `S_IRUSR | S_IWUSR`), mesmo que a propagação da API no Google Cloud ainda esteja em andamento:
  - **Token multi-conta por hash SHA-256:** `tokens/calendar_acct_<sha256_64>.json`
  - **Índice de contas e fuso horário:** `tokens/calendar_accounts_index.json`
  - **Token de compatibilidade legada:** `token.json`
  - **Keyring do sistema (opcional):** armazenado no cofre de credenciais do Windows quando disponível.
- Todos esses arquivos estão protegidos no [`.gitignore`](file:///c:/xampp/htdocs/amr/.gitignore) para jamais serem enviados ao GitHub.

### Passo 6: Verificar o Status da Conexão (`calendar-status`)
Para confirmar no terminal que o token está válido e a **Google Calendar API** já responde ao vivo:
```powershell
.\run.bat calendar-status
```
**Saída esperada de sucesso:**
```text
=== Status do Google Agenda (Aton) ===
Conta padrão configurada: servpb@gmail.com
Contas registradas (1):
  - servpb@gmail.com (fuso: America/Fortaleza, arquivo: calendar_acct_539e5e771105cdcccf103a1e8e449cf063bf4bb200a8b9823d24c0b8ea75e4a8.json)
Resultado da verificação: A conexão com o Google Agenda está ativa para a conta servpb@gmail.com.
```

---

## 3. Variáveis de Ambiente (`.env`)

As variáveis abaixo no arquivo `.env` (documentadas no [`.env.example`](file:///c:/xampp/htdocs/amr/.env.example)) controlam o comportamento do módulo:

```env
# Caminho das credenciais OAuth 2.0 Desktop baixadas do Google Cloud Console
GOOGLE_CALENDAR_CREDENTIALS_PATH=credentials.json

# Caminho do token legado de compatibilidade
GOOGLE_CALENDAR_TOKEN_PATH=token.json

# Diretório protegido onde ficam os tokens multi-conta e o índice
GOOGLE_CALENDAR_TOKENS_DIR=tokens

# Conta padrão opcional quando houver mais de uma conta autenticada
GOOGLE_CALENDAR_DEFAULT_ACCOUNT=

# ID da agenda padrão ('primary' representa a agenda principal da conta)
GOOGLE_CALENDAR_ID=primary

# Fuso horário padrão do usuário
GOOGLE_CALENDAR_TIMEZONE=America/Fortaleza
```

---

## 4. Pilares de Arquitetura e Segurança (Ajustes 1 a 10)

1. **Injeção Dinâmica de Contexto Temporal (`America/Fortaleza`):**
   - A cada sessão de voz, [`get_dynamic_system_instruction()`](file:///c:/xampp/htdocs/amr/src/core/prompts.py) injeta a data e hora exatas, o dia da semana calculado em código (`get_weekday_pt`) e a tabela de referência dos **próximos 7 dias** (`build_next_7_days_table`).
   - Se a conversa atravessar a meia-noite ou durar muito, o modelo aciona `get_current_time` para atualizar o contexto sem nunca calcular dias da semana de cabeça.
2. **Detecção Automática de Conflitos e Sugestão em Horário Comercial:**
   - Embutida diretamente em `create_event` e `edit_event` (não é necessário chamar `list_events` antes apenas para verificar conflito).
   - Ignora automaticamente eventos marcados como **"livre"** (`transparency == "transparent"`), eventos cancelados e convites **recusados** pelo usuário (`responseStatus == "declined"`).
   - Trata corretamente eventos de dia inteiro e eventos que cruzam a meia-noite, sugerindo até **3 horários livres dentro do horário comercial (08h às 18h)**.
3. **Portão de Confirmação com TTL, Uso Único e Vínculo de Sessão (`CalendarConfirmationManager`):**
   - Ações destrutivas ou de alto impacto (`delete_event`, `delete_calendar`, edição/exclusão de eventos recorrentes ou alteração de eventos com convidados) geram uma proposta pendente (`proposal_id`) com **validade de 60 segundos**, **consumo único** (bloqueio de replay) e **vínculo à sessão de voz ativa** (`session_id`).
   - A execução física só ocorre quando `confirm_action(proposal_id, confirmed_name?)` é chamada após o usuário confirmar verbalmente.
4. **Proteção Estrita da Agenda Principal (`primary`):**
   - `delete_calendar` bloqueia de forma absoluta qualquer tentativa de exclusão da agenda principal (`primary` ou e-mail da conta).
   - Apenas agendas secundárias podem ser excluídas, exigindo que o usuário fale o nome da agenda (validado com normalização tolerante a acentos, caixa e pontuação via `normalize_spoken_name`).
5. **Defesa contra Injeção de Prompt em Convites Externos:**
   - Campos vindos de eventos (`summary`, `description`, `location`) são truncados e delimitados como `[DADO_EVENTO_NAO_CONFIAVEL: ...]` com `untrusted_data=True`.
   - Padrões imperativos suspeitos (*"ignore suas regras"*, *"apague tudo"*) ativam `suspicious_content_detected=True` e um aviso falado de uma frase, mantendo ações destrutivas isoladas atrás de `confirm_action`.
6. **Divisão Explícita de Série Recorrente ("Esta e as Seguintes" / `following`):**
   - Como a API do Google Calendar não possui escopo nativo para *"esta e as seguintes"* em chamada única, o módulo implementa a divisão em duas etapas explícitas:
     1. Atualiza a série mestre original adicionando `UNTIL=<inicio_da_instancia_utc - 1s>` na regra `RRULE`.
     2. Cria uma nova série recorrente a partir do novo horário com os dados atualizados.
7. **Busca Prévia de Contatos (Sugestão sem Envio Automático):**
   - Quando o usuário menciona um convidado apenas pelo nome (ex.: *"reunião com a Carla"*), `lookup_contact_by_name` pesquisa na base local (`amr_memory.db` / `clientes` e `memories`) e em participantes de eventos recentes, **apenas sugerindo** o e-mail encontrado e exigindo confirmação (`attendees_confirmed=True`) antes de disparar convites.
8. **Separação Estrita entre Voz e Fluxo OAuth:**
   - O fluxo OAuth interativo de navegador fica restrito ao CLI (`run.bat calendar-auth`), nunca exposto como ferramenta do modelo.

---

## 5. Ferramentas Disponíveis (11 Ferramentas de Voz + 2 Aliases Legados)

### Eventos
- `list_events(calendar_id="primary", time_min?, time_max?, query?, max_results=20, page_offset=0, account?)`: Lista compromissos lendo no máximo **3 eventos por vez** na resposta falada e informando quantos restam.
- `create_event(title, start, end?, calendar_id="primary", description?, location?, attendees?, reminders=10, recurrence?, add_meet_link=False, all_day=False, force_conflict=False, attendees_confirmed=False, account?)`: Cria evento aplicando padrões de voz (1h de duração, lembrete de 10 min, dia inteiro quando sem hora) e checando conflitos automaticamente.
- `edit_event(event_id, calendar_id="primary", title?, start?, end?, description?, location?, attendees?, reminders?, recurrence?, recurrence_scope?, force_conflict=False, account?)`: Edita ou move evento, exigindo `recurrence_scope` (`"this"`, `"following"`, `"all"`) para recorrentes.
- `delete_event(event_id, calendar_id="primary", recurrence_scope?, account?)`: Cria proposta pendente de exclusão de evento (60s TTL).

### Agendas
- `list_calendars(account?)`: Lista a agenda principal e agendas secundárias.
- `create_calendar(name, description?, timezone_name="America/Fortaleza", account?)`: Cria uma nova agenda secundária.
- `edit_calendar(calendar_id, name?, description?, timezone_name?, account?)`: Renomeia ou atualiza agenda.
- `delete_calendar(calendar_id, account?)`: Bloqueia `primary` e cria proposta pendente exigindo o nome falado da agenda secundária.

### Apoio e Segurança
- `get_current_time(timezone_name="America/Fortaleza")`: Retorna data/hora atual, dia da semana calculado em código e tabela dos próximos 7 dias.
- `confirm_action(proposal_id, confirmed_name?)`: Valida e consome uma proposta pendente única dentro da janela de 60 segundos.
- `check_calendar_connection(account?)`: Verifica passivamente o estado da conexão OAuth 2.0.

*(Aliases legados `get_calendar_events` e `create_calendar_event` permanecem disponíveis para compatibilidade com o Briefing Matinal).*

---

## 6. Comandos CLI e Exemplos de Teste por Voz

### Comandos no Terminal
```powershell
# Autenticar conta no navegador (OAuth 2.0 Desktop)
.\run.bat calendar-auth
.\run.bat calendar-auth servpb@gmail.com

# Verificar status das contas conectadas
.\run.bat calendar-status

# Remover token de uma conta (opcionalmente revogando no Google)
.\run.bat calendar-remove servpb@gmail.com --revoke

# Executar os 17 testes automatizados do módulo
.\.venv\Scripts\python.exe -m pytest tests/test_google_calendar.py -v
```

### Exemplos de Comandos por Voz com o Aton (`.\run.bat`)
- **Status e Hora:** *"Aton, verifique a conexão com o Google Agenda."* / *"Aton, que horas são?"*
- **Consulta:** *"Aton, o que eu tenho na agenda hoje?"* / *"Aton, quais são os meus compromissos desta semana?"*
- **Criação Rápida:** *"Aton, marque dentista amanhã às duas da tarde."*
- **Evento de Dia Inteiro:** *"Aton, crie um evento de dia inteiro na sexta-feira chamado Fechamento Mensal."*
- **Edição / Mudança de Horário:** *"Aton, mude o dentista de amanhã para as quatro da tarde."*
- **Exclusão com Confirmação:** *"Aton, apague o compromisso de dentista de amanhã."* -> *"Sim, pode apagar."*
- **Agendas Secundárias:** *"Aton, crie uma agenda chamada Projetos Especiais."* / *"Aton, liste as minhas agendas."*
