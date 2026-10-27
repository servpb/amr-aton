# Segundo Cérebro do Aton (Supabase + pgvector + Busca Híbrida)

Este documento descreve a arquitetura técnica, modelo relacional, pipeline de consolidação e integração em tempo real do **Segundo Cérebro do Aton**, inspirado no J.A.R.V.I.S., projetado para armazenar e recuperar memórias permanentes, contexto do criador, clientes, projetos, tarefas e agenda.

---

## 1. Visão Geral e Princípios de Arquitetura

O Segundo Cérebro do Aton resolve a amnésia de modelos conversacionais e transcende a memória volátil de sessão através de quatro pilares:

1. **Persistência Total em Nuvem (Supabase / PostgreSQL):**
   - Banco de dados relacional de alta performance hospedado no Supabase.
   - Extensão `pgvector` nativa para indexação vetorial HNSW (Hierarchical Navigable Small World).
   - Extensão `unaccent` e dicionário em português (`portuguese`) para busca textual completa (Full-Text Search com `tsvector`/`tsquery`).
2. **Busca Híbrida com RRF (Reciprocal Rank Fusion):**
   - Não depende apenas de busca vetorial (que pode falhar em códigos exatos, datas ou placas de veículos) nem apenas de palavras-chave (que falha em analogias e sinônimos).
   - Combinação ponderada calculada diretamente no banco de dados via RPC PostgreSQL `buscar_memoria_hibrida`:
     - **65% de relevância:** Similaridade Cosseno (`1 - (embedding <=> query_embedding)`).
     - **35% de relevância:** Rank Textual ponderado com remoção de acentos (`ts_rank_cd(busca_texto, ...)`).
     - **Bônus de importância:** até +12% para memórias classificadas com importância 4 ou 5.
3. **Respostas Factuais Sem Alucinação (Zero Hallucination Gate):**
   - O método `ask_brain` consulta a base vetorial/textual.
   - Se nenhuma memória relevante for encontrada com score mínimo, o Aton responde de forma transparente e assertiva: *"Não encontrei nenhuma anotação registrada sobre isso em minha base de conhecimento"*, jamais inventando fatos.
   - Quando encontra, cita explicitamente as datas de registro e fontes de contexto (ex: *"De acordo com seu registro de 27/10/2026 sobre o canal Alta Restauração..."*).
4. **Resiliência Offline / Fallback Local:**
   - Caso o assistente esteja sem conexão com a internet ou as variáveis do Supabase não estejam preenchidas, o cliente `SecondBrainClient` comuta automaticamente para o SQLite local (`amr_memory.db`), garantindo disponibilidade ininterrupta.

---

## 2. Modelo Relacional e Tabelas Criadas

O ecossistema é composto por 6 migrações SQL aplicadas em ordem:

| Tabela | Objetivo Principal | RLS & Segurança |
| :--- | :--- | :--- |
| `perfil_criador` | Dados do criador, bio, negócios (agência digital, canal Alta Restauração), valores e preferências. | Ativo (Somente Leitura Geral / Escrita Restrita) |
| `historico_decisoes` | Registro de decisões passadas, lições aprendidas e motivos de escolhas. | Ativo |
| `clientes` | CRM: empresas, contatos, valor mensal recorrente, entregáveis e status. | Ativo |
| `contatos_clientes` | Pessoas de contato vinculadas a cada cliente (nome, cargo, telefone, e-mail). | Ativo |
| `interacoes_clientes` | Histórico de reuniões, e-mails e feedbacks de clientes. | Ativo |
| `projetos` | Projetos ativos, canal YouTube, clientes atendidos e orçamentos. | Ativo |
| `etapas_projeto` | Milestones e fases de cada projeto. | Ativo |
| `ideias_projetos` | Backlog de ideias de vídeos, melhorias e oportunidades. | Ativo |
| `tarefas` | Tarefas executivas, prioridades (baixa, média, alta, urgente) e prazos fatais. | Ativo |
| `dependencias_tarefas` | Relações de bloqueio entre tarefas (ex: comprar moldura antes de instalar). | Ativo |
| `agenda_eventos` | Compromissos e reuniões sincronizadas com Google Workspace. | Ativo |
| `lembretes_agenda` | Avisos sonoros e alertas para o assistente disparar. | Ativo |
| `base_conhecimento` | Procedimentos operacionais, manuais técnicos e especificações (ex: painéis automotivos). | Ativo |
| `conversas_sessao` | Sessões de diálogo do Aton com resumo sintético. | Ativo |
| `turnos_conversa` | Transcrições individuais de fala do criador e réplicas do assistente. | Ativo |
| `memoria_longo_prazo` | Fatos consolidados, embeddings de 768 dimensões, tags e busca de texto. | Ativo |
| `modulos_sistema` | Registro de capacidades e extensões ativas do cérebro. | Ativo |
| `auditoria_sistema` | Log imutável de todas as alterações, inserções e exclusões. | Ativo |

---

## 3. Função PostgreSQL de Busca Híbrida (`buscar_memoria_hibrida`)

Assinatura no PostgreSQL:
```sql
FUNCTION buscar_memoria_hibrida(
    query_texto text,
    query_embedding vector(768),
    match_count int DEFAULT 5,
    filtro_tipo text DEFAULT NULL,
    filtro_projeto_id uuid DEFAULT NULL,
    similaridade_minima float DEFAULT 0.20
)
RETURNS TABLE (
    id uuid,
    tipo text,
    assunto text,
    conteudo text,
    tags text[],
    importancia int,
    data_fato timestamptz,
    projeto_id uuid,
    cliente_id uuid,
    similaridade_semantica float,
    rank_textual float,
    score_final float
)
```

O índice vetorial utilizado é:
```sql
CREATE INDEX idx_memoria_embedding_hnsw 
ON memoria_longo_prazo 
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```

---

## 4. Ferramentas Integradas no Aton (Tool Calling)

O Aton possui 6 novas ferramentas dedicadas ao Segundo Cérebro, totalizando **41 ferramentas ativas**:

1. `salvar_memoria(assunto, conteudo, tipo, tags, importancia)`: Grava permanentemente um fato, decisão ou preferência.
2. `buscar_memoria(query, tipo, match_count)`: Executa busca híbrida semântica e por palavras-chave.
3. `perguntar_ao_cerebro(pergunta)`: Responde perguntas com citação de datas e contexto real, sem alucinações.
4. `criar_cliente_cerebro(nome, segmento, valor_mensal, entregaveis)`: Cadastra um cliente no CRM do Supabase.
5. `criar_tarefa_cerebro(titulo, prioridade, prazo)`: Registra uma tarefa prioritária com prazo fatal.
6. `resumo_geral_cerebro()`: Compila a visão 360 do criador (compromissos de hoje + tarefas urgentes + clientes).

---

## 5. Exemplo de Caso Real Validado em Testes

**Memória Gravada:**
- **Assunto:** *"Instalação Multimídia Siena 2006"*
- **Conteúdo:** *"Estou editando um vídeo sobre o unboxing e a instalação de uma central multimídia 2DIN em um Siena 2006, com adaptação do painel DIN que exige moldura nova."*
- **Tags:** `["alta_restauracao", "siena_2006", "central_multimidia", "edicao_video"]`
- **Importância:** `5`

**Consulta Realizada:**
- **Pergunta:** *"o que eu falei sobre edição de vídeo?"*
- **Retorno do Aton:** Responde assertivamente contextualizando o projeto do canal Alta Restauração, o Siena 2006, a multimídia 2DIN e a necessidade da moldura nova, citando a data e a fonte registrada, com 0% de alucinação.

---

## 6. Edge Functions (TypeScript / Deno)

Localizadas em `supabase/functions/`:

1. `brain-api`: Gateway RESTful que expõe endpoints unificados para CRUD de memórias, busca híbrida, CRM, tarefas e perguntas.
2. `consolidate-memory`: Rotina autônoma de consolidação que agrupa turnos de conversa recentes, gera embeddings, verifica duplicidade com limiar de similaridade cosseno `>= 0.88` e arquiva memórias duplicadas ou atualiza fatos antigos.
