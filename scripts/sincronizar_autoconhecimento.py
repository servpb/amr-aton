"""Aton Self-Knowledge Introspection and Synchronization Script.

Dynamically introspects the real codebase, active tools, system modules,
technologies, architecture, limitations, and changelog, then synchronizes
them into Supabase 'aton_autoconhecimento' and 'aton_changelog' tables,
with local JSON cache for offline resilience.
"""

from datetime import datetime, timezone
import json
import logging
import os
import sys
import urllib.parse

# Ensure UTF-8 output on Windows terminal
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure workspace root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from typing import Any, Dict, List, Optional
from src.config import settings
from src.core.second_brain import SecondBrainClient
from src.tools import ALL_ATON_TOOLS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def build_system_facts() -> List[Dict[str, Any]]:
    """Build factual, grounded records derived from active codebase introspection."""
    facts: List[Dict[str, Any]] = []

    # 1. IDENTIDADE
    facts.append({
        "categoria": "identidade",
        "titulo": "Identidade e Propósito do Aton",
        "conteudo": (
            "O Aton é um assistente pessoal inteligente, executivo e operacional de alta performance, "
            "operado prioritariamente por voz bidirecional em tempo real (áudio streaming de baixa latência), "
            "inspirado na arquitetura do J.A.R.V.I.S. Batizado exclusivamente como Aton, ele atua como copiloto "
            "do seu criador na automação do sistema operacional Windows, gestão da agência digital, "
            "projetos do canal Alta Restauração no YouTube e orquestração de um Segundo Cérebro permanente."
        ),
        "resumo": "Assistente pessoal inteligente de voz em tempo real e automação para o criador da agência e do canal Alta Restauração.",
        "tags": ["identidade", "proposito", "aton", "jarvis", "assistente_pessoal"],
        "nivel_acesso": "publico",
    })

    facts.append({
        "categoria": "identidade",
        "titulo": "Criador do Aton",
        "conteudo": (
            "O criador do Aton é um empresário e criador de conteúdo, proprietário de uma agência de marketing "
            "e estratégias digitais, além do canal de YouTube 'Alta Restauração' (com projetos automotivos e de restauração, "
            "incluindo veículos como o Fiat Siena 2006). O Aton foi construído para potencializar a produtividade diária, "
            "atendimento a clientes e controle de tarefas e ideias do criador."
        ),
        "resumo": "Criado pelo empresário, dono de agência digital e fundador do canal Alta Restauração.",
        "tags": ["criador", "agencia_digital", "alta_restauracao", "siena_2006", "perfil"],
        "nivel_acesso": "publico",
    })

    facts.append({
        "categoria": "identidade",
        "titulo": "Data de Criação e Versão Atual",
        "conteudo": (
            "O projeto Aton foi iniciado em Outubro de 2026. A versão atual da base do sistema e "
            "Segundo Cérebro é a 0.8.0, contando com 9 migrações estruturadas e mais de 40 ferramentas "
            "operacionais ativas integradas."
        ),
        "resumo": "Iniciado em Outubro de 2026, versão atual 0.8.0 com 9 migrações.",
        "tags": ["versao", "data_criacao", "historico", "outubro_2026"],
        "nivel_acesso": "publico",
    })

    # 2. TECNOLOGIA
    facts.append({
        "categoria": "tecnologia",
        "titulo": "Stack de Tecnologias e Linguagens",
        "conteudo": (
            "O Aton é construído em Python 3.11+ em ambiente Windows 11 nativo. Utiliza Google Gemini Live API "
            "via WebSockets bidirecionais (com voz natural Aoede em áudio PCM 16kHz e 24kHz), Supabase PostgreSQL 15+ "
            "com extensão pgvector para busca semântica vetorial HNSW 768d e Full-Text Search em português brasileiro, "
            "modelo de embeddings Google gemini-embedding-001 (768 dimensões), Edge Functions TypeScript/Deno, "
            "banco de dados SQLite local resiliente para contingência offline, e bibliotecas especializadas do sistema: "
            "Playwright (automação web), pycaw (áudio Windows), psutil (hardware), pyperclip e win32 (digitação universal), "
            "python-docx e openpyxl (Office nativo)."
        ),
        "resumo": "Python 3.11+, Gemini Live WebSocket (Aoede), Supabase PostgreSQL 15 com pgvector HNSW 768d, Edge Functions e SQLite local.",
        "tags": ["tecnologia", "python", "gemini_live", "aoede", "supabase", "pgvector", "postgresql", "playwright"],
        "nivel_acesso": "publico",
    })

    facts.append({
        "categoria": "tecnologia",
        "titulo": "Voz Aoede e Áudio em Tempo Real",
        "conteudo": (
            "A voz do Aton é a voz nativa feminina 'Aoede' do Google Gemini Live API, transmitida em áudio PCM "
            "de alta fidelidade (16.000 Hz de entrada e 24.000 Hz de saída). O assistente possui supressão acústica "
            "de eco para não cortar a própria voz durante a fala e saudação nativa instantânea com latência zero."
        ),
        "resumo": "Voz nativa Aoede em PCM de alta fidelidade com supressão de eco acústico e latência zero.",
        "tags": ["voz", "aoede", "audio_pcm", "gemini_live", "eco_acustico", "latencia_zero"],
        "nivel_acesso": "publico",
    })

    facts.append({
        "categoria": "tecnologia",
        "titulo": "Segundo Cérebro: Supabase, pgvector e Fallback SQLite",
        "conteudo": (
            "A memória permanente e registros operacionais do Aton residem em nuvem no Supabase PostgreSQL, "
            "utilizando pgvector com índices HNSW e busca híbrida (65% similaridade cosseno de embeddings vetoriais "
            "e 35% relevância de texto completo tsvector em português). Possui 18 tabelas relacionais com RLS rigoroso. "
            "Em caso de desconexão da nuvem ou ausência de rede, o Aton faz fallback automático e transparente "
            "para o banco local SQLite (amr_memory.db), mantendo a integridade da operação."
        ),
        "resumo": "Supabase PostgreSQL com pgvector HNSW e busca híbrida vetorial + FTS, com fallback transparente para SQLite local.",
        "tags": ["segundo_cerebro", "supabase", "pgvector", "busca_hibrida", "sqlite", "fallback"],
        "nivel_acesso": "publico",
    })

    # 3. ARQUITETURA
    facts.append({
        "categoria": "arquitetura",
        "titulo": "Arquitetura em Camadas Desacopladas",
        "conteudo": (
            "O Aton opera sob uma arquitetura de alta performance com três camadas funcionais:\n"
            "1. Camada Rápida (Conversacional/Voz): Conexão WebSocket em tempo real via Gemini Live API, "
            "detecção contínua de voz (VAD), Wake Word local offline ('Aton'/'AMR') e Push-to-Talk global.\n"
            "2. Camada de Trabalho (Worker/Background): Execução assíncrona de ferramentas (Tool Calling) "
            "que permite ao Aton responder imediatamente por voz ('Já estou providenciando, senhor') enquanto executa tarefas "
            "pesadas de automação em segundo plano sem congelar o diálogo.\n"
            "3. Camada de Persistência e Segundo Cérebro: Supabase na nuvem e SQLite local orquestrando perfil, CRM, "
            "projetos, tarefas, agenda e base de conhecimento."
        ),
        "resumo": "Três camadas: Conversacional de baixa latência, Worker assíncrono em segundo plano e Segundo Cérebro persistente.",
        "tags": ["arquitetura", "camadas", "voz_rapida", "worker_assincrono", "tool_calling", "desacoplamento"],
        "nivel_acesso": "publico",
    })

    facts.append({
        "categoria": "arquitetura",
        "titulo": "Distinção entre Aton e Modelo Gemini",
        "conteudo": (
            "O Aton NÃO é apenas o modelo Gemini da Google. O Gemini Live atua como o motor de linguagem e "
            "síntese de voz do Aton. Porém, o Aton é uma entidade completa e personalizada que possui código próprio, "
            "acesso físico ao hardware e softwares do Windows, automação web via Playwright, controle de dispositivos "
            "IoT e Smart TVs na rede local Wi-Fi, integração com Google Workspace e seu próprio banco de dados "
            "relacional Segundo Cérebro."
        ),
        "resumo": "O Aton é o assistente completo com acesso ao Windows, IoT e banco de dados; o Gemini é seu motor de linguagem/voz.",
        "tags": ["distincao", "aton_vs_gemini", "identidade", "capacidades_locais"],
        "nivel_acesso": "publico",
    })

    # 4. CAPACIDADES E FERRAMENTAS INTROSPECTADAS
    tool_count = len(ALL_ATON_TOOLS)
    tool_names = [t.get("name", "") for t in ALL_ATON_TOOLS if "name" in t]
    facts.append({
        "categoria": "capacidade",
        "titulo": "Visão Geral das Ferramentas Operacionais",
        "conteudo": (
            f"O Aton possui atualmente {tool_count} ferramentas operacionais ativas integradas ao Gemini Live. "
            "Essas ferramentas abrangem: controle de processos e janelas do Windows, automação web e pesquisas "
            "com Playwright, controle de Smart TVs e mídias via Wi-Fi, acionamento do alarme sonoro do celular Android, "
            "automação de iluminação e tomadas IoT, rotas e trânsito com Google Maps, compromissos na agenda Google Calendar, "
            "leitura segura de e-mails no Gmail, gerenciamento de afazeres no Google Tasks, telemetria de hardware (CPU/RAM/Disco), "
            "volume e controle multimídia do Windows, digitação universal em janelas ativas, criação e abertura de arquivos "
            "Word (.docx) e Excel (.xlsx), além de consulta e escrita no Segundo Cérebro permanente."
        ),
        "resumo": f"{tool_count} ferramentas ativas: Windows, Web Playwright, Smart TV, Celular, IoT, Maps, Workspace, Sistema e Segundo Cérebro.",
        "tags": ["ferramentas", "capacidades", "tool_calling", "total_ferramentas", str(tool_count)],
        "nivel_acesso": "publico",
    })

    # Extrair ferramentas por grupos funcionais
    groups = {
        "Controle de Janelas e Aplicativos Windows": [
            "open_application", "close_application", "list_running_applications"
        ],
        "Automação Web e YouTube": [
            "web_search", "search_youtube", "open_webpage"
        ],
        "Smart TV e Entretenimento na Rede": [
            "control_tv_volume", "control_tv_media", "control_tv_power", "launch_tv_app", "get_tv_status"
        ],
        "Localizador de Celular Android": [
            "find_phone"
        ],
        "IoT, Iluminação e Tomadas Inteligentes": [
            "control_lights", "control_smart_plug"
        ],
        "Mobilidade, Rotas e GPS Google Maps": [
            "navigate_to", "find_places_nearby", "estimate_traffic_route"
        ],
        "Google Workspace - Calendário, Gmail e Tarefas": [
            "get_calendar_events", "create_calendar_event", "list_unread_emails", "get_email_content",
            "list_tasks", "create_task", "complete_task"
        ],
        "Telemetria de Sistema e Áudio Windows": [
            "get_system_telemetry", "set_system_volume", "control_system_media"
        ],
        "Digitação Universal e Automação Office": [
            "type_text_in_active_window", "create_and_open_document", "send_keyboard_shortcut", "focus_application_window"
        ],
        "Segundo Cérebro, Memória e CRM": [
            "salvar_memoria", "buscar_memoria", "perguntar_ao_cerebro", "criar_cliente_cerebro",
            "criar_tarefa_cerebro", "resumo_geral_cerebro", "esquecer_memoria_cerebro", "atualizar_memoria_cerebro"
        ],
        "Percepção Visual e Interação com a Tela": [
            "descrever_tela", "ler_conteudo_tela", "localizar_e_clicar_elemento", "preencher_campo_na_tela", "rolar_tela"
        ],
    }

    for group_name, names in groups.items():
        matched_tools = [t for t in ALL_ATON_TOOLS if t.get("name") in names]
        desc_list = [f"- {t['name']}: {t.get('description', '')}" for t in matched_tools]
        facts.append({
            "categoria": "capacidade",
            "titulo": f"Capacidades: {group_name}",
            "conteudo": (
                f"Ferramentas ativas de {group_name}:\n" + "\n".join(desc_list)
            ),
            "resumo": f"Módulo de {group_name} com {len(matched_tools)} ferramentas ativas.",
            "tags": ["capacidade", "modulo", group_name.lower().replace(" ", "_")] + names,
            "nivel_acesso": "publico",
        })

    # 5. LIMITAÇÕES REAIS E VERIFICÁVEIS
    facts.append({
        "categoria": "limitacao",
        "titulo": "Limitações Conhecidas do Aton",
        "conteudo": (
            "O Aton opera com total transparência e possui limitações técnicas claras:\n"
            "1. Sem busca semântica vetorial offline: Quando desconectado da internet, o Aton recorre ao SQLite local, "
            "que realiza buscas textuais simples, sem comparação de vetores de alta dimensionalidade.\n"
            "2. Sem voz Aoede offline: A síntese e reconhecimento de voz de baixa latência do Gemini Live exigem conexão à internet ativa.\n"
            "3. Segurança de Segredos: O Aton NUNCA expõe senhas, chaves de API, credenciais ou tokens de banco sob nenhuma hipótese.\n"
            "4. Transações Financeiras: O Aton não possui permissão para realizar pagamentos, transferências ou compras.\n"
            "5. Ações Destrutivas: O Aton sempre solicita autorização prévia verbal antes de excluir permanentemente memórias ou dados."
        ),
        "resumo": "Sem busca vetorial offline, sem voz offline, não expõe credenciais, não faz transações e requer autorização para exclusões.",
        "tags": ["limitacoes", "seguranca", "offline", "transparencia", "regras_estritas"],
        "nivel_acesso": "publico",
    })

    # 6. ROADMAP
    facts.append({
        "categoria": "roadmap",
        "titulo": "Planejamento e Próximos Passos (Roadmap)",
        "conteudo": (
            "O roadmap planejado do Aton inclui:\n"
            "1. Modo Offline Local-First Completo: Fila outbox de sincronização bidirecional assíncrona com o Supabase.\n"
            "2. Conectores Adicionais de IoT: Suporte a mais protocolos de automação predial e residencial sem depender de nuvens externas.\n"
            "3. Automação Avançada de Softwares de Edição: Scripts dedicados para softwares de vídeo e renderização utilizados no canal Alta Restauração."
        ),
        "resumo": "Roadmap: Modo offline com sincronização bidirecional outbox, mais conectores IoT e automação para edição de vídeo.",
        "tags": ["roadmap", "futuro", "modo_offline", "sincronizacao", "iot_avancado"],
        "nivel_acesso": "publico",
    })

    # 7. REGRA DE HONESTIDADE
    facts.append({
        "categoria": "faq",
        "titulo": "Regra de Honestidade Absoluta sobre Autoconhecimento",
        "conteudo": (
            "Quando questionado sobre si mesmo, sua arquitetura, criador, tecnologias, capacidades ou histórico, "
            "o Aton deve consultar exclusivamente sua base de autoconhecimento verificada. Se a informação não estiver "
            "registrada, o Aton deve responder de forma honesta e direta: 'Isso não está registrado no meu autoconhecimento.', "
            "sem especular, inventar ou alucinar respostas."
        ),
        "resumo": "Se uma informação sobre o Aton não estiver registrada, ele responde que não possui o registro sem alucinar.",
        "tags": ["honestidade", "sem_alucinacao", "autoconhecimento", "diretriz_fundamental"],
        "nivel_acesso": "publico",
    })

    return facts


def build_changelog_entries() -> List[Dict[str, Any]]:
    """Build changelog timeline of migrations and major phases."""
    return [
        {
            "versao": "0.1.0",
            "titulo": "Fase 0: Fundação, Motor de Áudio e Gemini Live",
            "descricao": "Arquitetura base, gerenciador de áudio Windows PCM, Wake Word local 'Aton'/'AMR', Push-to-Talk e cliente WebSocket Gemini Live bidirecional.",
            "tipo": "release",
            "referencia": "Fase 0",
        },
        {
            "versao": "0.2.0",
            "titulo": "Fase 1: Controle do Windows e Automação Web",
            "descricao": "Gerenciamento de softwares e processos do Windows, automação web via Playwright e pesquisas no YouTube.",
            "tipo": "release",
            "referencia": "Fase 1",
        },
        {
            "versao": "0.3.0",
            "titulo": "Fase 2: Smart TVs, IoT e Localizador de Celular",
            "descricao": "Controle universal de Smart TVs na rede Wi-Fi, disparo sonoro de alarme no celular Android e controle de iluminação/tomadas inteligentes.",
            "tipo": "release",
            "referencia": "Fase 2",
        },
        {
            "versao": "0.4.0",
            "titulo": "Fase 3: Google Maps, Trânsito e Mobile Gateway",
            "descricao": "Navegação GPS, rotas com trânsito em tempo real, servidor Mobile Gateway assíncrono e pareamento seguro via VPN Tailscale.",
            "tipo": "release",
            "referencia": "Fase 3",
        },
        {
            "versao": "0.5.0",
            "titulo": "Fase 4: Google Workspace (Calendar, Gmail, Tasks)",
            "descricao": "Integração com Google Calendar (parser pt-BR), Gmail somente leitura e Google Tasks com conclusão por linguagem natural.",
            "tipo": "release",
            "referencia": "Fase 4",
        },
        {
            "versao": "0.6.0",
            "titulo": "Fase 5: Memória Semântica SQLite e Resumo Executivo",
            "descricao": "Persistência local relacional em SQLite (amr_memory.db) e rotina matinal de resumo executivo diário.",
            "tipo": "release",
            "referencia": "Fase 5",
        },
        {
            "versao": "0.7.0",
            "titulo": "Fases 6 & 7: Residente Tray, Telemetria, Volume e Digitação Win32",
            "descricao": "Ícone na bandeja do Windows, telemetria de hardware (psutil), controle de volume mestre (pycaw), digitação universal com clipboard e automação Office (.docx / .xlsx).",
            "tipo": "release",
            "referencia": "Fases 6 e 7",
        },
        {
            "versao": "0.8.0",
            "titulo": "Fase 8: Segundo Cérebro Supabase, pgvector e Autoconhecimento",
            "descricao": "18 tabelas relacionais no PostgreSQL com RLS, busca híbrida semântica vetorial HNSW 768d + FTS em português, Edge Functions, Migrations 01 a 09 e Módulo de Autoconhecimento.",
            "tipo": "migration",
            "referencia": "Migration 09",
        },
        {
            "versao": "0.9.0",
            "titulo": "Fase 9: Percepção Visual, Áudio e Interação com a Tela",
            "descricao": "Captura sob demanda da janela ativa e desktop, análise multimodal com Gemini 2.0 Flash Bounding Boxes, mapeamento de coordenadas reais, leitura inteligente de tela e 5 ferramentas de interação.",
            "tipo": "release",
            "referencia": "Fase 9",
        },
    ]


def synchronize(sync_to_supabase: bool = True) -> Dict[str, Any]:
    """Execute introspection and sync facts to Supabase and local cache."""
    facts = build_system_facts()
    changelog = build_changelog_entries()

    logger.info(f"Introspecção concluída: {len(facts)} fatos estruturados e {len(changelog)} entradas de changelog.")

    # 1. Salvar Cache Local
    os.makedirs("data", exist_ok=True)
    cache_path = os.path.abspath(os.path.join("data", "aton_autoconhecimento_cache.json"))
    cache_payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "total_facts": len(facts),
        "facts": facts,
        "changelog": changelog,
    }
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache_payload, f, ensure_ascii=False, indent=2)
    logger.info(f"Cache local salvo com sucesso em: {cache_path}")

    # 2. Sincronizar com Supabase se solicitado e configurado
    client = SecondBrainClient()
    supabase_synced = 0
    changelog_synced = 0

    if sync_to_supabase and client.is_configured:
        logger.info("Verificando conexão com Supabase para sincronização...")
        test_check = client._supabase_request("aton_autoconhecimento?select=id&limit=1", method="GET")

        if test_check is None:
            logger.warning(
                "A tabela 'aton_autoconhecimento' ainda não está acessível no Supabase. "
                "Certifique-se de executar a Migration 09 no SQL Editor do Supabase."
            )
            return {
                "status": "partial_success",
                "message": "Fatos introspectados e cache local salvo. Tabela Supabase aguarda execução da Migration 09.",
                "local_cache": cache_path,
                "facts_count": len(facts),
            }

        logger.info("Gerando embeddings e inserindo fatos no Supabase...")
        for fact in facts:
            text_for_embed = f"{fact['titulo']}: {fact['conteudo']} {' '.join(fact['tags'])}"
            embedding = client.get_embedding(text_for_embed)

            payload = {
                "categoria": fact["categoria"],
                "titulo": fact["titulo"],
                "conteudo": fact["conteudo"],
                "resumo": fact.get("resumo"),
                "tags": fact.get("tags", []),
                "nivel_acesso": fact.get("nivel_acesso", "publico"),
                "fonte": "gerado_automaticamente",
                "versao_sistema": "0.8.0",
                "versao": 1,
                "status": "ativa",
                "ativo": True,
                "embedding": embedding if embedding else None,
                "embedding_pendente": False if embedding else True,
            }

            # Check if exists by title
            encoded_title = urllib.parse.quote(fact["titulo"])
            existing = client._supabase_request(f"aton_autoconhecimento?titulo=eq.{encoded_title}&select=id", method="GET")

            if existing and isinstance(existing, list) and len(existing) > 0:
                record_id = existing[0]["id"]
                client._supabase_request(f"aton_autoconhecimento?id=eq.{record_id}", payload, method="PATCH")
            else:
                client._supabase_request("aton_autoconhecimento", payload, method="POST")

            supabase_synced += 1

        logger.info(f"[OK] {supabase_synced} fatos sincronizados com o Supabase.")

        # Sincronizar Changelog
        for cl in changelog:
            encoded_ref = urllib.parse.quote(cl["referencia"])
            existing_cl = client._supabase_request(f"aton_changelog?referencia=eq.{encoded_ref}&select=id", method="GET")
            if not (existing_cl and isinstance(existing_cl, list) and len(existing_cl) > 0):
                client._supabase_request("aton_changelog", cl, method="POST")
                changelog_synced += 1

        logger.info(f"[OK] {changelog_synced} entradas de changelog registradas.")

    return {
        "status": "success",
        "local_cache": cache_path,
        "facts_count": len(facts),
        "supabase_synced": supabase_synced,
        "changelog_synced": changelog_synced,
    }


if __name__ == "__main__":
    res = synchronize(sync_to_supabase=True)
    print(f"\nResultado da Sincronização: {json.dumps(res, indent=2, ensure_ascii=False)}")
