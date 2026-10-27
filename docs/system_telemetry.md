# Módulo de Telemetria de Hardware do Windows — ATON

Este documento detalha o módulo de **Telemetria de Hardware e Diagnóstico** do assistente Aton, permitindo monitorar recursos vitais do computador por comando de voz.

---

## 1. Objetivo

Fornecer diagnósticos em tempo real sobre a saúde e uso de recursos da máquina física no Windows (uso de processador CPU, memória RAM, capacidade e espaço livre em disco SSD/HD, e estado de bateria/energia), com respostas formatadas especificamente para síntese por voz.

---

## 2. Componentes e Estrutura

| Arquivo | Responsabilidade |
| :--- | :--- |
| `src/tools/system_telemetry.py` | Coleta métricas de hardware via biblioteca nativa `psutil` e formata a narrativa conversacional. |
| `src/tools/__init__.py` | Registro da ferramenta `get_system_telemetry` em `ALL_ATON_TOOLS`. |
| `tests/test_system_telemetry.py` | Bateria de testes unitários com mocks de sensores e cálculos de métricas. |

---

## 3. Ferramentas Integradas

### 3.1. `get_system_telemetry`
- **Descrição:** Consulta o status e métricas de diagnóstico de hardware da máquina local.
- **Parâmetros:**
  - `metric` (string, opcional, padrão: `'all'`): Métrica específica a consultar:
    - `'all'`: Diagnóstico completo de CPU, RAM, Disco e Bateria.
    - `'cpu'` ou `'processador'`: Porcentagem de uso e núcleos lógicos.
    - `'memory'`, `'ram'` ou `'memoria'`: Memória utilizada, disponível e total.
    - `'disk'`, `'disco'` ou `'armazenamento'`: Espaço livre e percentual de uso no drive `C:`.
    - `'battery'` ou `'bateria'`: Nível percentual, status de carregamento e tempo restante estimado.
- **Exemplo Falado:**
  - *"Aton, como está o uso da minha memória RAM?"*
  - *"Aton, quanto espaço livre ainda tenho no disco?"*
  - *"Aton, verifique a saúde da bateria."*
  - *"Aton, faça um diagnóstico geral do meu sistema."*

---

## 4. Retorno Estruturado

O módulo retorna tanto um payload estruturado para integração quanto um texto natural para fala direta do Aton:
```json
{
  "status": "success",
  "message": "A bateria está em 85% (carregando). O processador está operando com 18% de uso em 16 núcleos. A memória RAM está em 42% de uso (13.4 GB livres de 31.9 GB). O disco principal tem 240.5 GB livres de 950.0 GB.",
  "data": {
    "battery": {"percent": 85.0, "power_plugged": true},
    "cpu": {"percent": 18.0, "cores": 16},
    "memory": {"used_percent": 42.0, "free_gb": 13.4, "total_gb": 31.9},
    "disk": {"free_gb": 240.5, "total_gb": 950.0, "used_percent": 74.6}
  }
}
```

---

## 5. Como Testar

Execute a suíte de testes de telemetria via terminal:
```powershell
.\.venv\Scripts\pytest.exe tests/test_system_telemetry.py -v
```
