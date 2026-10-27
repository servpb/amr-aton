# Documentação: Google Calendar & Integração Google Workspace

## 1. Visão Geral
O módulo **Google Calendar** (`src/tools/google_calendar.py`) integra o assistente **Aton** à agenda e produtividade do Google (Fase 4 do Roadmap).

Ele permite que o usuário consulte seus próximos compromissos e agende novos eventos diretamente por voz durante a conversa em tempo real com o Aton ou através do painel móvel/carro.

---

## 2. Como Funciona a Arquitetura

1. **Autenticação Segura via OAuth 2.0 (Desktop App):**
   - Utiliza as credenciais do Google Cloud Console (`credentials.json`) para fluxo OAuth2 local de aplicativo Desktop.
   - O token de acesso gerado é salvo localmente em `token.json` (ignorado pelo Git).
   - O Aton renova o token automaticamente em segundo plano via `refresh_token` sem interromper a fala ou pedir novas autenticações constantes.
2. **Chamadas Diretas e Eficientes à Google Calendar API v3:**
   - Comunicação via HTTPS com autenticação `Bearer <token>` nos endpoints oficiais do Google Calendar (`https://www.googleapis.com/calendar/v3/calendars/primary/events`).
   - Não requer bibliotecas pesadas de terceiros; utiliza a biblioteca oficial `google-auth` já integrada ao ecossistema Google.
3. **Parser Inteligente de Datas e Horários Naturais em Português:**
   - Suporta comandos falados naturais como:
     - *"Aton, quais são meus compromissos de hoje?"*
     - *"Aton, o que tenho agendado para amanhã?"*
     - *"Aton, agende reunião com a diretoria amanhã às 15:00"*
     - *"Aton, marque consulta médica hoje às 16h"*
   - Interpreta automaticamente formatos ISO, referências relativas (*hoje*, *amanhã*) e horários (*14h30*, *15:00*).

---

## 3. Ferramentas Disponíveis (*Tool Calling* para Gemini Live)

### A. `get_calendar_events`
- **Descrição:** Consulta compromissos e reuniões agendadas na agenda do Google.
- **Parâmetros:**
  - `time_min` *(string, opcional)*: Início do filtro (ex: `'hoje'`, `'amanhã'` ou `'2026-10-28T08:00:00'`). Padrão: momento atual.
  - `time_max` *(string, opcional)*: Fim do filtro (ex: `'hoje às 23:59'`). Padrão: 24 horas à frente de `time_min`.
  - `max_results` *(integer, opcional)*: Limite de eventos a retornar (padrão: 10).
  - `calendar_id` *(string, opcional)*: ID da agenda (padrão: `'primary'`).
- **Exemplo de Retorno:**
```json
{
  "status": "success",
  "message": "Você tem 2 compromissos na agenda: Reunião de Planejamento em 28/10 às 14:00; Consulta Médica em 28/10 às 16:30.",
  "count": 2,
  "events": [
    {
      "id": "evt_123",
      "summary": "Reunião de Planejamento",
      "start": "2026-10-28T14:00:00-03:00",
      "display_time": "28/10 às 14:00",
      "location": "Google Meet"
    }
  ]
}
```

### B. `create_calendar_event`
- **Descrição:** Cria um novo evento na agenda do Google.
- **Parâmetros:**
  - `summary` *(string, obrigatório)*: Título do compromisso (ex: `'Dentista'`, `'Almoço com Cliente'`).
  - `start_time` *(string, obrigatório)*: Data e horário de início (ex: `'amanhã às 10h'`, `'hoje às 15:30'`).
  - `end_time` *(string, opcional)*: Horário de término (se omitido, define 1 hora de duração).
  - `description` *(string, opcional)*: Detalhes, pauta ou anotações do evento.
  - `location` *(string, opcional)*: Local ou link da reunião.
  - `calendar_id` *(string, opcional)*: ID da agenda (padrão: `'primary'`).
- **Exemplo de Retorno:**
```json
{
  "status": "success",
  "message": "Compromisso 'Dentista' agendado com sucesso para 28/10 às 15:00, senhor.",
  "event_id": "new_evt_789",
  "html_link": "https://www.google.com/calendar/event?eid=new_evt_789"
}
```

---

## 4. Passo a Passo para Ativação da Google Calendar API (Custo Zero)

Para conectar sua conta Google real ao Aton sem custos:

1. Acesse o [Google Cloud Console](https://console.cloud.google.com/).
2. Crie ou selecione um projeto (ex: *Aton Assistant*).
3. No menu lateral, acesse **APIs e Serviços** > **Biblioteca**.
4. Pesquise por **Google Calendar API** e clique em **Ativar**.
5. Em **APIs e Serviços** > **Credenciais**:
   - Clique em **Criar Credenciais** > **ID do cliente OAuth**.
   - Tipo de aplicativo: selecione **Aplicativo para Computador (Desktop App)**.
   - Nome: *Aton Desktop*.
   - Clique em **Criar** e depois faça o download do arquivo JSON.
6. Renomeie o arquivo baixado para `credentials.json` e coloque-o na raiz do projeto `c:\xampp\htdocs\amr\credentials.json`.
7. Na primeira execução com autenticação, um link no navegador solicitará sua autorização uma única vez, gerando o arquivo `token.json` local.

> [!NOTE]
> Enquanto `credentials.json` ou `token.json` não forem adicionados, o Aton continuará respondendo normalmente por voz avisando com clareza que a agenda aguarda configuração, sem gerar erros ou travar as outras 17 ferramentas do assistente.

---

## 5. Como Testar Automatizadamente

Execute os testes unitários do módulo de agenda:
```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_google_calendar.py -v
```

Casos cobertos:
- Verificação de retorno amigável quando não autenticado.
- Parsing e interpretação de datas relativas (*hoje às 15:00*, *amanhã às 10h*, ISO).
- Consulta e listagem de eventos com resposta falada sintetizada.
- Criação e agendamento de compromissos com horário de término padrão de 1 hora.
- Despacho unificado em `dispatch_tool` e presença nas ferramentas ativas (`ALL_ATON_TOOLS`).
