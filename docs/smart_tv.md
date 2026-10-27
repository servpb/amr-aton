# Documentação: Controle de Smart TV e Dispositivos de Mídia (smart_tv)

## 1. Objetivo
O módulo **smart_tv** inicia a **Fase 2 (Automação Residencial e Dispositivos na Rede Local)** do Aton. Ele permite controlar televisores inteligentes (LG webOS, Samsung Tizen, Android TV, Google TV e Chromecast) conectados ao mesmo Wi-Fi do computador através de comandos de voz naturais.

---

## 2. Componentes e Estrutura

| Arquivo | Responsabilidade |
| :--- | :--- |
| `src/tools/smart_tv.py` | Lógica de envio de Wake-on-LAN (para ligar), controle de volume, reprodução de mídia, lançamento de apps via protocolo universal DIAL (porta 8008) e verificação de status online. |
| `src/tools/__init__.py` | Integração na lista `ALL_ATON_TOOLS` (11 ferramentas ativas) e despacho no `dispatch_tool()`. |
| `src/config.py` | Leitura das variáveis `SMART_TV_IP`, `SMART_TV_BRAND` e `SMART_TV_MAC`. |
| `.env.example` | Documentação das variáveis de ambiente de Smart TV para o usuário. |
| `tests/test_smart_tv.py` | Bateria de testes unitários automatizados cobrindo WoL, rotas de comando e tratamento de status. |

---

## 3. Ferramentas Disponíveis no Gemini Live

### 3.1. `control_tv_volume`
- **Descrição:** Ajusta o volume da Smart TV ou altera o status de mudo.
- **Parâmetros:**
  - `action` (string, obrigatório): `'mute'`, `'unmute'`, `'up'`, `'down'` ou `'set'`.
  - `level` (inteiro, opcional): Nível de volume numérico de 0 a 100 (quando a ação for `'set'`).
- **Exemplo Falado:** *"Aton, coloque a TV no mudo"* ou *"Aton, aumente o volume da TV"*.

### 3.2. `control_tv_media`
- **Descrição:** Controla a reprodução de filmes, séries ou vídeos na tela da TV.
- **Parâmetros:**
  - `action` (string, obrigatório): `'play'`, `'pause'`, `'stop'`, `'next'`, `'previous'`.
- **Exemplo Falado:** *"Aton, pause a TV"* ou *"Aton, dê play na TV"*.

### 3.3. `control_tv_power`
- **Descrição:** Liga ou desliga a Smart TV pela rede local.
- **Parâmetros:**
  - `action` (string, obrigatório): `'on'` (utiliza Wake-on-LAN) ou `'off'`.
- **Exemplo Falado:** *"Aton, ligue a TV"* ou *"Aton, desligue a televisão"*.

### 3.4. `launch_tv_app`
- **Descrição:** Abre aplicativos de streaming na Smart TV via protocolo universal DIAL.
- **Parâmetros:**
  - `app_name` (string, obrigatório): Nome do aplicativo (ex: `'YouTube'`, `'Netflix'`, `'Spotify'`, `'Prime'`).
- **Exemplo Falado:** *"Aton, abra a Netflix na TV"* ou *"Aton, abra o YouTube na televisão"*.

### 3.5. `get_tv_status`
- **Descrição:** Verifica se a Smart TV está online e respondendo na rede local Wi-Fi.
- **Exemplo Falado:** *"Aton, a TV da sala está ligada?"*.

---

## 4. Configuração no `.env`

No seu arquivo `.env`, você pode definir os parâmetros da sua TV:
```env
# Endereço IP da Smart TV no seu Wi-Fi (ex: 192.168.1.50)
SMART_TV_IP=192.168.1.50

# Marca da TV (auto, samsung, lg, android_tv)
SMART_TV_BRAND=auto

# Endereço MAC para ligar a TV pela rede via Wake-on-LAN
SMART_TV_MAC=AA:BB:CC:DD:EE:FF
```

> **Dica:** O endereço IP e o endereço MAC da sua TV podem ser consultados facilmente no menu de **Rede / Conexão** da sua própria Smart TV ou na página de dispositivos conectados do seu roteador Wi-Fi.

---

## 5. Como Testar

Para executar a bateria de testes automatizados:
```powershell
.\run.bat test
```
Ou diretamente:
```powershell
python -m pytest tests/test_smart_tv.py
```

### Teste Interativo por Voz:
1. Inicie o Aton:
   ```powershell
   .\run.bat
   ```
2. Acorde o Aton dizendo *"Aton"* (ou pressione `[ENTER]`).
3. Diga: *"Aton, coloque a TV no mudo"*.
4. O Aton enviará o comando para a sua TV e responderá: *"Smart TV colocada no mudo, senhor."*.
