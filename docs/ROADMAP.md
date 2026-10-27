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
             │
             ▼
[Fase 7: Automação de Digitação & Documentos]
             │
             ▼
[Fase 8: Segundo Cérebro Supabase & pgvector]
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

---

## Fase 7: Automação de Digitação & Documentos (Office, Bloco de Notas e Navegadores)
**Meta:** Capacitar o Aton a digitar textos com acentuação e quebras de linha em qualquer software ativo, criar e abrir arquivos formatados (.docx Word, .xlsx Excel, .txt, .csv) e controlar atalhos de teclado do Windows.

- [x] Injeção de digitação rápida com fidelidade ABNT2/acentuação via `pyperclip` e clipboard (`src/tools/desktop_automation.py`). Documentado em [docs/desktop_automation.md](file:///c:/xampp/htdocs/amr/docs/desktop_automation.md) e [docs/fase_7.md](file:///c:/xampp/htdocs/amr/docs/fase_7.md).
- [x] Geração nativa e abertura de documentos Word (`.docx`) com títulos e parágrafos estruturados (`python-docx`).
- [x] Geração nativa e abertura de planilhas Excel (`.xlsx`) com colunas e dados numéricos/textuais formatados (`openpyxl`).
- [x] Simulação de atalhos universais de teclado (`Ctrl+S`, `Ctrl+A`, `Ctrl+C`, `Ctrl+V`, `Enter`, `Tab`).
- [x] Foco dinâmico de janelas em execução na tela via `pygetwindow`.
- [x] Integração no despachante unificado `dispatch_tool` e `ALL_ATON_TOOLS` (35 ferramentas ativas).
- **Critério de Pronto (Concluído ✅):** Dizer *"Aton, escreva no Bloco de Notas: Reunião às 15 horas"* ou *"Aton, crie uma planilha no Excel com colunas Produto, Quantidade e Preço"* e os softwares serem abertos e preenchidos em tempo real.

---

## Fase 8: Segundo Cérebro Supabase & pgvector (Memória Permanente & CRM)
**Meta:** Prover ao Aton uma memória permanente em nuvem, baseada em Supabase (PostgreSQL), extensão `pgvector` para busca semântica vetorial HNSW (768 dimensões com Gemini text-embedding-004), busca híbrida com Full-Text Search em português e CRM/Projetos integrados.

- [x] 6 migrações SQL com 18 tabelas relacionais em `supabase/migrations/` (perfil criador, clientes, projetos, tarefas, agenda, conhecimento, conversas, memória de longo prazo vetorial, módulos e auditoria). Documentado em [docs/second_brain.md](file:///c:/xampp/htdocs/amr/docs/second_brain.md).
- [x] Função RPC PostgreSQL `buscar_memoria_hibrida` combinando 65% cosseno + 35% Full-Text Search + bônus de importância.
- [x] 100% das tabelas protegidas por Row Level Security (RLS) e triggers automáticos de auditoria imutável.
- [x] Edge Functions em TypeScript/Deno (`brain-api` e `consolidate-memory` com deduplicação por similaridade >= 0.88).
- [x] Cliente nativo Python desacoplado com fallback automático para SQLite local (`src/core/second_brain.py`).
- [x] 6 ferramentas ativas integradas (`salvar_memoria`, `buscar_memoria`, `perguntar_ao_cerebro`, `criar_cliente_cerebro`, `criar_tarefa_cerebro`, `resumo_geral_cerebro`), totalizando 41 ferramentas ativas em `ALL_ATON_TOOLS`.
- [x] Guia prático de configuração passo a passo em [docs/supabase_setup_guide.md](file:///c:/xampp/htdocs/amr/docs/supabase_setup_guide.md).
- [x] Validação em testes com caso real: Unboxing e instalação de multimídia 2DIN no Siena 2006 (Alta Restauração) respondido com data, contexto e 0% de alucinação (`tests/test_second_brain.py`).
- **Critério de Pronto (Concluído ✅):** Dizer *"Aton, o que eu falei sobre edição de vídeo?"* e o assistente recuperar a memória exata do Siena 2006, moldura 2DIN e canal Alta Restauração, com citação de datas e assertividade factual.


