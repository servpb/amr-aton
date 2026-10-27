# Documentação: Navegação Web e Pesquisa Automatizada (web_browser)

## 1. Objetivo
O módulo **web_browser** expande a atuação do Aton para a internet (Fase 1 - Passo 2), permitindo realizar pesquisas no Google, localizar e abrir vídeos no YouTube e navegar para páginas e sites da web diretamente através de comandos de voz da Gemini Live API.

---

## 2. Componentes e Estrutura

| Arquivo | Responsabilidade |
| :--- | :--- |
| `src/tools/web_browser.py` | Lógica de normalização de URLs, montagem de pesquisas codificadas, integração com Playwright e abertura no navegador padrão do Windows via `webbrowser`. |
| `src/tools/__init__.py` | Agregação da lista unificada `ALL_ATON_TOOLS` (Windows + Web) e despachante global `dispatch_tool()`. |
| `src/core/live_client.py` | Transmissão de todas as 6 ferramentas ativas na sessão WebSocket bidirecional. |
| `tests/test_web_browser.py` | Suíte de testes unitários automatizados cobrindo geração de URLs, buscas e despachante unificado. |

---

## 3. Ferramentas Disponíveis no Gemini Live

### 3.1. `web_search`
- **Descrição:** Realiza pesquisas de tópicos, dúvidas, notícias ou informações no Google.
- **Parâmetros:**
  - `query` (string, obrigatório): Termo de pesquisa ou pergunta.
- **Exemplo Falado:** *"Aton, pesquise no Google qual a cotação do dólar hoje"* ou *"Aton, pesquise sobre inteligência artificial"*.

### 3.2. `search_youtube`
- **Descrição:** Pesquisa e abre diretamente o termo desejado no YouTube.
- **Parâmetros:**
  - `query` (string, obrigatório): Título do vídeo, nome da música, artista ou tema.
- **Exemplo Falado:** *"Aton, pesquise no YouTube música lo-fi para estudar"* ou *"Aton, pesquise no YouTube trailer do novo filme"*.

### 3.3. `open_webpage`
- **Descrição:** Abre um endereço ou domínio específico no navegador de internet.
- **Parâmetros:**
  - `url` (string, obrigatório): Endereço do site (ex: *"github.com"*, *"g1.globo.com"*, *"wikipedia.org"*).
- **Exemplo Falado:** *"Aton, abra o site do GitHub"* ou *"Aton, abra wikipedia.org"*.

---

## 4. Integração Playwright e Fallback Gracioso

- **Com Playwright instalado:** Suporta controle avançado de Chromium headless para extração textual e leitura de páginas.
- **Modo Nativo (Zero Configuração):** Utiliza o navegador padrão já instalado e configurado no Windows pelo usuário (Google Chrome, Microsoft Edge, Brave, Firefox), garantindo velocidade instantânea e sem necessidade de downloads pesados.

---

## 5. Como Testar

Para executar a suíte automatizada de testes da ferramenta web:
```powershell
.\run.bat test
```
Ou diretamente:
```powershell
python -m pytest tests/test_web_browser.py
```

### Teste Interativo por Voz:
1. Inicie o Aton:
   ```powershell
   .\run.bat
   ```
2. Acorde o assistente dizendo *"Aton"* (ou pressione `[ENTER]`).
3. Diga: *"Aton, pesquise no YouTube sobre música clássica"*.
4. O navegador abrirá instantaneamente na página de resultados do YouTube enquanto o Aton confirma por voz: *"Pesquisando sobre música clássica no YouTube, senhor."*.
