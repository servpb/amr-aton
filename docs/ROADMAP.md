# ROADMAP.md - Roteiro de Desenvolvimento do Aton

Este documento define as fases de evolução do assistente **Aton**, os objetivos de cada etapa, as tecnologias utilizadas e os critérios de aceitação ("Critérios de Pronto").

---

## 🎯 Visão Geral das Fases

```
[Fase 0: Fundação & Cérebro de Voz]
             │
             ▼
[Fase 1: Controle do Windows & Softwares Locais]
             │
             ▼
[Fase 2: Automação Residencial & Dispositivos Locais]
             │
             ▼
[Fase 3: Presença Móvel & Carro (Android + GPS)]
             │
             ▼
[Fase 4: Google Workspace (Agenda, Gmail, Tarefas)]
             │
             ▼
[Fase 5: Memória Semântica de Longo Prazo]
             │
             ▼
[Fase 6: Sistema & Residente Windows]
```

---

## Fase 0: Fundação & Cérebro Local (Voz em Tempo Real)
**Meta:** Ter o Aton ouvindo pelo microfone, ativado pela palavra-chave "Aton" (ou atalho de teclado), conversando em tempo real com voz natural via Gemini Live e respondendo pelos alto-falantes do PC.

- [x] Estrutura inicial do projeto com `pyproject.toml`, `.env.example`, `.gitignore` e `run.bat`.
- [x] Módulo de áudio (`src/audio/`): Captura de microfone com baixa latência e saída de áudio com `sounddevice`.
- [x] Detecção de palavra-chave local (*Wake Word*) para "Aton" (usando biblioteca offline ultraleve para consumo 0 de API).
- [x] Conexão com a API do **Gemini Live** via SDK oficial `google-genai` com voz em português do Brasil e personalidade prestativa/respeitosa.
- [x] Modo conversacional contínuo com detecção de voz e suporte a interrupções de fala.
- **Critério de Pronto (Concluído ✅):** Chamar *"Aton"*, o assistente responder por voz *"Sim, senhor?"*, manter um diálogo curto de perguntas e respostas por áudio, e ele voltar a dormir após alguns segundos de silêncio.

---

## Fase 1: Controle do Sistema Operacional & Softwares Locais
**Meta:** Permitir que o Aton execute comandos no Windows, abra softwares (editores de vídeo/imagem, navegadores), manipule janelas e navegue na web.

- [x] Arquitetura assíncrona de 2 camadas: a voz responde confirmando enquanto uma tarefa em background executa a ação.
- [x] Ferramenta de controle de processos do Windows (abrir, fechar, listar aplicativos via Tool Calling do Gemini Live). Documentado em [docs/windows_apps.md](file:///c:/xampp/htdocs/amr/docs/windows_apps.md).
- [x] Integração para navegação web e pesquisa (Google, YouTube, URLs com Playwright e suporte nativo). Documentado em [docs/web_browser.md](file:///c:/xampp/htdocs/amr/docs/web_browser.md).
- [ ] Esqueleto de integração para softwares de edição/criação instalados no PC.
- [ ] Portão de confirmação para ações destrutivas (ex: fechar programas sem salvar, apagar arquivos).
- **Critério de Pronto (Concluído ✅):** Dizer *"Aton, abra o Bloco de Notas"* ou *"Aton, pesquise no YouTube sobre [tema]"* e a ação ocorrer no Windows com confirmação falada instantânea.

---

## Fase 2: Automação Residencial & Dispositivos na Rede Local
**Meta:** Capacitar o Aton a controlar aparelhos da casa conectados ao mesmo Wi-Fi (Smart TV, iluminação, tomadas inteligentes e celular).

- [x] Descoberta e controle de Smart TVs na rede local (Samsung Tizen, LG webOS, Android TV via WoL e protocolo universal DIAL). Documentado em [docs/smart_tv.md](file:///c:/xampp/htdocs/amr/docs/smart_tv.md).
- [x] Controle de lâmpadas inteligentes e tomadas Wi-Fi compatíveis com protocolos locais (Tuya, Sonoff, Yeelight, Shelly, Philips Hue). Documentado em [docs/smart_lights.md](file:///c:/xampp/htdocs/amr/docs/smart_lights.md).
- [x] Ferramenta para localização do celular Android na mesma rede (disparo de alarme sonoro de alto volume). Documentado em [docs/phone_finder.md](file:///c:/xampp/htdocs/amr/docs/phone_finder.md).
- **Critério de Pronto (Concluído ✅):** Dizer *"Aton, coloque a TV no mudo, apague a luz do quarto e onde está meu celular?"* e todos os comandos responderem simultaneamente por áudio e rede.

---

## Fase 3: Presença Móvel & Carro (Android + GPS em Viagem)
**Meta:** Levar o Aton para fora de casa (no celular e no carro via Bluetooth/Android Auto), com capacidade de traçar rotas e monitorar o trajeto.

- [x] Conexão remota segura via **Tailscale** entre o celular e o computador de casa (sem abrir portas nem custos de servidor). Documentado em [docs/tailscale_and_mobile_gateway.md](file:///c:/xampp/htdocs/amr/docs/tailscale_and_mobile_gateway.md).
- [x] Cliente móvel leve para Android (Painel Web HUD PWA para carro com Push-to-Talk, atalhos rápidos e API REST). Documentado em [docs/tailscale_and_mobile_gateway.md](file:///c:/xampp/htdocs/amr/docs/tailscale_and_mobile_gateway.md).
- [x] Ferramenta de navegação com **Google Maps**: disparo de rotas via *Android Intents* (`google.navigation:q=...`), trânsito e pontos de interesse (postos de combustível, restaurantes, farmácias). Documentado em [docs/google_maps.md](file:///c:/xampp/htdocs/amr/docs/google_maps.md).
- **Critério de Pronto (Concluído ✅):** Dizer *"Aton, trace uma rota para [destino] evitando pedágios"* ou *"Aton, encontre o posto de gasolina mais próximo"* e a rota abrir pronta no mapa com confirmação falada instantânea, e acessar o Aton pelo celular remotamente em trânsito.

---

## Fase 4: Integração Google Workspace (Produtividade)
**Meta:** Integrar o Aton ao ecossistema de produtividade pessoal do Google.

- [x] Leitura e criação de eventos no **Google Agenda (Google Calendar)**. Documentado em [docs/google_calendar.md](file:///c:/xampp/htdocs/amr/docs/google_calendar.md).
- [x] Leitura e resumo de e-mails importantes no **Gmail** (modo somente leitura por segurança). Documentado em [docs/gmail.md](file:///c:/xampp/htdocs/amr/docs/gmail.md).
- [x] Gestão de tarefas e lembretes no **Google Tasks**. Documentado em [docs/google_tasks.md](file:///c:/xampp/htdocs/amr/docs/google_tasks.md).
- **Critério de Pronto (Concluído ✅):** Perguntar *"Aton, quais são os meus compromissos de hoje?"*, *"Aton, tenho algum e-mail importante?"* ou *"Aton, marque a tarefa de compras como feita"* e o assistente gerenciar agenda, e-mails e tarefas por voz com confirmações instantâneas.

---

## Fase 5: Memória Semântica de Longo Prazo
**Meta:** Permitir que o Aton lembre de preferências, projetos passados, rotinas e forneça resumos diários.

- [x] Banco de dados relacional leve persistente com SQLite (`src/core/memory.py`). Documentado em [docs/fase_5.md](file:///c:/xampp/htdocs/amr/docs/fase_5.md).
- [x] Armazenamento e consulta semântica de fatos, preferências do usuário e regras (`remember_fact`, `recall_memory`, `forget_memory`). Documentado em [docs/fase_5.md](file:///c:/xampp/htdocs/amr/docs/fase_5.md).
- [x] Rotina de resumo executivo matinal (`get_daily_briefing`), agregando Google Agenda, Google Tasks, Gmail e preferências. Documentado em [docs/fase_5.md](file:///c:/xampp/htdocs/amr/docs/fase_5.md).
- **Critério de Pronto (Concluído ✅):** Dizer *"Aton, lembre-se de que eu prefiro exportar vídeos sempre em 4K 60fps"* e, em qualquer sessão futura, o Aton consultar e aplicar essa informação autonomamente, além de gerar o briefing matinal completo.
 
---

## Fase 6: Sistema & Residente Windows (Bandeja, Telemetria & Áudio do PC)
**Meta:** Transformar o Aton em um assistente de segundo plano discreto no Windows com ícone na bandeja, leitura de diagnósticos de hardware e controle de volume e multimídia por voz.

- [x] Ícone residente e dinâmico na bandeja do Windows (*System Tray*) com menu de contexto e mutação de microfone (`src/integrations/system_tray.py`). Documentado em [docs/system_tray_and_telemetry.md](file:///c:/xampp/htdocs/amr/docs/system_tray_and_telemetry.md) e [docs/fase_6.md](file:///c:/xampp/htdocs/amr/docs/fase_6.md).
- [x] Telemetria e diagnóstico de hardware em tempo real: bateria, CPU, RAM e disco (`src/tools/system_telemetry.py`). Documentado em [docs/system_tray_and_telemetry.md](file:///c:/xampp/htdocs/amr/docs/system_tray_and_telemetry.md).
- [x] Controle de volume mestre e multimídia universal do Windows (`src/tools/system_audio.py`). Documentado em [docs/system_tray_and_telemetry.md](file:///c:/xampp/htdocs/amr/docs/system_tray_and_telemetry.md).
- [x] Integração no despachante geral `dispatch_tool` e `ALL_ATON_TOOLS` (31 ferramentas ativas).
- [x] Novos atalhos e roteamento de linguagem natural no Painel HUD Móvel (`src/integrations/mobile_gateway.py`).
- **Critério de Pronto (Concluído ✅):** O Aton opera minimizado na bandeja com ícone de status dinâmico; o usuário pode mutar o microfone pelo menu da bandeja, perguntar *"Aton, como está o PC?"* ou *"Aton, diminua o volume do PC para 30%"* e tudo responder com confirmação falada e execução instantânea.
