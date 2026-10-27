# Documentação: Fase 4 - Integração Google Workspace (Produtividade)

## 1. Visão Geral e Objetivos
A **Fase 4** integrou o **Aton** ao coração da produtividade pessoal do Google (Agenda, Gmail e Tarefas). O assistente tornou-se capaz de consultar e criar compromissos na agenda, ler e resumir mensagens recebidas no Gmail (com segurança estrita de somente leitura) e gerenciar to-dos no Google Tasks.

---

## 2. Módulos e Ferramentas Desenvolvidas

### A. Google Agenda / Google Calendar (`src/tools/google_calendar.py`)
- **Objetivo:** Consultar e agendar compromissos e reuniões por voz.
- **Recursos Principais:**
  - Autenticação OAuth2 Desktop App com renovação automática via `refresh_token`.
  - Parser inteligente de datas e horários em português (*hoje*, *amanhã*, *14h30*, *15:00*, ISO).
- **Ferramentas (*Tool Calling* para Gemini Live):**
  - `get_calendar_events(time_min, time_max, max_results)`: lista compromissos com resumo em linguagem natural.
  - `create_calendar_event(summary, start_time, end_time, description, location)`: cria novo evento na agenda.
- **Documentado em:** [docs/google_calendar.md](file:///c:/xampp/htdocs/amr/docs/google_calendar.md).

### B. Gmail Somente Leitura (`src/tools/gmail.py`)
- **Objetivo:** Verificar e ler e-mails importantes recebidos pelo usuário.
- **Segurança Estrita (Regra 6 do GEMINI.md):** Operação restrita ao escopo `gmail.readonly` para evitar qualquer risco de envio ou exclusão acidental.
- **Ferramentas (*Tool Calling* para Gemini Live):**
  - `list_unread_emails(max_results, query)`: lista remetente e assunto de e-mails não lidos ou importantes.
  - `get_email_content(email_id)`: lê o conteúdo limpo do e-mail decodificado em base64url sem tags HTML.
- **Documentado em:** [docs/gmail.md](file:///c:/xampp/htdocs/amr/docs/gmail.md).

### C. Google Tasks / Tarefas e Lembretes (`src/tools/google_tasks.py`)
- **Objetivo:** Gerenciar afazeres, pendências e listas de to-dos.
- **Recursos Principais:** Conclusão inteligente por título em linguagem natural (não exige IDs técnicos do usuário).
- **Ferramentas (*Tool Calling* para Gemini Live):**
  - `list_tasks(show_completed, max_results)`: lista tarefas ativas da lista padrão.
  - `create_task(title, notes, due_date)`: adiciona nova tarefa com vencimento.
  - `complete_task(task_id_or_title)`: conclui a tarefa pelo nome ou ID.
- **Documentado em:** [docs/google_tasks.md](file:///c:/xampp/htdocs/amr/docs/google_tasks.md).

---

## 3. Critérios de Pronto Atingidos (100% Concluído ✅)
- Perguntar *"Aton, quais são os meus compromissos de hoje?"*, *"Aton, tenho algum e-mail importante?"* ou *"Aton, marque a tarefa de compras como feita"* e o assistente responder com fluidez e precisão por voz.
