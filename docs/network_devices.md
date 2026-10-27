# Documentação: ATON em Rede e Dispositivos Autorizados (network_devices)

## 1. Visão Geral
O módulo **network_devices** evolui o ATON para operar como um **Hub/Serviço anfitrião na rede local**, permitindo que múltiplos dispositivos autorizados — como **smartphones (Android e iOS), Smart TVs (Samsung Tizen, LG webOS, Android TV) e outros computadores** — se conectem de forma segura para enviar comandos, ouvir respostas e operar o assistente.

A arquitetura adota o princípio de **Zero Confiança por Padrão (*Zero-Trust Local*)**:
- Estar na mesma rede Wi-Fi ou ter um endereço IP visível **NÃO concede autorização** para conectar ou controlar o computador.
- Qualquer conexão exige **confirmação mútua e pareamento seguro por código PIN descartável de 6 dígitos** com validade de 5 minutos.
- Permissões são **granulares por dispositivo** (`commands`, `audio`, `screen`, `files`, `control`).

---

## 2. Arquitetura e Componentes

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        ATON HOST (Windows PC)                          │
├──────────────────────────┬─────────────────────────────────────────────┤
│ NetworkDiscovery         │ • Enumera interfaces locais (Wi-Fi, Tailscale, Eth)│
│ (src/core/network_discovery.py) │ • Anúncio mDNS/DNS-SD (_aton._tcp.local.)     │
│                          │ • Sonda controlada de sub-rede (/api/status)│
├──────────────────────────┼─────────────────────────────────────────────┤
│ DeviceManager            │ • Tabela SQLite 'aton_paired_devices'       │
│ (src/core/device_manager.py) │ • Geração de PIN de uso único (6 dígitos) │
│                          │ • Tokens de 256 bits com hash SHA-256       │
│                          │ • Validação de permissões granulares        │
├──────────────────────────┼─────────────────────────────────────────────┤
│ MobileGatewayServer      │ • Endpoints REST (/api/pair, /api/network)  │
│ (src/integrations/mobile_gateway.py) │ • Web HUD SPA responsiva para Celular e TV│
├──────────────────────────┼─────────────────────────────────────────────┤
│ Network Tools (53 ferramentas)│ • get_network_info, list_network_devices    │
│ (src/tools/network_tools.py) │ • revoke_network_device, scan_network_devices│
└──────────────────────────┴─────────────────────────────────────────────┘
                               ▲
        mDNS / HTTP            │ Token Bearer / PIN
                               ▼
   ┌──────────────────────┬──────────────────────┬──────────────────────┐
   │     SMARTPHONES      │       SMART TVS      │  OUTROS COMPUTADORES │
   │ (Android Auto & iOS) │(Tizen / webOS / TV)  │  (Web Desktop / CLI) │
   │ • Web Speech PTT     │ • Layout TV D-Pad    │ • Console & Dashboard│
   │ • Ações Rápidas      │ • Botões de Mídia    │ • Pareamento com PIN │
   └──────────────────────┴──────────────────────┴──────────────────────┘
```

---

## 3. Matriz de Permissões Granulares

Cada dispositivo pareado possui uma lista explícita de permissões concedidas. Ações fora das permissões concedidas são bloqueadas com código HTTP `403 Forbidden`:

| Permissão | Escopo e Ações Permitidas | Ferramentas Associadas |
| :--- | :--- | :--- |
| `commands` | Envio de comandos gerais por voz/texto, agenda, clima, tarefas, resumo matinal. | `get_daily_briefing`, `list_tasks`, `get_calendar_events`, `search_youtube`, etc. |
| `audio` | Entrada e saída de áudio via Web Speech ou streaming. | Canal de voz do Web HUD. |
| `screen` | Captura da tela do computador anfitrião e inspeção visual multimodal. | `descrever_tela`, `ler_conteudo_tela`, `localizar_e_clicar_elemento`, etc. |
| `files` | Criação, leitura e abertura de documentos de texto e planilhas. | `create_and_open_document`. |
| `control` | Controle do computador: digitação remota, atalhos de teclado, fechamento de programas e volume mestre. | `type_text_in_active_window`, `send_keyboard_shortcut`, `close_application`, `set_system_volume`. |

---

## 4. Fluxo de Pareamento Seguro (Passo a Passo)

1. **Descoberta do ATON:**
   - O dispositivo abre no navegador a URL do ATON na rede local (ex: `http://192.168.0.9:8443`), descoberta via mDNS (`_aton._tcp.local.`) ou informada pelo usuário.
2. **Solicitação de Pareamento:**
   - Na tela de pareamento, o usuário informa o nome do dispositivo (ex: *"Galaxy S24 de Bruno"*) e clica em **"Solicitar Pareamento"**.
   - O ATON Host gera um código PIN numérico de 6 dígitos (ex: `729415`) válido por 5 minutos e emite um bipe sonoro no computador.
3. **Validação do PIN:**
   - O usuário digita o PIN no dispositivo ou confirma no anfitrião.
   - O anfitrião emite um token de sessão de 256 bits exclusivo (`aton_...`) e armazena o hash criptográfico SHA-256 na tabela `aton_paired_devices`.
4. **Comunicação Autenticada:**
   - O dispositivo salva o token no `localStorage` e envia o cabeçalho `Authorization: Bearer <token>` em todas as requisições subsequentes.
5. **Revogação Instantânea:**
   - O usuário pode revogar o acesso de qualquer dispositivo a qualquer momento com 1 clique no Web HUD ou por comando de voz: *"Aton, desconecte o celular"*.

---

## 5. Endpoints da API de Rede

| Método | Endpoint | Autenticação | Descrição |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/status` | Pública / Opcional | Retorna status de conexão, versão e tipo do host. |
| `GET` | `/api/network/interfaces` | Pública | Retorna as interfaces ativas (Wi-Fi, Ethernet, Tailscale) e IPs locais. |
| `POST` | `/api/pair/request` | Pública | Inicia solicitação de pareamento e gera código PIN temporário. |
| `POST` | `/api/pair/confirm` | Pública | Valida PIN de 6 dígitos e devolve token de autenticação. |
| `GET` | `/api/network/devices` | Dispositivo Pareado | Lista dispositivos pareados e solicitações pendentes. |
| `POST` | `/api/network/scan` | Dispositivo Pareado | Executa busca controlada via mDNS ou sonda de sub-rede. |
| `POST` | `/api/devices/revoke` | Dispositivo Pareado | Invalida o token e revoga o dispositivo indicado. |
| `POST` | `/api/command` | Dispositivo Pareado | Executa ferramentas respeitando a matriz de permissões. |

---

## 6. Dispositivos Remotos e Redes Externas (4G / 5G)

- A descoberta por mDNS/Broadcast opera **estritamente na rede local (Wi-Fi/LAN)**.
- Para conexão segura com o celular em trânsito (4G/5G) ou computadores externos, o ATON utiliza a **VPN Mesh Tailscale**:
  - Comunicação através de IP privado `100.x.y.z` com criptografia ponta a ponta (WireGuard).
  - **Zero portas públicas expostas** no roteador residencial (sem risco de invasão por varredura externa de portas).
  - Custo zero (Tailscale Free Tier).

---

## 7. Ferramentas Integradas do Assistente ATON

O assistente ATON reconhece nativamente por voz e texto as ferramentas:
- `get_network_info`: *"Aton, qual é o seu IP na rede?"*
- `list_network_devices`: *"Aton, quais dispositivos estão conectados?"*
- `revoke_network_device`: *"Aton, desconectar o Galaxy S24"*
- `scan_network_devices`: *"Aton, procurar dispositivos na rede"*

---

## 8. Testes Automatizados

Para executar os testes do módulo de rede e autorização:
```cmd
.\.venv\Scripts\pytest.exe tests/test_network_devices.py
```
*(Resultado: 8/8 testes aprovados cobrindo geração de PIN, validação de token, escopos granulares e bloqueio 403 Forbidden)*.
