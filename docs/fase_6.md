# Documentação: Fase 6 - Sistema & Residente Windows (Bandeja, Telemetria & Controle de Áudio/Mídia)

## 1. Visão Geral e Objetivos
A **Fase 6** expande o alcance operacional do **Aton** diretamente no ecossistema do Windows, transformando-o em uma aplicação residente de segundo plano completa. 

Os objetivos principais desta fase foram:
1. **Presença Silenciosa e Residente:** Permitir que o assistente opere minimizado na bandeja do sistema (*System Tray*), com ícone de status dinâmico (Dormindo, Ouvindo, Falando, Mudo) e menu rápido de contexto para mutar o microfone, disparar o resumo executivo, abrir o HUD móvel ou encerrar a aplicação.
2. **Telemetria de Sistema por Voz:** Fornecer ao usuário diagnósticos rápidos do hardware do PC em linguagem natural (bateria restante, uso de processador, consumo de memória RAM e espaço livre em disco).
3. **Controle de Áudio Mestre e Multimídia:** Permitir regular o volume do Windows, silenciar o som da máquina e controlar a reprodução multimídia (Spotify, reprodutores e navegadores) por voz ou pelo painel móvel.

---

## 2. Componentes Criados e Integrados

| Componente | Arquivo | Responsabilidade |
|---|---|---|
| **System Tray** | [src/integrations/system_tray.py](file:///c:/xampp/htdocs/amr/src/integrations/system_tray.py) | Ícone dinâmico com 4 estados na bandeja do Windows e menu de contexto via `pystray` e `Pillow`. |
| **System Telemetry** | [src/tools/system_telemetry.py](file:///c:/xampp/htdocs/amr/src/tools/system_telemetry.py) | Diagnóstico de hardware (bateria, CPU, RAM e disco) via `psutil`. |
| **System Audio & Media** | [src/tools/system_audio.py](file:///c:/xampp/htdocs/amr/src/tools/system_audio.py) | Ajuste de volume mestre e mute via `pycaw`, e simulação de teclas de mídia via `ctypes`. |
| **Orquestrador Central** | [src/core/assistant.py](file:///c:/xampp/htdocs/amr/src/core/assistant.py) | Inicialização e controle de ciclo de vida da bandeja e atualização de estados do ícone. |
| **Despachante Unificado** | [src/tools/__init__.py](file:///c:/xampp/htdocs/amr/src/tools/__init__.py) | Registro de 3 novas ferramentas no `ALL_ATON_TOOLS`, totalizando **31 ferramentas ativas**. |
| **Mobile Gateway & Car HUD** | [src/integrations/mobile_gateway.py](file:///c:/xampp/htdocs/amr/src/integrations/mobile_gateway.py) | Novos botões de atalho rápido e comandos de linguagem natural para status do PC, volume e mídia. |

---

## 3. Ferramentas Adicionadas ao Gemini Live (*Tool Calling*)

1. **`get_system_telemetry(metric: str = "all")`**:
   - Responde sobre bateria, CPU, RAM e disco rígido.
   - Exemplos falados: *"Aton, como está o desempenho do computador?"*, *"Aton, quanta bateria ainda temos?"*, *"Aton, quanto espaço livre temos no disco C?"*.
2. **`set_system_volume(level: int = None, mute: bool = None)`**:
   - Ajusta o volume mestre do Windows (0 a 100%) ou coloca em mudo.
   - Exemplos falados: *"Aton, coloque o volume do computador em 30%"*, *"Aton, silencie o áudio do PC"*.
3. **`control_system_media(action: str)`**:
   - Dispara comandos de reprodução (`play_pause`, `next`, `previous`, `stop`) compatíveis com Spotify, YouTube e players de áudio/vídeo.
   - Exemplos falados: *"Aton, pause a música"*, *"Aton, passe para a próxima música"*.

---

## 4. Testes Automatizados

Foram implementadas suítes completas de testes unitários:
- [tests/test_system_telemetry.py](file:///c:/xampp/htdocs/amr/tests/test_system_telemetry.py) (5 testes)
- [tests/test_system_audio.py](file:///c:/xampp/htdocs/amr/tests/test_system_audio.py) (6 testes)
- [tests/test_system_tray.py](file:///c:/xampp/htdocs/amr/tests/test_system_tray.py) (4 testes)

Execução:
```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_system_telemetry.py tests/test_system_audio.py tests/test_system_tray.py -v
```
Resultado: **15 testes aprovados** (100% de sucesso).
Total da suíte global: **128 testes aprovados**.

---

## 5. Critério de Pronto da Fase 6

- [x] O Aton roda com ícone visual discreto na bandeja do Windows (*System Tray*).
- [x] O usuário pode mutar o microfone diretamente pelo menu da bandeja.
- [x] O usuário pode perguntar por voz pelo status de bateria, CPU, RAM e disco do PC e receber diagnósticos instantâneos.
- [x] O usuário pode ajustar volume e mídia do Windows por voz ou pelo painel Web HUD móvel.
- [x] Documentações criadas em `docs/system_tray_and_telemetry.md` e `docs/fase_6.md`.
