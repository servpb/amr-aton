# Módulo de Memória Semântica Local e Briefing Diário — ATON

Este documento detalha o módulo de **Memória Semântica Local** e rotina matinal autônoma de **Resumo Executivo Diário** (*Daily Briefing*) do assistente Aton.

---

## 1. Objetivo

Permitir ao Aton reter fatos, preferências, instruções e regras pessoais do usuário com persistência permanente em banco de dados local SQLite (`amr_memory.db`), além de orquestrar a síntese de agenda, tarefas pendentes e e-mails não lidos em um resumo executivo falado.

---

## 2. Componentes e Estrutura

| Arquivo | Responsabilidade |
| :--- | :--- |
| `src/core/memory.py` | Gerenciador de conexão SQLite, persistência relacional, busca textual e agregação de briefing diário. |
| `src/tools/__init__.py` | Registro dos esquemas de *Tool Calling* em `ALL_ATON_TOOLS`. |
| `tests/test_memory.py` | Bateria de testes automatizados unitários cobrindo CRUD de memórias e síntese de briefing. |

---

## 3. Ferramentas Integradas

### 3.1. `remember_fact`
- **Descrição:** Armazena ou atualiza uma preferência, fato ou regra informada pelo usuário.
- **Parâmetros:**
  - `category` (string, obrigatório): Categoria do fato (`preferência`, `trabalho`, `pessoal`, `rotina`, `regras`).
  - `key` (string, obrigatório): Chave identificadora única (ex: `formato_video`, `cafe_favorito`).
  - `content` (string, obrigatório): Conteúdo completo do fato ou preferência.
- **Exemplo Falado:** *"Aton, lembre-se de que eu prefiro exportar vídeos sempre em 4K a 60 frames."*

### 3.2. `recall_memory`
- **Descrição:** Recupera fatos ou preferências guardadas com base em palavras-chave ou categoria.
- **Parâmetros:**
  - `query` (string, opcional): Termo de busca textual.
  - `category` (string, opcional): Filtragem por categoria.
- **Exemplo Falado:** *"Aton, o que você lembra sobre minhas preferências de edição de vídeo?"*

### 3.3. `forget_memory`
- **Descrição:** Remove um registro ou regra previamente memorizada.
- **Parâmetros:**
  - `key` (string, obrigatório): Chave do registro a ser esquecido.
- **Exemplo Falado:** *"Aton, esqueça a minha preferência de formato de vídeo."*

### 3.4. `get_daily_briefing`
- **Descrição:** Agrega de forma autônoma os eventos do Google Calendar para o dia, tarefas pendentes do Google Tasks e e-mails não lidos do Gmail, retornando um relatório executivo para síntese de áudio.
- **Exemplo Falado:** *"Aton, qual é o meu resumo diário de hoje?"* ou *"Aton, como está o meu dia?"*

---

## 4. Esquema de Banco de Dados Local

Tabela `memories` no SQLite (`amr_memory.db`):
```sql
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    key TEXT NOT NULL UNIQUE,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memories_key ON memories(key);
CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
```

---

## 5. Como Testar

Execute a suíte de testes de memória via terminal:
```powershell
.\.venv\Scripts\pytest.exe tests/test_memory.py -v
```
