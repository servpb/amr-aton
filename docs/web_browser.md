# Documentação: Navegação Web e Pesquisa Automatizada (web_browser)

## 1. Objetivo
O módulo **web_browser** expande a atuação do Aton para a internet (Fase 1 - Passo 2), permitindo realizar pesquisas no Google, localizar e abrir vídeos no YouTube, reproduzir músicas/vídeos diretamente no PC sem degradar para busca (`play_pc_youtube`) e navegar para páginas e sites da web diretamente através de comandos de voz da Gemini Live API.

---

## 2. Componentes e Estrutura

| Arquivo | Responsabilidade |
| :--- | :--- |
| `src/tools/web_browser.py` | Lógica de normalização de URLs, montagem de pesquisas codificadas, reprodução direta no YouTube do PC (`play_pc_youtube`), verificação honesta de player via medidor de pico de áudio (`IAudioMeterInformation`), integração com Playwright e abertura no navegador padrão do Windows via `webbrowser`. |
| `src/core/destination_guard.py` | Roteamento estrito de intenção (tocar vs. pesquisar) e resolução de destino (PC vs. Fire Stick). |
| `src/tools/task_tools.py` | Resolução de escolhas ordinais ("a segunda", "a primeira") vinculando à reprodução correta no PC (`play_pc_youtube`) ou Fire TV (`play_fire_tv_youtube`). |
| `src/tools/__init__.py` | Agregação da lista unificada `ALL_ATON_TOOLS` e despachante global `dispatch_tool()`. |
| `tests/test_youtube_routing_and_pc_playback.py` | Suíte de testes automatizados cobrindo os 8 cenários de intenção, precedência de destino, autoplay bloqueado e isolamento de falha. |
| `tests/test_web_browser.py` | Suíte de testes unitários automatizados cobrindo geração de URLs, buscas e despachante web. |

---

## 3. Ferramentas Disponíveis no Gemini Live

### 3.1. `play_pc_youtube`
- **Descrição:** Pesquisa e reproduz diretamente uma música ou vídeo no navegador padrão do computador, abrindo `https://www.youtube.com/watch?v={video_id}`.
- **Diferenciação Estrita (Tocar vs. Pesquisar):** Quando o usuário pede *"toque Roberto Carlos"*, o Aton localiza o ID real do vídeo e inicia a reprodução direta. Nunca transforma silenciosamente um pedido de reprodução em página de resultados de busca.
- **Apresentação de Opções para Pedidos Genéricos:** Para pedidos genéricos como *"toque uma música do Roberto Carlos"*, apresenta opções reais encontradas e guarda a ordem no contexto de tarefa, aguardando confirmação como *"a segunda"* ou *"pode colocar a primeira"*.
- **Verificação Honesta de Autoplay:** Como navegadores modernos do Windows podem bloquear autoplay com som até haver interação do usuário, o Aton monitora as sessões de áudio do Windows via `IAudioMeterInformation`. Sem evidência sonora positiva dentro de 2,5s, reporta honestamente em estado inconclusivo: *"Abri o vídeo '...', mas não consegui confirmar a reprodução automática. Pode ser necessário clicar para reproduzir."*
- **Parâmetros:**
  - `query` (string, opcional): Título da música, vídeo ou artista.
  - `video_id` (string, opcional): ID direto do vídeo no YouTube.

### 3.2. `search_youtube`
- **Descrição:** Abre a página de resultados de pesquisa do YouTube (`https://www.youtube.com/results?search_query=...`).
- **Parâmetros:**
  - `query` (string, obrigatório): Termo de busca no YouTube.
- **Exemplo Falado:** *"Aton, pesquise no YouTube vídeos sobre inteligência artificial"*.

### 3.3. `web_search`
- **Descrição:** Realiza pesquisas de tópicos, dúvidas, notícias ou informações no Google.
- **Parâmetros:**
  - `query` (string, obrigatório): Termo de pesquisa ou pergunta.
- **Exemplo Falado:** *"Aton, pesquise no Google qual a cotação do dólar hoje"*.

### 3.4. `open_webpage`
- **Descrição:** Abre um endereço ou domínio específico no navegador de internet.
- **Parâmetros:**
  - `url` (string, obrigatório): Endereço do site (ex: *"github.com"*, *"g1.globo.com"*).

---

## 4. Regras de Roteamento de Destino (PC vs. Fire Stick)

1. **Precedência da Fala Explícita:** Se o usuário disser *"no Fire Stick"*, executa no Fire Stick mesmo que o contexto anterior fosse PC. Se disser *"no computador"*, executa no PC mesmo que o contexto anterior fosse Fire Stick.
2. **Contexto Ativo de Sessão:** Na ausência de destino na fala, utiliza o contexto ativo válido da sessão.
3. **Pergunta Verbal se Ambíguo:** Se não houver fala explícita e não houver contexto anterior, o assistente bloqueia a execução física e pergunta: *"No computador ou no Fire Stick?"*.

---

## 5. Como Testar

Para executar a suíte automatizada de testes:
```powershell
.venv\Scripts\python.exe -m pytest tests/test_youtube_routing_and_pc_playback.py tests/test_web_browser.py tests/test_destination_guard.py -v
```
