# Documentação: Fase 1 - Controle do Windows & Softwares Locais

## 1. Visão Geral e Objetivos
A **Fase 1** expandiu os poderes do **Aton** para interagir diretamente com o sistema operacional Windows e com a web aberta, operando na arquitetura desacoplada de duas camadas: a camada de voz responde imediatamente por áudio confirmando a solicitação (*"Já estou abrindo, senhor"*), enquanto a ação é executada em segundo plano sem travar ou congelar a conversa.

---

## 2. Módulos e Ferramentas Desenvolvidas

### A. Gerenciamento de Aplicativos e Janelas do Windows (`src/tools/windows_apps.py`)
- **Objetivo:** Abrir, alternar, fechar e inspecionar aplicativos e programas instalados no computador.
- **Ferramentas (*Tool Calling* para Gemini Live):**
  - `open_application(app_name, bring_to_front)`: Localiza e executa executáveis nativos e softwares do usuário (ex: Bloco de Notas, Calculadora, Navegadores, Editores de Mídia).
  - `close_application(app_name)`: Encerra processos graciosamente por nome ou PID.
  - `list_running_applications(limit)`: Lista os softwares em execução com foco na janela ativa.
- **Documentado em:** [docs/windows_apps.md](file:///c:/xampp/htdocs/amr/docs/windows_apps.md).

### B. Navegação Web e Pesquisa Automatizada (`src/tools/web_browser.py`)
- **Objetivo:** Permitir que o Aton pesquise na internet, abra vídeos no YouTube ou navegue em páginas web.
- **Ferramentas (*Tool Calling* para Gemini Live):**
  - `web_search(query, search_engine)`: Pesquisa termos e assuntos diretamente no Google ou DuckDuckGo com resposta instantânea.
  - `search_youtube(query)`: Localiza e inicia a reprodução do vídeo ou música desejada no YouTube.
  - `open_webpage(url, new_window)`: Abre URLs específicas no navegador padrão do sistema.
- **Documentado em:** [docs/web_browser.md](file:///c:/xampp/htdocs/amr/docs/web_browser.md).

---

## 3. Despacho e Integração Assíncrona
- **Despachante Unificado (`src/tools/__init__.py`):** Encaminha as chamadas do modelo para as funções adequadas via `dispatch_tool`.
- **Execução não bloqueante (`src/core/assistant.py`):** Executado em threadpool (`loop.run_in_executor`) com devolução do resultado via `send_tool_response`.

---

## 4. Critérios de Pronto Atingidos (100% Concluído ✅)
- Dizer *"Aton, abra o Bloco de Notas"* e o programa abrir imediatamente com confirmação falada.
- Dizer *"Aton, pesquise no YouTube sobre [música ou tema]"* e o vídeo abrir no navegador padrão.
