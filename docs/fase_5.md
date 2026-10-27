# Documentação: Fase 5 - Memória Semântica de Longo Prazo & Resumo Executivo Matinal

## 1. Visão Geral e Objetivos
A **Fase 5** coroa a evolução do **Aton**, conferindo ao assistente a capacidade de recordar preferências duradouras, fatos pessoais, regras de trabalho e rotinas através de um banco de dados relacional local persistente em SQLite (`amr_memory.db`).

Além disso, introduz a rotina executiva de **Resumo Matinal (Daily Briefing)**, que consolida de forma autônoma a agenda do dia, as tarefas pendentes, os e-mails não lidos e as preferências do usuário em um discurso de alto impacto, no melhor estilo J.A.R.V.I.S.

---

## 2. Como Funciona a Arquitetura

### A. Banco de Dados Local Persistente em SQLite (`src/core/memory.py`)
- **Tabela `memories`:**
  - `id`: Chave primária autoincrementada.
  - `category`: Categoria de contexto (`preferência`, `trabalho`, `pessoal`, `rotina`).
  - `key`: Identificador único indexado (ex: `resolucao_video`, `aniversario`).
  - `content`: Texto detalhado do fato ou instrução.
  - `created_at` e `updated_at`: Timestamps em padrão UTC ISO 8601.
- **Normalização Inteligente de Texto:**
  - O motor de busca utiliza remoção de acentos (`unicodedata.normalize('NFKD')`), limpeza de pontuação e divisão em tokens para garantir correspondência exata mesmo quando o usuário fala termos com ou sem acentos (ex: *"resolução"* encontra *"resolucao_video"*).

### B. Resumo Executivo Matinal (`get_daily_briefing`)
- Agrega automaticamente:
  1. **Google Calendar:** Próximos compromissos de hoje.
  2. **Google Tasks:** Lista de tarefas e afazeres pendentes.
  3. **Gmail:** Quantidade e remetentes dos e-mails não lidos mais recentes.
  4. **Saudação Contextual:** Varia de acordo com a hora do dia (*Bom dia*, *Boa tarde*, *Boa noite*).

---

## 3. Ferramentas Disponíveis (*Tool Calling* para Gemini Live)

### A. `remember_fact`
- **Descrição:** Armazena preferências e fatos permanentes na memória de longo prazo.
- **Parâmetros:**
  - `key` *(string, obrigatório)*: Identificador curto do fato (ex: `'resolucao_video'`).
  - `content` *(string, obrigatório)*: Descrição completa (ex: `'O usuário prefere exportar vídeos em 4K 60fps'`).
  - `category` *(string, opcional)*: Categoria (`'preferência'`, `'trabalho'`, `'pessoal'`, `'rotina'`).
- **Exemplo de Retorno:**
```json
{
  "status": "success",
  "message": "Com certeza, senhor. Registrei em minha memória de longo prazo que: O usuário prefere exportar vídeos em 4K 60fps.",
  "key": "resolucao_video"
}
```

### B. `recall_memory`
- **Descrição:** Consulta fatos, preferências e memórias guardadas por palavra-chave ou categoria.
- **Parâmetros:**
  - `query` *(string, obrigatório)*: Assunto ou pergunta (ex: `'qual resolução de vídeo?'`).
  - `category` *(string, opcional)*: Filtro de categoria.
- **Exemplo de Retorno:**
```json
{
  "status": "success",
  "message": "Consultando minhas memórias sobre 'resolução', recordo-me de que: 'O usuário prefere exportar vídeos em 4K 60fps'.",
  "count": 1
}
```

### C. `forget_memory`
- **Descrição:** Remove uma lembrança ou preferência específica da memória permanente.
- **Parâmetros:**
  - `key` *(string, obrigatório)*: Identificador da memória a ser excluída.

### D. `get_daily_briefing`
- **Descrição:** Gera o resumo matinal agregando compromissos, tarefas e e-mails do dia.
- **Exemplo de Resposta Sintetizada:**
```
"Bom dia, senhor! Aqui está o seu resumo executivo de hoje. Na sua agenda, você tem 2 compromissos: Reunião de Diretoria às 14:00; Alinhamento Técnico às 16:30. Nas tarefas pendentes, você possui 2 itens: 'Revisar relatório trimestral'; 'Enviar proposta para cliente'. No Gmail, há 1 novo e-mail não lido: de Ana Gerente sobre 'Aprovação do Projeto'. Estou à disposição para o que precisar. Desejo um excelente e produtivo dia!"
```

---

## 4. Integração no Cérebro do Aton e Painel Móvel
- **28 Ferramentas Ativas:** Todas as ferramentas de Sistema, Web, Smart TV, Celular, IoT, GPS, Agenda, Gmail, Tasks e Memória unificadas em `ALL_ATON_TOOLS`.
- **Painel Móvel & Carro:** Botão rápido *"📋 Resumo do Dia"* e reconhecimento por voz em linguagem natural no [src/integrations/mobile_gateway.py](file:///c:/xampp/htdocs/amr/src/integrations/mobile_gateway.py).

---

## 5. Como Testar Automatizadamente

Execute a suíte de testes da memória de longo prazo:
```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_memory.py -v
```

Casos cobertos:
- Inserção e atualização (UPSERT) de memórias na base SQLite.
- Consulta semântica com correspondência de termos e normalização fonética/gráfica.
- Exclusão com confirmação de contagem de linhas afetadas.
- Agregação do resumo executivo diário.
- Despacho unificado em `dispatch_tool` e presença em `ALL_ATON_TOOLS`.
