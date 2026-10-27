# Guia Prático de Configuração do Supabase para o Aton

Este guia passo a passo foi preparado para você (criador) conectar o **Aton** ao seu banco de dados em nuvem no **Supabase (PostgreSQL + pgvector)**, transformando o assistente em seu Segundo Cérebro permanente com custo zero.

---

## 1. Criando seu Projeto Gratuito no Supabase

1. Acesse [supabase.com](https://supabase.com) e faça login (pode usar sua conta do GitHub).
2. Clique em **"New project"** (Novo Projeto).
3. Preencha as informações:
   - **Name:** `aton-second-brain` (ou o nome que preferir).
   - **Database Password:** Escolha uma senha forte e guarde-a com segurança.
   - **Region:** Selecione **`South America (São Paulo) - sa-east-1`** (para garantir a menor latência possível no Brasil).
   - **Pricing Plan:** Selecione o plano **Free** (Custo Zero).
4. Clique em **"Create new project"** e aguarde cerca de 1 a 2 minutos até o banco ser provisionado.

---

## 2. Obtendo as Chaves de Acesso e URL

No painel do seu projeto no Supabase:

1. No menu lateral esquerdo, clique no ícone de engrenagem **"Project Settings"** (Configurações do Projeto).
2. Clique na aba **"API"**.
3. Copie os seguintes dados:
   - **Project URL:** Exemplo: `https://xyzabcdefghijklm.supabase.co`
   - **Project API keys -> `anon` (public):** Chave anônima pública.
   - **Project API keys -> `service_role` (secret):** Chave mestra do assistente (clique em *Reveal* para copiar).

> [!CAUTION]
> A chave `service_role` dá acesso de superusuário ao banco para o Aton gerenciar tabelas protegidas por RLS. **Nunca compartilhe ou suba essa chave em repositórios públicos**. Ela deve ficar exclusivamente no seu arquivo `.env` local.

---

## 3. Configurando o Arquivo `.env` do Aton

No diretório raiz do projeto `amr/`, abra o seu arquivo `.env` (se não existir, copie de `.env.example`) e adicione as seguintes variáveis:

```env
# ==========================================
# SEGUNDO CÉREBRO: SUPABASE & PGVECTOR
# ==========================================
SUPABASE_URL=https://seu-projeto-id.supabase.co
SUPABASE_KEY=sua_chave_anon_aqui
SUPABASE_SERVICE_ROLE_KEY=sua_chave_service_role_aqui
```

Substitua pelos valores reais que você copiou no Passo 2.

---

## 4. Aplicando as Migrações SQL no Banco

Você pode rodar os scripts SQL diretamente pelo painel web do Supabase em menos de 3 minutos:

1. No menu lateral esquerdo do Supabase, clique em **"SQL Editor"** (ícone com código SQL).
2. Clique no botão **"New query"** (Nova consulta).
3. Abra e execute os arquivos de migração que já criamos dentro da pasta `supabase/migrations/` **na seguinte ordem**:

### Ordem de Execução:
1. `supabase/migrations/20261027000001_core_and_extensions.sql`  
   *(Ativa as extensões `pgvector`, `pgcrypto`, `unaccent` e cria as tabelas de módulos e auditoria)*
2. `supabase/migrations/20261027000002_creator_and_clients.sql`  
   *(Cria o perfil do criador, histórico de decisões, clientes e CRM)*
3. `supabase/migrations/20261027000003_projects_and_tasks.sql`  
   *(Cria as tabelas de projetos, etapas, ideias e tarefas com prioridades)*
4. `supabase/migrations/20261027000004_agenda_and_knowledge.sql`  
   *(Cria as tabelas de agenda, lembretes e base técnica de conhecimento)*
5. `supabase/migrations/20261027000005_memory_and_vectors.sql`  
   *(Cria as sessões de diálogo, a tabela de memória de longo prazo vetorial `vector(768)`, o índice HNSW e a função `buscar_memoria_hibrida`)*
6. `supabase/migrations/20261027000006_rls_and_security.sql`  
   *(Ativa o Row Level Security em 100% das tabelas, cria políticas de acesso e a função de exportação em JSON)*

> **Dica:** Para cada arquivo, cole o conteúdo no editor e clique no botão verde **"Run"** (ou aperte `Ctrl + Enter`). Ao final, aparecerá a mensagem *"Success. No rows returned"*.

---

## 5. Testando a Conexão e o Funcionamento

### Teste Rápido Automatizado:
No terminal da pasta do projeto, execute:
```bash
.\.venv\Scripts\python.exe -m pytest tests/test_second_brain.py -v
```

Todos os 9 testes do Segundo Cérebro devem passar com sucesso (`PASSED`).

### Testando na Prática por Voz ou Código:
Quando você iniciar o Aton (`run.bat`):
1. **Gravar uma memória:**
   - Diga: *"Aton, lembre-se de que no canal Alta Restauração estou adaptando o painel do Siena 2006 para uma central 2DIN com moldura sob medida."*
   - O Aton gravará o fato, gerará o embedding vetorial de 768 dimensões pelo Gemini e salvará na tabela `memoria_longo_prazo`.
2. **Consultar o cérebro:**
   - Diga: *"Aton, o que eu falei sobre a edição de vídeo do Siena?"*
   - O Aton fará a busca híbrida (similaridade semântica + texto), localizará a memória e responderá com a data exata e o contexto completo, sem inventar nada.

---

## 6. Como Adicionar Novos Módulos no Futuro

O Segundo Cérebro foi projetado com arquitetura modular desacoplada:

1. **Registro de Módulos:**
   - A tabela `modulos_sistema` armazena os módulos ativos (ex: `crm`, `agenda`, `automotivo`, `videos_youtube`, `financeiro`).
   - Para registrar um novo módulo, basta executar:
     ```sql
     INSERT INTO modulos_sistema (codigo, nome, versao, ativo, config)
     VALUES ('financeiro', 'Módulo Financeiro Pessoal', '1.0.0', true, '{"moeda": "BRL"}');
     ```
2. **Criação da Migração:**
   - Crie um novo arquivo numerado em `supabase/migrations/`, por exemplo:  
     `20261027000007_modulo_financeiro.sql`.
   - Adicione a chave estrangeira referenciando o criador ou projeto conforme necessário.
   - Ative sempre o RLS (`ALTER TABLE ... ENABLE ROW LEVEL SECURITY;`).
3. **Exposição no Aton:**
   - Adicione a declaração da ferramenta em `src/tools/second_brain_tools.py` e vincule ao `dispatch_second_brain_tool`.
   - O assistente reconhecerá a ferramenta imediatamente em linguagem natural.
