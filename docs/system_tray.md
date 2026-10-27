# Módulo Residente da Bandeja do Windows (System Tray) — ATON

Este documento detalha o módulo de **Presença Residente na Bandeja do Windows** (*System Tray*) do assistente Aton, permitindo controle visual de estado e acesso rápido sem necessidade de interface gráfica pesada.

---

## 1. Objetivo

Fornecer uma presença visual silenciosa e elegante na barra de tarefas do Windows (área de notificação / *System Tray*) usando a biblioteca `pystray`. O ícone reflete dinamicamente os estados operacionais do Aton e oferece menu de contexto com atalhos de controle de ciclo de vida.

---

## 2. Componentes e Estrutura

| Arquivo | Responsabilidade |
| :--- | :--- |
| `src/integrations/system_tray.py` | Gerenciador do ícone residente, gerador dinâmico de ícones com monograma 'A' via `Pillow`, e menu de contexto. |
| `src/core/assistant.py` | Vinculação com o ciclo de vida do assistente, atualizando o estado do ícone em cada transição da máquina de estados. |
| `tests/test_system_tray.py` | Bateria de testes automatizados com mocks de thread e menu. |

---

## 3. Estados Visuais e Paleta de Cores

O ícone de alta resolução (64x64px com monograma geométrico 'A') adapta suas cores em tempo real conforme o Aton opera:

| Estado | Cor de Fundo | Borda | Significado Operacional |
| :--- | :--- | :--- | :--- |
| **`sleeping`** | Cinza Neutro (`#64748B`) | Slate Claro | Aguardando Wake Word local (*"Aton"*) ou Push-to-Talk. |
| **`listening`** | Verde Esmeralda (`#10B981`) | Menta Suave | Canal de áudio ativo ouvindo o usuário e transmitindo via WebSocket. |
| **`speaking`** | Azul Celeste (`#0EA5E9`) | Sky Blue | Assistente respondendo por voz nativa (Aoede) nos alto-falantes. |
| **`muted`** | Vermelho Alerta (`#EF4444`) | Coral | Microfone em modo mudo temporário. |

---

## 4. Menu de Contexto (Botão Direito no Ícone)

O menu de contexto na bandeja do Windows oferece:
1. **Status Dinâmico:** Exibe *"Aton: Em Repouso"*, *"Aton: Ouvindo"*, *"Aton: Falando"*, etc.
2. **Abrir Painel Mobile (HUD):** Abre o navegador no painel web local (`http://localhost:8443`).
3. **Alternar Mudo:** Muta ou desmuta o microfone de entrada.
4. **Encerrar Aton:** Finaliza graciosamente todas as threads, fecha a conexão Gemini Live e encerra a aplicação.

---

## 5. Como Testar

Execute a suíte de testes de System Tray via terminal:
```powershell
.\.venv\Scripts\pytest.exe tests/test_system_tray.py -v
```
