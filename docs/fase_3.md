# Documentação: Fase 3 - Presença Móvel & Carro (Android + GPS em Viagem)

## 1. Visão Geral e Objetivos
A **Fase 3** permitiu que o **Aton** saísse de dentro de casa e acompanhasse o usuário em viagens, no carro e em movimento, combinando navegação curva a curva sem custos de API e acesso remoto seguro ponto a ponto via VPN privada Mesh.

---

## 2. Módulos e Ferramentas Desenvolvidas

### A. Navegação, Rotas e GPS com Google Maps (`src/tools/google_maps.py`)
- **Objetivo:** Disparar rotas no Google Maps e consultar postos de combustível, trânsito e pontos de interesse.
- **Técnica de Custo Zero:** Uso de *Android Intents* nativos (`google.navigation:q=...`), que abrem diretamente a navegação guiada curva a curva no aplicativo do Google Maps sem consumir créditos da Maps Platform API.
- **Ferramentas (*Tool Calling* para Gemini Live):**
  - `navigate_to(destination, mode, avoid)`: calcula e lança navegação curva a curva com opção de desvio de pedágios ou rodovias.
  - `find_places_nearby(place_type, location)`: localiza postos de gasolina, farmácias, restaurantes ou hospitais próximos.
  - `estimate_traffic_route(destination, origin)`: consulta fluxo e mapa de trânsito em tempo real.
- **Documentado em:** [docs/google_maps.md](file:///c:/xampp/htdocs/amr/docs/google_maps.md).

### B. Mobile Gateway & Acesso Remoto Seguro com Tailscale (`src/integrations/mobile_gateway.py`)
- **Objetivo:** Servidor assíncrono ultraleve HTTP/JSON rodando em segundo plano no PC Windows (porta 8443).
- **Recursos Principais:**
  - **Interface Web Mobile HUD (PWA):** Painel responsivo em tema escuro (Glassmorphism) com botão central de Push-to-Talk via Web Speech API e botões de atalho rápido para uso no carro ou celular.
  - **Endpoints REST:** `/api/status` e `/api/command` para acionamento remoto por voz ou via Tasker/MacroDroid.
  - **Tailscale Mesh VPN:** Conexão remota criptografada WireGuard entre o smartphone e o PC de casa sem abrir portas no roteador (*port forwarding*) nem gastar com servidores VPS.
- **Documentado em:** [docs/tailscale_and_mobile_gateway.md](file:///c:/xampp/htdocs/amr/docs/tailscale_and_mobile_gateway.md).

---

## 3. Critérios de Pronto Atingidos (100% Concluído ✅)
- Dizer *"Aton, trace uma rota para [destino] evitando pedágios"* ou *"Aton, encontre o posto de gasolina mais próximo"* e a rota abrir pronta no mapa.
- Acessar o Aton pelo celular de qualquer lugar do mundo com latência baixa via Tailscale.
