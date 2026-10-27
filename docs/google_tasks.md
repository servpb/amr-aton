# Documentação: Integração Google Tasks (Tarefas e Lembretes)

## 1. Visão Geral
O módulo **Google Tasks** (`src/tools/google_tasks.py`) conclui a **Fase 4 (Google Workspace)** do roadmap do **Aton**, adicionando gerenciamento inteligente de tarefas, listas de afazeres (*to-dos*) e lembretes por comando de voz natural.

Com este módulo, o usuário pode consultar suas pendências, criar novas tarefas com data de vencimento e marcar afazeres como concluídos sem tocar no teclado ou na tela.

---

## 2. Como Funciona a Arquitetura

1. **Autenticação Segura via OAuth 2.0:**
   - Compartilha o mesmo fluxo OAuth2 unificado do Google Workspace (`credentials.json` e `token.json`).
   - Escopo oficial: `https://www.googleapis.com/auth/tasks`.
2. **Integração com a Google Tasks REST API v1:**
   - Lista tarefas ativas na lista padrão (`@default`) ou listas específicas do usuário.
   - Adiciona tarefas com título, anotações e datas de vencimento convertidas para RFC 3339.
3. **Conclusão Inteligente por Nome/Título em Linguagem Natural:**
   - O usuário não precisa saber IDs alfanuméricos longos. Quando disser:
     *"Aton, marque a tarefa 'comprar pão de queijo' como concluída"*
     o sistema pesquisa as tarefas pendentes, localiza o item mais relevante e dispara a atualização para `status: "completed"`.
4. **Resumo Falado Sintetizado:**
   - O Aton verbaliza com precisão:
     *"Você tem 2 tarefas pendentes: primeiro 'Comprar café', depois 'Enviar relatório semanal'."*

---

## 3. Ferramentas Disponíveis (*Tool Calling* para Gemini Live)

### A. `list_tasks`
- **Descrição:** Lista as pendências e afazeres da lista do Google Tarefas.
- **Parâmetros:**
  - `show_completed` *(boolean, opcional)*: Inclui tarefas já concluídas se `true` (padrão: `false`).
  - `task_list_id` *(string, opcional)*: ID da lista (padrão: `'@default'`).
  - `max_results` *(integer, opcional)*: Máximo de tarefas a retornar (padrão: 10).
- **Exemplo de Retorno:**
```json
{
  "status": "success",
  "message": "Você tem 2 tarefas pendentes: 'Comprar café'; 'Enviar relatório'.",
  "count": 2,
  "tasks": [
    {
      "id": "tsk_01",
      "title": "Comprar café",
      "status": "needsAction",
      "notes": ""
    }
  ]
}
```

### B. `create_task`
- **Descrição:** Adiciona uma nova tarefa ou lembrete.
- **Parâmetros:**
  - `title` *(string, obrigatório)*: Título da tarefa (ex: `'Revisar proposta comercial'`, `'Comprar frutas'`).
  - `notes` *(string, opcional)*: Detalhes ou notas extras.
  - `due_date` *(string, opcional)*: Data de vencimento (ex: `'hoje'`, `'amanhã'`, `'2026-10-30'`).
  - `task_list_id` *(string, opcional)*: ID da lista (padrão: `'@default'`).
- **Exemplo de Retorno:**
```json
{
  "status": "success",
  "message": "Tarefa 'Revisar proposta comercial' adicionada com sucesso à sua lista, senhor.",
  "task_id": "new_tsk_99",
  "title": "Revisar proposta comercial"
}
```

### C. `complete_task`
- **Descrição:** Marca uma tarefa existente como feita, buscando pelo título ou pelo ID.
- **Parâmetros:**
  - `task_id_or_title` *(string, obrigatório)*: Nome ou ID da tarefa (ex: `'revisar proposta'`).
  - `task_list_id` *(string, opcional)*: ID da lista (padrão: `'@default'`).
- **Exemplo de Retorno:**
```json
{
  "status": "success",
  "message": "Tarefa 'Revisar proposta comercial' marcada como concluída com sucesso, senhor.",
  "task_id": "new_tsk_99",
  "title": "Revisar proposta comercial"
}
```

---

## 4. Passo a Passo para Ativação da Google Tasks API (Custo Zero)

1. Acesse o [Google Cloud Console](https://console.cloud.google.com/).
2. No seu projeto do Aton, acesse **APIs e Serviços** > **Biblioteca**.
3. Pesquise por **Google Tasks API** e clique em **Ativar**.
4. Em **Tela de consentimento OAuth** > **Escopos**, adicione o escopo `.../auth/tasks`.
5. O Aton utilizará o mesmo arquivo `credentials.json` já configurado na raiz do projeto.

---

## 5. Como Testar Automatizadamente

Execute a suíte de testes do Google Tasks:
```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_google_tasks.py -v
```

Casos cobertos:
- Verificação de retorno amigável quando não autenticado.
- Listagem de tarefas vazias e preenchidas, filtrando tarefas já concluídas.
- Criação de tarefas com ou sem data de vencimento.
- Conclusão direta por ID e conclusão inteligente por correspondência de título falado.
- Despacho unificado em `dispatch_tool` e contagem de ferramentas ativas (`ALL_ATON_TOOLS`).
