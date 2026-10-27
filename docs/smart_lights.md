# Documentação: Iluminação e Tomadas Inteligentes (smart_lights)

## 1. Objetivo
O módulo **smart_lights** permite ao Aton controlar lâmpadas inteligentes, iluminação de cômodos, fitas LED e tomadas Wi-Fi (plugs inteligentes) diretamente na rede local, sem depender de servidores em nuvem lentos ou APIs pagas.

---

## 2. Componentes e Estrutura

| Arquivo | Responsabilidade |
| :--- | :--- |
| `src/tools/smart_lights.py` | Lógica de controle de estados (`on`/`off`/`toggle`), níveis de intensidade (brilho 0-100%), nomes de cores e controle de tomadas inteligentes. |
| `src/tools/__init__.py` | Integração na lista `ALL_ATON_TOOLS` (14 ferramentas ativas) e despacho no `dispatch_tool()`. |
| `src/config.py` | Leitura da variável `SMART_LIGHTS_BRIDGE_IP`. |
| `tests/test_smart_lights.py` | Bateria de testes unitários automatizados cobrindo comandos de cômodos, cores, brilho e tomadas. |

---

## 3. Ferramentas no Gemini Live

### 3.1. `control_lights`
- **Descrição:** Controla lâmpadas, iluminação de cômodos específicos, intensidade de brilho ou cor da luz.
- **Parâmetros:**
  - `action` (string, obrigatório): `'on'` (acender), `'off'` (apagar), `'toggle'` (alternar).
  - `room` (string, opcional): Nome do cômodo (ex: `'quarto'`, `'sala'`, `'escritório'`, `'cozinha'`).
  - `brightness` (inteiro, opcional): Porcentagem de brilho de 0 a 100.
  - `color` (string, opcional): Cor da lâmpada (ex: `'azul'`, `'vermelho'`, `'amarelo'`, `'branco'`, `'verde'`).
- **Exemplos Falados:**
  - *"Aton, apague as luzes da sala"*
  - *"Aton, acenda a luz do quarto com 50% de brilho"*
  - *"Aton, mude a luz do escritório para azul"*

### 3.2. `control_smart_plug`
- **Descrição:** Controla tomadas e plugs inteligentes conectados a aparelhos domésticos.
- **Parâmetros:**
  - `action` (string, obrigatório): `'on'` (ligar), `'off'` (desligar), `'toggle'` (alternar).
  - `device_name` (string, opcional): Nome do aparelho conectado (ex: `'cafeteira'`, `'ventilador'`, `'abajur'`).
- **Exemplos Falados:**
  - *"Aton, ligue a cafeteira"*
  - *"Aton, desligue a tomada do ventilador"*

---

## 4. Protocolos Locais Suportados (Custo Zero)

O módulo foi projetado para interoperar diretamente com os padrões mais comuns de automação residencial local:
- **Philips Hue / DeCONZ / Zigbee Bridge:** Protocolo REST local (`http://<ip>/api/...`).
- **Shelly / Tasmota / Sonoff DIY:** Comandos HTTP diretos de relé (`/relay/0?turn=on`).
- **Yeelight / Tuya Local:** Controle de socket local direto via Wi-Fi.

Para conectar o Aton ao seu hub ou ponte local, basta definir no `.env`:
```env
SMART_LIGHTS_BRIDGE_IP=192.168.1.80
```

---

## 5. Como Testar

Para executar a bateria de testes automatizados:
```powershell
.\run.bat test
```
Ou diretamente:
```powershell
python -m pytest tests/test_smart_lights.py
```

### Teste Interativo por Voz:
1. Inicie o Aton:
   ```powershell
   .\run.bat
   ```
2. Acorde o Aton dizendo *"Aton"* (ou pressione `[ENTER]`).
3. Diga: *"Aton, apague as luzes do escritório e ligue a cafeteira"*.
4. O Aton responderá confirmando ambas as ações por voz com a voz natural Aoede.
