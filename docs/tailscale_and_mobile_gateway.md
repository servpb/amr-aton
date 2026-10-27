# Documentação: Mobile Gateway & Acesso Remoto Seguro com Tailscale

## 1. Visão Geral
O módulo **Mobile Gateway** (`src/integrations/mobile_gateway.py`) implementa a camada de presença móvel e automação em movimento do assistente **Aton** (Fase 3 do Roadmap). 

Ele provê um servidor assíncrono ultraleve HTTP/JSON rodando no computador Windows hospedeiro que serve simultaneamente:
1. Uma interface web mobile responsiva (Progressive Web App / HUD) otimizada para uso em smartphones no carro e no dia a dia.
2. Uma API REST rápida para execução remota de ferramentas (`/api/command` e `/api/status`), compatível com aplicativos Android de automação (MacroDroid, Tasker) e atalhos por voz.
3. Conexão criptografada ponto a ponto através de rede **Tailscale Mesh VPN**, dispensando redirecionamento de portas (*port forwarding*), IP público fixo ou custos de servidores VPS.

---

## 2. Como Funciona a Arquitetura

```
+-------------------------------------------------------------+
|                     SMARTPHONE / CARRO                      |
|                                                             |
|  [HUD Mobile PWA]           [Tasker / MacroDroid]           |
|  • Botão Push-to-Talk       • Webhook de rota GPS           |
|  • Atalhos rápidos carro    • Automação de ligar/desligar   |
+------------------------------+------------------------------+
                               |
                   Rede Criptografada Ponto a Ponto
                       (Tailscale WireGuard VPN)
                               |
+------------------------------v------------------------------+
|                   COMPUTADOR WINDOWS (Aton)                  |
|                                                             |
|  MobileGatewayServer (porta 8443)                           |
|  ├── GET  /mobile       -> Interface Web HUD                |
|  ├── GET  /api/status   -> Status e ferramentas ativas      |
|  └── POST /api/command  -> Despacho para ALL_ATON_TOOLS      |
|                                                             |
|  Assíncrono: não bloqueia o microfone ou o Gemini Live      |
+-------------------------------------------------------------+
```

---

## 3. Configurações e Variáveis de Ambiente (`.env`)

| Variável | Padrão | Descrição |
|---|---|---|
| `GATEWAY_ENABLED` | `true` | Ativa ou desativa o servidor do gateway móvel |
| `GATEWAY_HOST` | `0.0.0.0` | Endereço de escuta (todas as interfaces de rede) |
| `GATEWAY_PORT` | `8443` | Porta TCP do servidor móvel |
| `GATEWAY_API_TOKEN` | `""` | Token secreto opcional para autenticação Bearer ou via query `?token=` |

---

## 4. Endpoints da API

### A. Painel Web Mobile HUD
- **Rota:** `GET /` ou `GET /mobile`
- **Retorno:** Interface HTML5 moderna e escura (Glassmorphism), com botão central de Push-to-Talk (Web Speech API) e botões rápidos:
  - 🚗 *Traçar Rota p/ Casa* (`navigate_to`)
  - ⛽ *Posto Próximo* (`find_places_nearby`)
  - 📺 *TV no Mudo* (`control_tv_volume`)
  - 💡 *Apagar Luzes* (`control_lights`)
  - 📱 *Localizar Celular* (`find_phone`)
  - 🎵 *Música na Estrada* (`search_youtube`)

### B. Status do Assistente
- **Rota:** `GET /api/status`
- **Exemplo de Resposta:**
```json
{
  "status": "online",
  "assistant_name": "Aton",
  "version": "0.1.0",
  "state": "conversing",
  "tools_count": 17
}
```

### C. Execução de Comandos
- **Rota:** `POST /api/command`
- **Opção 1 - Invocação Direta de Ferramenta:**
```json
{
  "tool_name": "navigate_to",
  "tool_args": {
    "destination": "Aeroporto de Guarulhos"
  }
}
```
- **Opção 2 - Transcrição de Voz / Texto Natural:**
```json
{
  "command": "mutar a tv"
}
```
O servidor aplica heurísticas locais e aciona o módulo correspondente (`control_tv_volume`, `control_lights`, `find_phone`, `navigate_to` ou `web_search`).

---

## 5. Configuração da Rede Remota com Tailscale (Custo Zero)

O Tailscale permite conectar o smartphone Android e o PC Windows em uma VPN privada segura sem abrir portas no roteador:

1. **No PC Windows:**
   - Instale o cliente gratuito do [Tailscale](https://tailscale.com/download/windows).
   - Faça login com sua conta Google.
   - Anote o endereço IP do PC na rede Tailscale (exemplo: `100.85.120.45`).
2. **No Smartphone Android:**
   - Baixe o app **Tailscale** na Google Play Store e faça login com a mesma conta Google.
   - Ative a chave de conexão.
3. **No Navegador do Smartphone:**
   - Acesse: `http://100.85.120.45:8443`
   - O painel do Aton abrirá instantaneamente em qualquer lugar do mundo (no carro via 4G/5G ou em redes externas).
   - No Chrome/Android, selecione **"Adicionar à tela inicial"** para instalar o Aton como um aplicativo nativo (PWA).

---

## 6. Como Testar Automatizadamente

Execute a suíte de testes do Mobile Gateway:
```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_mobile_gateway.py -v
```

Casos cobertos:
- Inicialização e desligamento assíncrono do servidor.
- Verificação de autorização com tokens Bearer e por query string.
- Leitura do endpoint `/api/status`.
- Execução de ferramentas via `/api/command`.
- Interpretação de texto por linguagem natural.
- Renderização do HTML do HUD.
- Tratamento de acessos não autorizados (401) e rotas inexistentes (404).
