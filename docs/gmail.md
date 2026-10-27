# Documentação: Integração Gmail (Somente Leitura)

## 1. Visão Geral
O módulo **Gmail** (`src/tools/gmail.py`) capacita o assistente **Aton** a verificar, listar e ler e-mails importantes recebidos pelo usuário diretamente por voz (Fase 4 do Roadmap).

Em estrita conformidade com a política de segurança do projeto (Regra 6 do `GEMINI.md`), a integração opera exclusivamente no modo **Somente Leitura (`gmail.readonly`)**, garantindo que o assistente possa informar sobre mensagens recebidas sem qualquer risco de envio acidental, exclusão ou alteração de e-mails.

---

## 2. Como Funciona a Arquitetura

1. **Autenticação Segura via OAuth 2.0:**
   - Compartilha o mesmo fluxo e arquivo `credentials.json` e `token.json` do Google Workspace.
   - Escopo seguro restrito: `https://www.googleapis.com/auth/gmail.readonly`.
2. **Processamento e Decodificação de Mensagens:**
   - Realiza consultas na Gmail REST API v1 (`https://gmail.googleapis.com/gmail/v1/users/me/messages`).
   - Decodifica automaticamente o conteúdo em formato *base64url*.
   - Limpa tags HTML, scripts e espaços excessivos, extraindo apenas o texto puro da mensagem.
3. **Resumo Falado Inteligente em Português:**
   - Ao listar e-mails, o Aton sintetiza uma resposta fluida:
     *"Você tem 2 novos e-mails não lidos: primeiro de Diretoria sobre 'Reunião Geral', depois de Financeiro sobre 'Fatura do Mês'."*
   - Ao ler o conteúdo de um e-mail específico, resume a mensagem limitando o áudio para evitar respostas excessivamente longas.

---

## 3. Ferramentas Disponíveis (*Tool Calling* para Gemini Live)

### A. `list_unread_emails`
- **Descrição:** Lista e resume os e-mails mais recentes e não lidos da caixa de entrada.
- **Parâmetros:**
  - `max_results` *(integer, opcional)*: Quantidade máxima de e-mails a retornar (padrão: 5).
  - `query` *(string, opcional)*: Filtro de busca do Gmail (padrão: `'is:unread label:INBOX'`). Permite comandos como `'from:chefe'` ou `'is:important'`.
- **Exemplo de Retorno:**
```json
{
  "status": "success",
  "message": "Você tem 1 novo e-mail de Ana Gerente com o assunto 'Aprovação do Projeto'.",
  "count": 1,
  "emails": [
    {
      "id": "18c123456789abcd",
      "from": "Ana Gerente",
      "full_from": "Ana Gerente <ana@empresa.com>",
      "subject": "Aprovação do Projeto",
      "date": "Wed, 28 Oct 2026 14:00:00 -0300",
      "snippet": "Prezado senhor, o projeto Aton foi aprovado com louvor..."
    }
  ]
}
```

### B. `get_email_content`
- **Descrição:** Obtém o texto completo e resumo de um e-mail específico pelo seu ID retornado por `list_unread_emails`.
- **Parâmetros:**
  - `email_id` *(string, obrigatório)*: Identificador único da mensagem no Gmail.
- **Exemplo de Retorno:**
```json
{
  "status": "success",
  "message": "E-mail de Ana Gerente sobre 'Aprovação do Projeto': Prezado senhor, o projeto Aton foi aprovado com louvor pela equipe...",
  "email_id": "18c123456789abcd",
  "from": "Ana Gerente",
  "subject": "Aprovação do Projeto",
  "body": "Prezado senhor, o projeto Aton foi aprovado com louvor pela equipe."
}
```

---

## 4. Passo a Passo para Ativação da Gmail API (Custo Zero)

Para habilitar a leitura de e-mails na mesma credencial do Google Workspace:

1. Acesse o [Google Cloud Console](https://console.cloud.google.com/).
2. No seu projeto do Aton, acesse **APIs e Serviços** > **Biblioteca**.
3. Pesquise por **Gmail API** e clique em **Ativar**.
4. Em **Tela de consentimento OAuth** > **Escopos**, adicione o escopo `.../auth/gmail.readonly`.
5. Pronto! O Aton utilizará o mesmo arquivo `credentials.json` para autorizar a agenda e os e-mails com uma única confirmação do usuário.

---

## 5. Como Testar Automatizadamente

Execute a suíte de testes do Gmail:
```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_gmail.py -v
```

Casos cobertos:
- Decodificação de dados base64url e limpeza de HTML.
- Comportamento de aviso amigável quando não autenticado.
- Caixa de entrada vazia (*"não tem nenhum novo e-mail não lido"*).
- Listagem e resumo de mensagens com remetente simplificado e assunto.
- Leitura do corpo da mensagem e formatação da fala.
- Despacho unificado em `dispatch_tool` e presença nas ferramentas ativas (`ALL_ATON_TOOLS`).
