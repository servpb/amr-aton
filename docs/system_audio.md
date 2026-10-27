# Módulo de Controle de Áudio e Multimídia do Windows — ATON

Este documento detalha o módulo de **Controle de Volume Mestre e Teclas Multimídia** do assistente Aton, permitindo regular o som do computador e controlar reprodução de mídia por voz.

---

## 1. Objetivo

Permitir ao Aton ajustar o volume geral do Windows (0% a 100%), mutar/desmutar o áudio do computador via API de baixo nível `pycaw`, e emitir comandos multimídia globais (play, pause, avançar faixa, retroceder faixa, parar) através de códigos virtuais de teclado do Windows (`user32.keybd_event`).

---

## 2. Componentes e Estrutura

| Arquivo | Responsabilidade |
| :--- | :--- |
| `src/tools/system_audio.py` | Integração com `pycaw` (Core Audio Windows) para controle do endpoint master e despacho de eventos Win32 de mídia. |
| `src/tools/__init__.py` | Registro das ferramentas `set_system_volume` e `control_system_media` em `ALL_ATON_TOOLS`. |
| `tests/test_system_audio.py` | Testes automatizados cobrindo alterações de volume, mutação e despacho de teclas de mídia. |

---

## 3. Ferramentas Integradas

### 3.1. `set_system_volume`
- **Descrição:** Ajusta o volume mestre do computador ou ativa/desativa o modo mudo.
- **Parâmetros:**
  - `level` (inteiro, opcional): Nível percentual de volume desejado (de `0` a `100`).
  - `mute` (booleano, opcional): `True` para silenciar o computador, `False` para restaurar o som.
- **Exemplo Falado:**
  - *"Aton, ajuste o volume para 50%."*
  - *"Aton, mute o som do computador."*
  - *"Aton, ative o som novamente no volume 30%."*

### 3.2. `control_system_media`
- **Descrição:** Envia comandos universais de reprodução multimídia para o aplicativo ativo (Spotify, YouTube, VLC, reprodutores de mídia).
- **Parâmetros:**
  - `action` (string, obrigatório): Ação multimídia desejada:
    - `'play'` ou `'pause'`: Alterna entre tocar e pausar (`VK_MEDIA_PLAY_PAUSE = 0xB3`).
    - `'next'` ou `'proxima'`: Avança para a próxima música/faixa (`VK_MEDIA_NEXT_TRACK = 0xB0`).
    - `'previous'`, `'anterior'` ou `'prev'`: Volta para a faixa anterior (`VK_MEDIA_PREV_TRACK = 0xB1`).
    - `'stop'` ou `'parar'`: Interrompe a reprodução (`VK_MEDIA_STOP = 0xB2`).
- **Exemplo Falado:**
  - *"Aton, pause a música."*
  - *"Aton, passe para a próxima faixa."*
  - *"Aton, volte para a música anterior."*

---

## 4. Teclas Virtuais Win32 Suportadas

```python
VK_MEDIA_NEXT_TRACK = 0xB0      # Próxima faixa
VK_MEDIA_PREV_TRACK = 0xB1      # Faixa anterior
VK_MEDIA_STOP = 0xB2            # Parar reprodução
VK_MEDIA_PLAY_PAUSE = 0xB3      # Play / Pause universal
```

---

## 5. Como Testar

Execute a suíte de testes de controle de áudio via terminal:
```powershell
.\.venv\Scripts\pytest.exe tests/test_system_audio.py -v
```
