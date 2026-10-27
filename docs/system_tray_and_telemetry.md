# Documentação: Sistema & Residente Windows (Bandeja, Telemetria & Áudio do PC)

## 1. Visão Geral do Módulo
O módulo **Sistema & Residente Windows** confere ao **Aton** a capacidade de operar continuamente em segundo plano na barra de tarefas do Windows, fornecendo:
1. **Ícone Dinâmico na Bandeja do Sistema (System Tray):** Feedback visual do estado do assistente (Dormindo, Ouvindo, Falando, Silenciado) e menu de contexto rápido.
2. **Telemetria e Diagnóstico de Hardware em Tempo Real:** Leitura de métricas como percentual de bateria e tempo restante, utilização de CPU, consumo de memória RAM e espaço livre em disco rígido.
3. **Controle de Volume Mestre e Mídia do Windows:** Controle do volume dos alto-falantes (0 a 100%), ativação de mudo e comandos universais de reprodução multimídia (Play/Pause, Próxima Faixa, Faixa Anterior e Parar).

---

## 2. Como Funciona a Arquitetura

### A. Ícone Residente na Bandeja (`src/integrations/system_tray.py`)
- **Geração de Ícone Dinâmico em Memória:**
  - Gera ícones RGBA 64x64 com monograma estilizado "A" através da biblioteca `Pillow` (`PIL.ImageDraw`).
  - Paleta de cores por estado:
    - ⚪ **Dormindo (`sleeping`):** Cinza ardósia `(100, 116, 139)`.
    - 🟢 **Ouvindo (`listening`):** Verde esmeralda `(16, 185, 129)`.
    - 🔵 **Falando (`speaking`):** Azul cibernético `(14, 165, 233)`.
    - 🔴 **Silenciado (`muted`):** Vermelho carmesim `(239, 68, 68)`.
- **Thread Dedicado e Não-Bloqueante:**
  - O loop do `pystray.Icon` roda em uma thread paralela *daemon*, não interferindo no loop de eventos assíncrono do assistente (`asyncio`).
- **Menu de Contexto (Botão Direito):**
  - **Status do Aton:** Exibe o estado e tooltip atual.
  - **Mutar / Desmutar Microfone:** Interrompe a captura do microfone localmente com feedback visual.
  - **Abrir Painel Móvel (HUD):** Abre a interface Web PWA no navegador padrão.
  - **Resumo do Dia (Briefing):** Aciona a geração do relatório executivo matinal.
  - **Sair do Aton:** Encerra o assistente e desliga todos os subsistemas de áudio e conexões.

### B. Telemetria de Hardware (`src/tools/system_telemetry.py`)
- Utiliza a biblioteca local de alta performance `psutil`.
- Suporta comandos detalhados ou agregados:
  - `metric="all"`: Retorna o diagnóstico completo da máquina em uma única narrativa falada.
  - `metric="battery"`: Percentual de carga, indicador de carregamento e tempo estimado de autonomia.
  - `metric="cpu"`: Percentual instantâneo de uso do processador e contagem de núcleos lógicos.
  - `metric="memory"`: Percentual de RAM, gigabytes usados, livres e totais.
  - `metric="disk"`: Espaço total, ocupado e livre na partição do sistema `C:`.

### C. Controle de Áudio e Mídia do Sistema (`src/tools/system_audio.py`)
- **Volume Mestre (`set_system_volume`):**
  - Utiliza `pycaw` (`AudioUtilities.GetSpeakers()`) para manipular diretamente a interface nativa de áudio do Windows (`IAudioEndpointVolume`).
  - Ajusta o volume em porcentagem exata (0 a 100%) ou ativa/desativa o modo mudo.
- **Mídia Universal (`control_system_media`):**
  - Emite eventos de teclado virtual no Windows via `ctypes.windll.user32.keybd_event`.
  - Códigos de tecla virtual:
    - `0xB3`: `VK_MEDIA_PLAY_PAUSE` (Play / Pause universal)
    - `0xB0`: `VK_MEDIA_NEXT_TRACK` (Avançar música)
    - `0xB1`: `VK_MEDIA_PREV_TRACK` (Retornar música)
    - `0xB2`: `VK_MEDIA_STOP` (Parar reprodução)
  - Compatível com Spotify Desktop, reprodutores nativos do Windows, YouTube no Chrome/Edge e players de streaming.

---

## 3. Ferramentas Disponíveis (*Tool Calling* para Gemini Live)

### A. `get_system_telemetry`
- **Descrição:** Obtém informações de diagnóstico e telemetria do PC do usuário em tempo real.
- **Parâmetros:**
  - `metric` *(string, opcional)*: `'all'`, `'battery'`, `'cpu'`, `'memory'` ou `'disk'`.
- **Exemplo de Retorno:**
```json
{
  "status": "success",
  "message": "Status do sistema: A bateria está em 44% (na bateria, com autonomia estimada de 2 horas e 54 minutos); Uso do processador em 12.5% com 12 núcleos lógicos; Memória RAM em 68.2% (10.9 GB usados de 16.0 GB, restando 5.1 GB livres); Disco C: 41.0 GB livres de um total de 476.2 GB (91.4% ocupado).",
  "metric": "all",
  "data": { ... }
}
```

### B. `set_system_volume`
- **Descrição:** Ajusta o volume de som mestre do computador Windows (0 a 100%) ou coloca/remove o som do modo mudo.
- **Parâmetros:**
  - `level` *(integer, opcional)*: Nível de volume desejado de 0 a 100.
  - `mute` *(boolean, opcional)*: `true` para mutar ou `false` para desmutar.
- **Exemplo de Retorno:**
```json
{
  "status": "success",
  "message": "Volume mestre do Windows ajustado para 50%.",
  "volume_percent": 50,
  "is_muted": false
}
```

### C. `control_system_media`
- **Descrição:** Controla a reprodução multimídia no Windows (Play/Pause, avançar música, voltar música ou parar).
- **Parâmetros:**
  - `action` *(string, obrigatório)*: `'play_pause'`, `'next'`, `'previous'` ou `'stop'`.
- **Exemplo de Retorno:**
```json
{
  "status": "success",
  "message": "Com certeza, senhor. Reprodução alternada (Play/Pause).",
  "action": "play_pause"
}
```

---

## 4. Integração no Painel HUD Móvel & Carro

Os botões de acesso rápido foram adicionados à interface móvel do [src/integrations/mobile_gateway.py](file:///c:/xampp/htdocs/amr/src/integrations/mobile_gateway.py):
- **📊 Status do PC:** Aciona a telemetria com um toque.
- **🔊 Volume PC 50%:** Define rapidamente o som do computador para nível moderado.
- **⏯️ Play / Pause:** Alterna a música ou vídeo em reprodução no PC.
- **⏭️ Próxima Faixa:** Pula de música sem tirar as mãos do volante.

---

## 5. Como Testar Automatizadamente

Execute a suíte de testes do módulo:
```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_system_telemetry.py tests/test_system_audio.py tests/test_system_tray.py -v
```

Casos cobertos:
- Leitura agregada e individual de telemetria de hardware (`battery`, `cpu`, `memory`, `disk`).
- Ajuste de volume mestre e controle de mudo com mock de `pycaw`.
- Emulação de teclas multimídia via `_send_media_key`.
- Geração dinâmica de ícones RGBA 64x64 em todos os estados de assistente.
- Menu de contexto, mutação pelo menu da bandeja e ciclo de vida de início/parada do thread da bandeja.
- Roteamento pelo despachante unificado `dispatch_tool` e presença em `ALL_ATON_TOOLS` (31 ferramentas ativas).
