# Organizador Seguro de Arquivos Locais & Área de Trabalho (`src/tools/local_files.py`)

## 1. Visão Geral e Objetivo
O módulo **Organizador Seguro de Arquivos Locais & Área de Trabalho** do Aton permite gerenciar, localizar, resumir e organizar pastas de trabalho do usuário (como `Downloads`, `Área de Trabalho` e `Documentos`) 100% por voz com foco absoluto em **segurança, não-destruição e integridade dos dados**.

O Aton foi desenhado com base em um princípio inviolável: **ele nunca apaga arquivos do usuário** e **nunca executa movimentações de arquivos sem prévia proposta e autorização verbal explícita ("Sim")** do usuário dentro de uma janela de 60 segundos.

---

## 2. Sandbox Estrito e Pastas Autorizadas
O módulo opera com isolamento rigoroso de diretórios (`ALLOWED_USER_FOLDERS`). Qualquer tentativa de acessar ou navegar fora dessas pastas é imediatamente bloqueada com erro descritivo.

### Pastas de Usuário Permitidas:
- `downloads`: pasta de downloads do usuário (`~/Downloads`).
- `documentos`: pasta de documentos do usuário (`~/Documents` ou `~/Documentos`).
- `area_de_trabalho`: área de trabalho do usuário (`~/Desktop` ou `~/Área de Trabalho`).
- `imagens`: pasta de imagens (`~/Pictures` ou `~/Imagens`).
- `videos`: pasta de vídeos (`~/Videos` ou `~/Vídeos`).
- `documentos_aton`: pasta de saída de documentos do projeto (`output_docs/`).

### Proteções de Sandbox:
- **Bloqueio de Path Traversal (`..`):** Qualquer tentativa de subida na árvore de diretórios é abortada.
- **Resolução de Links Simbólicos e Junções NTFS (`realpath`):** Links simbólicos, junções do Windows ou redirecionamentos que apontem para fora das pastas autorizadas são validados pelo caminho canônico real e bloqueados.
- **Bloqueio de Pastas de Sistema:** `C:\Windows`, `Program Files`, `AppData`, `.git`, `.ssh`, `.venv`, `node_modules` e diretórios de tokens são inacessíveis.
- **Proteção de Arquivos Sensíveis:** Arquivos com nomes `.env*`, `credentials.json`, `token*.json`, `*.pem`, `*.key`, `*.pfx`, `*.sqlite3`, `*.db`, executáveis/scripts de sistema (`.dll`, `.sys`, `.reg`, `.bat`, `.cmd`, `.ps1`, `.vbs`) nunca são lidos nem movimentados.
- **Isolamento de Arquivos Compactados:** Arquivos `.zip`, `.rar`, `.7z`, `.tar`, `.gz` nunca são descompactados (prevenindo *zip-bombs* e execução oculta); são apenas categorizados na pasta `Compactados`.

---

## 3. Os 6 Requisitos de Segurança Implementados

| Requisito | Como o Aton Garante |
| :--- | :--- |
| **1. Links Simbólicos & Atalhos** | Validação canônica via `os.path.realpath` imediatamente antes da leitura e da movimentação física. |
| **2. Defesa contra Prompt Injection** | O conteúdo lido de qualquer arquivo é encapsulado em tags `[DADOS_BRUTOS_ARQUIVO_NAO_CONFIAVEL: ...]` e credenciais/tokens são higienizados (`[CREDENTIAL_REDACTED]`). Instruções encontradas em arquivos nunca autorizam ações ou acionam ferramentas. |
| **3. Confirmação em Duas Fases** | Token criptográfico aleatório (`arq_<hex>`), validade estrita de 60 segundos, uso único, vínculo à sessão de voz ativa e substituição automática de propostas anteriores. |
| **4. Barreira Anti-Sobrescrita Dinâmica** | Resolução atômica no momento exato do movimento: se já existir `relatorio.pdf` no destino, ele é nomeado como `relatorio (1).pdf`, `relatorio (2).pdf`, etc. Nenhum arquivo pré-existente é sobrescrito. |
| **5. Reversão Confiável (Undo)** | Cada lote confirmado é registrado na tabela `file_operations_history` do SQLite interno (`data/reminders.sqlite3`). A ferramenta `desfazer_ultima_organizacao()` restaura os arquivos às suas posições originais, também com proteção anti-sobrescrita. |
| **6. Limites Seguros de Leitura** | Limite de tamanho de arquivo de 10 MB, leitura máxima de 64 KB brutos para textos, limite de 4000 caracteres no resumo, máximo de 100 parágrafos em `.docx`, máximo de 3 abas / 30 linhas / 15 colunas em `.xlsx` e máximo de 40 linhas em `.csv`. |

---

## 4. Categorias de Organização Automática
Quando o usuário pede para organizar a pasta de `Downloads` ou a `Área de Trabalho`, arquivos soltos no diretório raiz são agrupados nas seguintes subpastas:

- `Documentos/`: `.pdf`, `.docx`, `.doc`, `.txt`, `.md`, `.pptx`, `.ppt`, `.rtf`, `.odt`
- `Planilhas/`: `.xlsx`, `.xls`, `.csv`, `.ods`
- `Imagens/`: `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`, `.svg`, `.bmp`, `.ico`
- `Videos_e_Audio/`: `.mp4`, `.mkv`, `.mov`, `.avi`, `.webm`, `.mp3`, `.wav`, `.flac`, `.ogg`, `.m4a`
- `Compactados/`: `.zip`, `.rar`, `.7z`, `.tar`, `.gz`, `.bz2`
- `Instaladores/`: `.exe`, `.msi`, `.msix`
- **Arquivos Temporários Ignorados:** Downloads parciais ou em andamento (`.crdownload`, `.part`, `.tmp`, `~$*`) permanecem intocados na raiz para evitar corrupção de downloads ativos.

---

## 5. Ferramentas de Voz Registradas

### 1. `buscar_arquivos_locais(termo_busca="", pasta="downloads", extensao="", limite=10)`
Lista arquivos na pasta indicada com nome, tamanho em KB e data de modificação.

### 2. `ler_resumo_arquivo_local(caminho_ou_nome, pasta="downloads")`
Extrai e higieniza o conteúdo de arquivos `.txt`, `.md`, `.csv`, `.json`, `.docx` e `.xlsx`, retornando o texto delimitado com aviso de dados passivos.

### 3. `propor_organizacao_pasta(pasta="downloads")`
Analisa arquivos soltos, gera a distribuição por categorias e cria um `proposal_id` com validade de 60 segundos. **Nenhum arquivo é movido neste momento**.

### 4. `propor_mover_arquivo(nome_arquivo, pasta_origem="downloads", pasta_destino="documentos", subpasta="", novo_nome="")`
Cria proposta para mover (e opcionalmente renomear) um arquivo específico entre pastas autorizadas.

### 5. `confirmar_operacao_arquivo(proposal_id)`
Executa a movimentação com tratamento de arquivos em uso (`PermissionError`), barreira anti-sobrescrita e registro do lote no SQLite.

### 6. `desfazer_ultima_organizacao()`
Reverte o último lote não desfeito registrado no SQLite, devolvendo os arquivos às suas localizações anteriores.

---

## 6. Exemplos de Diálogo por Voz
- **Usuário:** *"Aton, quais planilhas eu baixei hoje na pasta de downloads?"*
  - **Aton:** *"Encontrei 2 planilhas na sua pasta de downloads: balanco_mensal.xlsx de 45 KB e orcamento.csv de 12 KB."*
- **Usuário:** *"Organize minha pasta de downloads."*
  - **Aton:** *"Analisei sua pasta de downloads e posso organizar 14 arquivos soltos: 5 em Documentos, 3 em Planilhas, 4 em Imagens e 2 em Compactados. Downloads temporários foram ignorados. Posso confirmar a organização?"*
- **Usuário:** *"Sim."*
  - **Aton:** *"Operação concluída com sucesso: 14 arquivos movidos para suas respectivas subpastas."*
- **Usuário:** *"Aton, desfaça essa última organização."*
  - **Aton:** *"Desfazer concluído: 14 arquivos foram restaurados para a raiz da pasta de downloads."*

---

## 7. Testes Automatizados
A suíte completa em `tests/test_local_files.py` valida 100% dos requisitos usando `tmp_path` isolado sem tocar em diretórios reais do usuário:
1. `test_1_sandbox_blocks_outside_paths_and_sensitive_files`
2. `test_2_search_and_read_files_txt_docx_xlsx_with_prompt_injection_delimiters`
3. `test_3_organize_folder_requires_two_phase_confirmation_and_ignores_temp_files`
4. `test_4_move_file_never_overwrites_existing_destination_and_handles_permission_error`
5. `test_5_undo_last_organization_restores_files_to_original_locations`
6. `test_6_proposal_expiration_session_binding_and_duplicate_confirmation_blocked`
7. `test_7_symlinks_outside_sandbox_and_archives_are_strictly_blocked`
8. `test_8_dynamic_destination_conflict_during_confirmation_never_overwrites`
9. `test_9_module_registry_and_unified_dispatcher_integration`

Para rodar os testes:
```powershell
.venv\Scripts\python.exe -m pytest tests/test_local_files.py -v
```
