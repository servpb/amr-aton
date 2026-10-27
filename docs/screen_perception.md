# Módulo de Percepção Visual, Áudio e Interação com a Tela — ATON

Este documento detalha o módulo de **Percepção Visual e Interação com a Tela**, que dota o assistente Aton de visão computacional multimodal e capacidade de interação direta com interfaces gráficas do Windows, operado por comandos de voz em tempo real.

---

## 1. Visão Geral e Princípios de Privacidade

O módulo permite ao Aton compreender o que está visível no computador do usuário (aplicativos, janelas ativas, navegadores, documentos e formulários) e interagir através do mouse e teclado, respondendo por voz nativa em Português do Brasil (voz Aoede).

### Princípios Inegociáveis:
1. **Zero Captura Passiva / Contínua:** A tela **nunca** é gravada ou capturada em segundo plano sem solicitação. O Aton só realiza capturas sob demanda no exato instante em que o usuário pede verbalmente ou via atalho.
2. **Privacidade e Proteção de Segredos:** Campos de senha ou credenciais confidenciais nunca são lidos ou expostos por áudio.
3. **Portão de Confirmação para Ações de Alto Impacto:** Cliques em botões destrutivos ou transacionais (*"Excluir"*, *"Enviar mensagem"*, *"Finalizar compra"*, *"Formatar"*) exigem confirmação verbal prévia do usuário (`confirmacao_previa=True`).
4. **Comunicação Transparente de Incerteza:** Quando um elemento visual estiver ilegível, oculto ou for ambíguo, o Aton comunica verbalmente o que conseguiu identificar e pede esclarecimento, sem clicar às cegas.

---

## 2. Arquitetura Técnica em Duas Camadas

O módulo é dividido de forma desacoplada entre captura/visão e ferramentas operacionais:

```
┌────────────────────────────────────────────────────────┐
│             Usuário (Voz / Push-to-Talk)              │
│       "Aton, o que tem na tela?" / "Clique em Salvar"  │
└───────────────────────────┬────────────────────────────┘
                            ▼
┌────────────────────────────────────────────────────────┐
│             Gemini Live (Voz Aoede pt-BR)              │
│         Tool Calling com Confirmação Imediata          │
└───────────────────────────┬────────────────────────────┘
                            ▼
┌────────────────────────────────────────────────────────┐
│    src/core/screen_perceiver.py (Motor de Visão)       │
│  - Captura sob demanda (Tela inteira ou Janela ativa)  │
│  - Metadados Win32 (Título da janela ativa e processo) │
│  - Análise Multimodal Gemini Vision (Bounding Boxes)   │
│  - Mapeamento de coordenadas [ymin, xmin, ymax, xmax]  │
└───────────────────────────┬────────────────────────────┘
                            ▼
┌────────────────────────────────────────────────────────┐
│    src/tools/screen_perception.py (Ações na Interface) │
│  - descrever_tela: Explicação executiva do que se vê   │
│  - ler_conteudo_tela: Extração e leitura de trechos    │
│  - localizar_e_clicar_elemento: Clique com pyautogui   │
│  - preencher_campo_na_tela: Foco e digitação universal │
│  - rolar_tela: Scroll suave para cima/baixo            │
│  - Portão de Confirmação para Ações de Alto Impacto    │
└────────────────────────────────────────────────────────┘
```

### Componentes:
- **`src/core/screen_perceiver.py`**:
  - Inspeciona títulos e retângulos de janela ativa via Win32 API (`GetForegroundWindow`, `GetWindowTextW`, `GetWindowRect`).
  - Realiza capturas com `Pillow` (`ImageGrab`) e fallback resiliente caso o ambiente esteja bloqueado.
  - Otimiza e redimensiona a imagem para até 1280px em JPEG comprimido para envio de ultra-baixa latência.
  - Processa a imagem via SDK oficial `google-genai` com fallback automático e resiliente entre os modelos Flash disponíveis (`gemini-3.5-flash`, `gemini-3.6-flash`, etc.) e contingência REST.
  - Converte Bounding Boxes normalizadas `[ymin, xmin, ymax, xmax]` (escala de 0 a 1000) para coordenadas absolutas da tela `(screen_x, screen_y)`.
- **`src/tools/screen_perception.py`**:
  - Implementa as 5 ferramentas expostas ao Gemini Live.
  - Executa ações com `pyautogui` (movimentação suave de cursor e cliques) e `pyperclip` (digitação com suporte nativo a acentos e pontuação).

---

## 3. As 5 Ferramentas Integradas (`ALL_ATON_TOOLS`)

O Aton possui agora **49 ferramentas operacionais ativas**, incluindo:

| Ferramenta | Parâmetros | Descrição |
| :--- | :--- | :--- |
| `descrever_tela` | `alvo` ('janela_ativa'/'fullscreen'), `detalhe` ('resumo'/'detalhado') | Explica por voz o que está aberto no monitor ou janela ativa de forma executiva. |
| `ler_conteudo_tela` | `alvo`, `trecho` ('tudo' ou nome da seção) | Extrai e lê textos visíveis de documentos, mensagens, relatórios ou páginas web. |
| `localizar_e_clicar_elemento` | `descricao_elemento`, `tipo_clique` ('simples'/'duplo'/'direito'), `confirmacao_previa` | Localiza o elemento visualmente via Bounding Box e executa o clique com o mouse. |
| `preencher_campo_na_tela` | `descricao_campo`, `texto`, `alvo` | Localiza a caixa de entrada, clica para focar e insere texto via clipboard com acentuação perfeita. |
| `rolar_tela` | `direcao` ('baixo'/'cima'), `quantidade` (1 a 10) | Rola a página ou documento para cima ou para baixo para leitura contínua. |

---

## 4. Exemplos de Comandos por Voz

O usuário pode interagir naturalmente com o Aton:

- *"Aton, o que está aberto na minha tela agora?"* -> Aciona `descrever_tela()`.
- *"Aton, leia o conteúdo desse relatório na tela."* -> Aciona `ler_conteudo_tela()`.
- *"Aton, clique no botão de Salvar."* -> Aciona `localizar_e_clicar_elemento(descricao_elemento='botão salvar')`.
- *"Aton, preencha o campo de busca com 'relatório mensal'."* -> Aciona `preencher_campo_na_tela(...)`.
- *"Aton, role a página um pouco para baixo."* -> Aciona `rolar_tela(direcao='baixo', quantidade=3)`.
- *"Aton, clique em excluir este arquivo."* -> Retorna pedido de confirmação de segurança verbal antes do clique.

---

## 5. Como Testar

Os testes automatizados cobrem a detecção de janelas, otimização de imagem, cálculo de coordenadas, portão de segurança e despachantes:

```powershell
.\.venv\Scripts\pytest.exe tests/test_screen_perception.py -v
```

Resultado: **11 testes passando em 2.88s**.
Suíte completa do projeto: **171 testes aprovados sem falhas**.
