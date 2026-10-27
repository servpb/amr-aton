# Módulo de Autoconhecimento do Aton (Self-Knowledge & Changelog)

Este documento detalha o módulo de **Autoconhecimento do Aton**, responsável por fornecer respostas precisas, verificáveis e fundamentadas sobre a identidade, criador, arquitetura, tecnologias, ferramentas operacionais ativas, limitações reais e changelog do assistente, eliminando alucinações.

---

## 1. Objetivo e Princípios Fundamentais

Quando questionado sobre si mesmo (ex: *"quem te criou?"*, *"quais tecnologias você usa?"*, *"quais são suas ferramentas?"*, *"o que você não faz?"*), o assistente Aton não deve depender de memórias informais ou alucinar respostas genéricas de LLM. Ele consulta sua base dedicada de autoconhecimento, governada por quatro princípios:

1. **Introspecção Dinâmica a partir do Código Real:**
   - O conteúdo é gerado por inspeção automática do sistema real (`ALL_ATON_TOOLS`, `modulos_sistema`, `configuracao_sistema`, migrações e histórico).
   - Não depende de textos digitados de memória que ficariam obsoletos com o tempo.
2. **Regra de Honestidade Absoluta (Zero Hallucination):**
   - Se um fato sobre o Aton não estiver registrado na base de autoconhecimento, a resposta é padronizada e transparente:
     *"Isso não está registrado no meu autoconhecimento."*
3. **Gate de Segurança e Sigilo:**
   - O Aton recusa terminantemente qualquer consulta que tente extrair senhas, chaves de API (`GEMINI_API_KEY`, chaves do Supabase), tokens de autenticação ou credenciais confidenciais.
4. **Distinção Clara entre Aton e Gemini:**
   - O Gemini Live (com voz Aoede) é o motor de linguagem e síntese de voz em tempo real.
   - O Aton é a entidade completa de assistente desktop, com acesso direto a softwares do Windows, automação web via Playwright, controle de dispositivos na rede Wi-Fi, APIs do Google Workspace e Segundo Cérebro persistente.

---

## 2. Estrutura de Tabelas e Migration 09

A funcionalidade é suportada por duas tabelas isoladas criadas na **Migration 09** (`supabase/migrations/20261027000009_aton_self_knowledge.sql`):

### A. Tabela `aton_autoconhecimento`
Armazena os fatos estruturados sobre o assistente:
- `id` (UUID, Chave Primária).
- `categoria` (`identidade`, `tecnologia`, `arquitetura`, `capacidade`, `limitacao`, `roadmap`, `historico`, `faq`).
- `titulo` (VARCHAR, título conciso do fato).
- `conteudo` (TEXT, descrição factual completa).
- `resumo` (TEXT, resumo executivo em 1-2 frases).
- `tags` (TEXT[], palavras-chave associadas).
- `nivel_acesso` (`publico` ou `interno`).
- `fonte` (`gerado_automaticamente` ou `manual`).
- `versao_sistema` (ex: `0.8.0`).
- `versao` (INT, suporte a versionamento aditivo).
- `fato_origem_id` (UUID, auto-referência para histórico de alterações).
- `status` (`ativa`, `substituida`, `arquivada`).
- `embedding` (`vector(768)` com índice HNSW para similaridade cosseno).
- `busca_texto` (`tsvector` em português gerado via trigger).
- `deleted_at`, `created_at`, `updated_at`.

### B. Tabela `aton_changelog`
Registra a linha do tempo técnica das versões e migrações do sistema:
- `id` (UUID).
- `data` (TIMESTAMPTZ).
- `versao` (VARCHAR, ex: `0.1.0` a `0.8.0`).
- `titulo` (VARCHAR).
- `descricao` (TEXT).
- `tipo` (`migration`, `release`, `nova_tool`, `ajuste_seguranca`).
- `referencia` (VARCHAR).

---

## 3. Função RPC PostgreSQL: `buscar_autoconhecimento_hibrido`

Função com segurança definer e search_path restrito que combina busca semântica vetorial (65%) e ranqueamento textual Full-Text Search em português (35%):

```sql
SELECT * FROM public.buscar_autoconhecimento_hibrido(
    query_texto => 'quais tecnologias você utiliza',
    query_embedding => '[-0.012, 0.045, ...]'::vector(768),
    match_count => 4,
    filtro_categoria => 'tecnologia',
    filtro_nivel_acesso => 'publico'
);
```

---

## 4. Ferramenta no Gemini Live: `consultar_autoconhecimento`

Integrada ao conjunto `ALL_ATON_TOOLS` (ferramenta de número 42+):

### Declaração JSON Schema:
```json
{
  "name": "consultar_autoconhecimento",
  "description": "Consulta a base verificada de autoconhecimento do Aton sobre sua própria identidade, criador (dono de agência digital e canal Alta Restauração), arquitetura em três camadas, tecnologias reais (Python, Gemini Live, Supabase, pgvector), lista completa de ferramentas ativas, limitações reais e changelog. Responde com sinceridade e nunca expõe senhas ou chaves.",
  "parameters": {
    "type": "OBJECT",
    "properties": {
      "pergunta": {
        "type": "STRING",
        "description": "A pergunta sobre o próprio Aton (ex: 'quem é seu criador?', 'quais ferramentas você tem?', 'qual sua arquitetura?', 'o que você não faz?')."
      },
      "categoria": {
        "type": "STRING",
        "description": "Categoria opcional: 'identidade', 'tecnologia', 'arquitetura', 'capacidade', 'limitacao', 'roadmap', 'historico'."
      }
    },
    "required": ["pergunta"]
  }
}
```

---

## 5. Script de Sincronização e Introspecção

Localizado em `scripts/sincronizar_autoconhecimento.py`:
- Inspeciona dinamicamente `ALL_ATON_TOOLS` em `src/tools/__init__.py`.
- Gera 22 fatos estruturados e 8 entradas de changelog.
- Salva o cache offline imediato em `data/aton_autoconhecimento_cache.json`.
- Calcula embeddings vetoriais de 768 dimensões com o Gemini.
- Realiza upsert no Supabase na tabela `aton_autoconhecimento` e registra eventos em `aton_changelog`.

### Execução:
```powershell
.\.venv\Scripts\python.exe scripts/sincronizar_autoconhecimento.py
```

---

## 6. Como Testar

Os testes automatizados cobrem todos os critérios de aceitação:
```powershell
.\.venv\Scripts\pytest.exe tests/test_autoconhecimento.py -v
```

Casos testados:
1. `test_introspection_facts_structure`: Presença de todas as categorias e campos obrigatórios.
2. `test_changelog_structure`: Linha do tempo de releases de 0.1.0 até 0.8.0.
3. `test_local_cache_creation`: Geração íntegra do arquivo de cache `data/aton_autoconhecimento_cache.json`.
4. `test_consultar_identidade_e_criador`: Fatos sobre criador, agência digital e canal Alta Restauração.
5. `test_consultar_tecnologia`: Menção a Python, Gemini Live, Supabase e pgvector.
6. `test_consultar_capacidades_e_ferramentas`: Listagem e contagem de ferramentas ativas.
7. `test_consultar_limitacoes`: Transparência sobre limitações offline e financeiras.
8. `test_security_refusal_of_secrets`: Recusa formal e segura ao ser questionado sobre senhas/chaves.
9. `test_honesty_rule_unknown_topic`: Resposta honesta de "não registrado" para tópicos desconhecidos.
10. `test_second_brain_tool_dispatcher`: Roteamento e despacho do tool no ciclo de vida.
11. `test_tool_declarations_count`: Presença de `consultar_autoconhecimento` em `ALL_ATON_TOOLS`.
