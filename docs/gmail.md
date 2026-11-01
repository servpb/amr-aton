# Documentação: Módulo de Conexão Multi-Contas com Gmail (OAuth 2.0 Desktop & API Oficial)

## 1. Visão Geral
O módulo de conexão com **Gmail** capacita o assistente **Aton** a autenticar-se com segurança via navegador (fluxo **OAuth 2.0 para Aplicativo Desktop**), gerenciar **múltiplas contas do Gmail simultaneamente** (ou uma única conta) e consultar e-mails em Português do Brasil.

A arquitetura é dividida em dois componentes desacoplados:
- **Serviço Centralizado (`src/integrations/gmail_service.py`):** Implementa `GmailConnectionService` e `get_gmail_service()`, responsável por:
  - Validação estrutural de `credentials.json` (garantindo tipo `installed` / Desktop);
  - Armazenamento multi-contas livre de colisões usando hash SHA-256 completo de 64 caracteres (`tokens/gmail_acct_<sha256_64>.json`) e índice seguro (`tokens/accounts_index.json`), sem usar o endereço de e-mail diretamente como nome de arquivo;
  - Migração atômica e sem perda de um `token.json` legado (confirmando o e-mail real via `users/me/profile` antes de mover e preservando o `token.json` intacto em caso de falha de rede);
  - Verificação da conta autorizada no navegador antes de salvar (`expected_email`), cancelando sem sobrescrever nada caso o usuário selecione outra conta por engano;
  - Renovação silenciosa de tokens expirados antes de reportar erro e invalidação imediata de tokens revogados (`invalid_grant` / HTTP `401`);
  - Remoção de conta local ou com revogação remota nos servidores do Google (`remove_account`);
  - Diagnóstico granular de erros HTTP `403` (`accessNotConfigured` vs. `insufficientPermissions` vs. `quota_exceeded`).
- **Ferramentas do Assistente (`src/tools/gmail.py`):** Expõe 5 ferramentas para o Gemini Live, Resumo Executivo Matinal (`src/core/memory.py`) e Mobile Gateway:
  1. `list_unread_emails(max_results=5, query="is:unread label:INBOX", account=None)`
  2. `get_email_content(email_id, account=None)`
  3. `authenticate_gmail(expected_email=None)`
  4. `check_gmail_connection(account=None)`
  5. `remove_gmail_account(account, revoke_remote=False)`

---

## 2. Permissões (Escopos) e Política de Expiração em Modo "Testando" (7 Dias)

### Escopo Solicitado Atual (Somente Leitura)
- `https://www.googleapis.com/auth/gmail.readonly`

### Aviso Importante: Expiração de 7 Dias em Modo "Testando" (Google Cloud)
De acordo com a [Política Oficial do Google OAuth 2.0](https://developers.google.com/identity/protocols/oauth2/#expiration):
- Enquanto o status de publicação do aplicativo no Google Cloud Console (**Google Auth Platform > Público-alvo**) estiver como **"Testando" (Testing)** com tipo de usuário **Externo**, cada conta conectada precisa estar listada em **Usuários de teste**;
- Além disso, para aplicativos externos em modo **Testando** que solicitam escopos restritos do Gmail (`gmail.readonly`), **os tokens de atualização (`refresh_token`) emitidos pelo Google expiram após 7 dias**, exigindo uma nova autorização semanal no navegador (`run.bat gmail-auth <email>`) enquanto o aplicativo permanecer nesse modo.

---

## 3. Comportamento Multi-Contas e Garantias de Segurança

1. **Identificador de Arquivo Seguro e Sem Colisão:**
   - Os arquivos de token nunca usam o endereço de e-mail diretamente no nome do arquivo.
   - Cada conta confirmada pela API (`users/me/profile`) recebe um identificador baseado no hash SHA-256 completo (64 caracteres hexadecimais) do e-mail normalizado (`tokens/gmail_acct_<sha256>.json`). Caso exista qualquer conflito no índice ou no metadado `account_email` em disco, o serviço acrescenta sufixo incremental (`_1`, `_2`) sem jamais sobrescrever outra conta.
2. **Migração Atômica do `token.json` Legado:**
   - Se existir um `token.json` legado na raiz do projeto, o serviço: (1) carrega e valida estrutura e escopos, (2) renova silenciosamente se necessário, (3) consulta `users/me/profile` para confirmar o endereço de e-mail real daquele token (sem presumir endereço fixo), (4) grava `tokens/gmail_acct_<sha256>.json` e `tokens/accounts_index.json` de forma atômica (`.tmp` + `os.replace`) e (5) somente após confirmar ambos em disco remove o `token.json` antigo. Em caso de falha de rede ou API, o `token.json` legado é preservado intacto.
3. **Verificação da Conta Autorizada Antes de Salvar (`expected_email`):**
   - Ao executar `run.bat gmail-auth cursopb@gmail.com` (ou informar `expected_email`), o Aton envia `login_hint` ao Google e, após o consentimento no navegador, verifica o e-mail retornado por `users/me/profile` em memória **antes** de gravar em disco. Se você tiver clicado em outra conta por engano, o Aton alerta a divergência (`account_mismatch`) e cancela sem salvar nem sobrescrever nada.
4. **Consulta Unificada vs. Por Conta e Limite `max_results`:**
   - Em `list_unread_emails`, se `account` for informado (ex.: `"cursopb@gmail.com"` ou `"cursopb"`), apenas aquela caixa é consultada.
   - Se `account` for omitido e houver múltiplas contas conectadas, todas as contas ativas são consultadas com **isolamento de falhas** (se uma conta estiver expirada/revogada, as mensagens das demais contas são preservadas e um aviso indica qual conta precisa de reconexão).
   - Cada mensagem inclui o campo `"account"` identificando sua caixa de origem, e o parâmetro `max_results` (padrão `5`) representa o **limite total combinado** das mensagens mais recentes ordenadas por data (`internalDate`).
5. **Busca de Mensagem por ID (`get_email_content`) e Detecção de Ambiguidade:**
   - Como IDs de mensagem do Gmail só têm garantia de unicidade dentro de uma mesma caixa postal, se `account` não for informado em `get_email_content(email_id)`, o Aton procura nas contas conectadas: se encontrar em apenas uma caixa, retorna o conteúdo com `"account"`; se encontrar o mesmo ID em mais de uma caixa, retorna `"status": "ambiguous_account"` listando as contas correspondentes para que o usuário especifique qual deseja ler.
6. **Remoção Local vs. Revogação Remota no Google (`gmail-remove`):**
   - O comando `run.bat gmail-remove <email>` apaga o arquivo de token local e remove a conta do Aton, mas **não revoga** a autorização nos servidores da Conta Google.
   - Para também revogar o token remotamente nos servidores do Google (`https://oauth2.googleapis.com/revoke`), adicione a flag `--revoke`: `run.bat gmail-remove <email> --revoke`.

---

## 4. Comandos de Gerenciamento de Contas (CLI)

### A. Verificar Status de Todas as Contas Conectadas (Modo Passivo)
```cmd
run.bat gmail-status
```
*(Ou verificar uma conta específica: `run.bat gmail-status cursopb@gmail.com`)*

### B. Conectar ou Reconectar Cada uma das Suas Contas no Navegador
Cadastrar o e-mail como usuário de teste no Google Cloud apenas autoriza o login; para conectar efetivamente cada caixa ao Aton, execute um comando por vez e conclua o consentimento no navegador:
```cmd
run.bat gmail-auth servpb@gmail.com
run.bat gmail-auth cursopb@gmail.com
run.bat gmail-auth contato.hostpb@gmail.com
run.bat gmail-auth contato.cpbm@gmail.com
run.bat gmail-auth devsebastiao.alves@gmail.com
run.bat gmail-auth luciana1social@gmail.com
```

### C. Desconectar / Remover uma Conta do Aton
- **Apenas desconectar localmente do Aton:**
  ```cmd
  run.bat gmail-remove cursopb@gmail.com
  ```
- **Desconectar localmente e também revogar a autorização no Google:**
  ```cmd
  run.bat gmail-remove cursopb@gmail.com --revoke
  ```

### D. Rodar a Suíte de Testes Automatizados
```cmd
.\.venv\Scripts\pytest.exe tests/test_gmail.py -v
```
