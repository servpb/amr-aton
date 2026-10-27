# Documentação: Gerenciador de Aplicativos e Janelas do Windows (windows_apps)

## 1. Objetivo
O módulo **windows_apps** implementa a camada de automação local do Windows (Fase 1 do Aton), permitindo abrir softwares, executar programas utilitários, abrir links/navegadores, listar aplicativos em execução e encerrar processos através de comandos de voz naturais processados via *Tool Calling* da Gemini Live API.

---

## 2. Componentes e Estrutura

| Arquivo | Responsabilidade |
| :--- | :--- |
| `src/tools/windows_apps.py` | Lógica de resolução de nomes, execução de subprocessos (`subprocess.Popen` desanexado) e encerramento de processos via `taskkill`. |
| `src/tools/__init__.py` | Exportação de funções e declarações de ferramentas (*Function Declarations*). |
| `src/core/live_client.py` | Registro dos esquemas de ferramentas em `LiveConnectConfig(tools=...)` e envio de retorno via `send_tool_response()`. |
| `src/core/assistant.py` | Despacho assíncrono em thread separada no método `_handle_tool_call()`, mantendo o fluxo de áudio ininterrupto. |
| `tests/test_windows_apps.py` | Bateria de testes unitários automatizados com mocks de processos do Windows. |

---

## 3. Ferramentas Disponíveis no Gemini Live

### 3.1. `open_application`
- **Descrição:** Abre um programa instalado no computador ou um endereço da web.
- **Parâmetros:**
  - `app_name` (string, obrigatório): Nome amigável do programa (ex: *"bloco de notas"*, *"calculadora"*, *"chrome"*, *"vscode"*, *"spotify"*) ou URL (*"youtube.com"*).
  - `args` (string, opcional): Parâmetros adicionais para a linha de comando.
- **Exemplo Falado:** *"Aton, abra a calculadora"* ou *"Aton, abra o Bloco de Notas"*.

### 3.2. `close_application`
- **Descrição:** Encerra uma janela, aplicativo ou processo em execução no Windows com inteligência em 3 níveis:
  1. **Fechamento de Janela Ativa:** Suporte a termos como *"janela ativa"*, *"tela atual"*, fechando o primeiro plano via mensagem Win32 `WM_CLOSE`.
  2. **Fechamento por Título de Janela:** Identifica abas/janelas abertas como *"YouTube"*, *"Netflix"* via `pygetwindow` e aciona `win.close()` sem derrubar todo o navegador.
  3. **Encerramento de Processo com Fallback Forçado (`/F`):** Executa `taskkill /im target.exe /t` gracioso; se houver recusa por subprocessos protegidos (como Edge e Chrome), aciona automaticamente `taskkill /f /im target.exe /t`.
- **Parâmetros:**
  - `app_name` (string, obrigatório): Nome do programa, aba/site (ex: *"YouTube"*), ou *"janela ativa"*.
- **Exemplo Falado:** *"Aton, feche o YouTube"*, *"Aton, feche a tela atual"* ou *"Aton, feche o Edge"*.

### 3.3. `list_running_applications`
- **Descrição:** Consulta a lista de processos conhecidos e janelas ativas no momento via `tasklist`.
- **Exemplo Falado:** *"Aton, quais programas estão abertos?"*.

---

## 4. Tabela de Atalhos Suportados

| Termo em Português | Termo em Inglês | Alvo Windows / Executável |
| :--- | :--- | :--- |
| bloco de notas | notepad | `notepad.exe` |
| calculadora | calc, calculator | `calc.exe` / `calculator:` |
| navegador, chrome | google chrome | `chrome.exe` |
| edge | microsoft edge | `msedge.exe` |
| explorador, arquivos | explorer | `explorer.exe` |
| terminal, prompt | cmd, powershell | `cmd.exe` / `powershell.exe` |
| gerenciador de tarefas | task manager | `taskmgr.exe` |
| paint | paint | `mspaint.exe` |
| configurações | settings | `ms-settings:` |
| vs code | code, vscode | `code.cmd` |
| spotify | spotify | `spotify.exe` |
| links da web (ex: `youtube.com`) | urls | `https://...` (via navegador padrão) |

---

## 5. Como Testar

Para rodar os testes unitários do módulo de aplicativos do Windows:
```powershell
.\run.bat test
```
Ou diretamente:
```powershell
python -m pytest tests/test_windows_apps.py
```

### Teste Interativo por Voz:
1. Inicie o assistente:
   ```powershell
   .\run.bat
   ```
2. Fale: *"Aton"* (ou aperte `[ENTER]`).
3. Diga: *"Aton, abra a calculadora"*.
4. A Calculadora do Windows se abrirá instantaneamente enquanto o Aton confirma por voz: *"Calculadora aberta com sucesso, senhor."*.
