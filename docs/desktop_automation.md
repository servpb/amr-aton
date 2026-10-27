# Documentação: Automação de Digitação, Documentos e Teclado no Windows (Fase 7)

## 1. Visão Geral do Módulo
O módulo de **Automação de Desktop** capacita o **Aton** a interagir diretamente com softwares em execução na tela do Windows, fornecendo:
1. **Digitação Universal em Janelas Ativas:** Digitação ou injeção rápida de texto com fidelidade total a acentos, cedilhas, quebras de linha e pontuação em qualquer editor (Bloco de Notas, Word, Excel, navegadores e formulários web).
2. **Criação e Abertura Instantânea de Documentos:** Geração nativa de arquivos `.docx` (Word), `.xlsx` (Excel), `.txt`, `.csv` e `.md` gravados na pasta Documentos e abertos automaticamente pelo sistema operacional.
3. **Atalhos e Controle de Teclado:** Execução de comandos como salvar (`Ctrl+S`), selecionar tudo (`Ctrl+A`), copiar/colar (`Ctrl+C`, `Ctrl+V`), `Enter`, `Tab` e `Esc`.
4. **Foco Dinâmico de Janelas:** Identificação e restauração de janelas abertas para primeiro plano antes da digitação.

---

## 2. Como Funciona a Arquitetura (`src/tools/desktop_automation.py`)

### A. Injeção Rápida de Texto com Fidelidade de Acentuação
- Em vez de simular caractere por caractere (o que pode sofrer atrasos ou corromper acentos do teclado ABNT2 como *ã*, *é*, *ç*), o Aton utiliza a biblioteca `pyperclip` para alimentar a área de transferência com o texto completo em UTF-8 e envia a combinação `Ctrl+V` via `pyautogui.hotkey`.
- O conteúdo original da área de transferência é preservado e restaurado logo após a colagem.

### B. Geração Nativa de Documentos Office
- **Microsoft Word (`docx`):**
  - Utiliza `python-docx` para criar documentos estruturados com títulos (`Heading 1`) e parágrafos limpos.
- **Microsoft Excel (`xlsx`):**
  - Utiliza `openpyxl` para criar planilhas eletrônicas. O Aton reconhece automaticamente delimitadores como ponto e vírgula (`;`), vírgula (`,`), tabulação (`\t`) ou barra vertical (`|`), convertendo dados numéricos para células com tipos de dados adequados.
- **Bloco de Notas & Texto Puro (`txt`, `md`, `csv`):**
  - Escrita direta com codificação UTF-8 padrão.
- **Abertura Automática:**
  - Acionada via `os.startfile(filepath)`, utilizando os manipuladores de arquivo nativos do Windows.

---

## 3. Ferramentas Disponíveis (*Tool Calling* para Gemini Live)

### A. `type_text_in_active_window`
- **Descrição:** Digita ou cola texto diretamente na janela ativa ou no aplicativo indicado.
- **Parâmetros:**
  - `text` *(string, obrigatório)*: Texto a ser inserido.
  - `app_name` *(string, opcional)*: Aplicativo para focar antes de digitar (ex: `'notepad'`, `'word'`, `'excel'`, `'chrome'`, `'edge'`).
  - `press_enter` *(boolean, opcional)*: Se verdadeiro, pressiona a tecla Enter após digitar.
- **Exemplo de Retorno:**
```json
{
  "status": "success",
  "message": "Texto inserido com sucesso no notepad.",
  "text_length": 54
}
```

### B. `create_and_open_document`
- **Descrição:** Cria um novo arquivo de texto, Word ou planilha Excel com o conteúdo desejado e abre no aplicativo padrão.
- **Parâmetros:**
  - `file_name` *(string, obrigatório)*: Nome do arquivo (ex: `'relatorio'`, `'planilha_compras'`).
  - `content` *(string, obrigatório)*: Conteúdo do documento. Para planilhas, separe colunas por `;`, `,` ou tabulação.
  - `file_type` *(string, opcional)*: Tipo do arquivo: `'txt'`, `'docx'`, `'xlsx'`, `'csv'`, `'md'`. Padrão é `'txt'`.
- **Exemplo de Retorno:**
```json
{
  "status": "success",
  "message": "Documento 'relatorio.docx' criado com sucesso e aberto no Microsoft Word.",
  "file_path": "C:\\Users\\ODE\\Documents\\relatorio.docx",
  "file_type": "docx"
}
```

### C. `send_keyboard_shortcut`
- **Descrição:** Envia um atalho de teclado para o Windows ou aplicativo em foco.
- **Parâmetros:**
  - `shortcut` *(string, obrigatório)*: Combinação de teclas (ex: `'ctrl+s'`, `'ctrl+a'`, `'enter'`, `'tab'`).
  - `app_name` *(string, opcional)*: Aplicativo para focar antes de enviar o atalho.

### D. `focus_application_window`
- **Descrição:** Traz a janela de um aplicativo específico para o primeiro plano na tela.
- **Parâmetros:**
  - `app_name` *(string, obrigatório)*: Nome do aplicativo (ex: `'notepad'`, `'word'`, `'excel'`, `'chrome'`).

---

## 4. Como Testar Automatizadamente

Execute a suíte de testes de automação de desktop:
```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_desktop_automation.py -v
```

Casos cobertos:
- Digitação via injeção de clipboard com suporte a acentos.
- Digitação com envio de tecla Enter.
- Criação e integridade de arquivo de texto `.txt`.
- Geração de documento binário do Word `.docx`.
- Geração de planilha estruturada do Excel `.xlsx`.
- Envio de atalhos simples e combinados (`Ctrl+S`, `Enter`).
- Localização e foco de janelas via `pygetwindow`.
- Roteamento pelo despachante unificado `dispatch_tool` e presença em `ALL_ATON_TOOLS` (35 ferramentas ativas).
