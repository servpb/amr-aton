"""Central module registry, introspection, and voice explanation engine for Aton.

Provides accurate, grounded knowledge about Aton's active functional modules,
registered tools, spoken usage examples, verified limitations, and operational status.
Crucially cross-references live registered tools in ALL_ATON_TOOLS without duplicating
manual descriptions or exposing secret keys / credentials.
"""

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from src.config import settings
from src.core.fire_tv_discovery import (
    load_confirmed_fire_tv_state,
    mask_serial,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class ModuleDefinition:
    """Represents a coherent functional module grouping registered tools."""

    def __init__(
        self,
        slug: str,
        name: str,
        area: str,
        area_name: str,
        description: str,
        aliases: List[str],
        tool_names: List[str],
        voice_examples: List[str],
        limitations: List[str],
        status_evaluator: Optional[Callable[[], Tuple[str, str, Optional[Dict[str, Any]]]]] = None,
    ):
        self.slug = slug
        self.name = name
        self.area = area
        self.area_name = area_name
        self.description = description
        self.aliases = [a.lower().strip() for a in aliases]
        self.expected_tool_names = tool_names
        self.voice_examples = voice_examples
        self.limitations = limitations
        self._status_evaluator = status_evaluator

    def evaluate_status(self, registered_tools: Set[str]) -> Tuple[str, str, Optional[Dict[str, Any]]]:
        """Determine module status based on registered tools and local configuration."""
        active_tools = [t for t in self.expected_tool_names if t in registered_tools]
        if not active_tools:
            return "indisponivel", "Nenhuma ferramenta deste módulo está registrada no sistema.", None

        if self._status_evaluator:
            try:
                return self._status_evaluator()
            except Exception as exc:
                logger.debug(f"Error evaluating status for module {self.slug}: {exc}")
                return "estado_desconhecido", f"Não foi possível avaliar o estado: {exc}", None

        return "disponivel", "Módulo operacional com ferramentas locais registradas.", None


def _check_fire_tv_status() -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Check Fire TV module status without external network calls."""
    adb_path = settings.fire_tv_adb_path.strip()
    if not adb_path or not Path(adb_path).is_file():
        return "indisponivel", "Executável adb.exe não configurado ou arquivo ausente.", None

    state = load_confirmed_fire_tv_state()
    confirmed_ip = state.get("confirmed_ip", "").strip()
    confirmed_at = state.get("confirmed_at")
    model = state.get("model", "AFTSS")
    serial = state.get("serial", "")

    has_valid_verification = bool(confirmed_ip and serial and confirmed_at)

    if has_valid_verification:
        time_str = ""
        try:
            dt = datetime.fromtimestamp(confirmed_at, tz=timezone.utc)
            time_str = dt.strftime("%d/%m/%Y às %H:%M UTC")
        except Exception:
            time_str = str(confirmed_at)

        return (
            "configurado",
            "O módulo do Fire Stick está configurado e a identidade foi conferida na última conexão. Posso verificar se ele está disponível agora.",
            {
                "ip": confirmed_ip,
                "modelo": model,
                "serial": mask_serial(serial),
                "data_confirmacao": time_str,
                "verificacao_anterior": True,
                "conectividade_atual": "nao_verificada_nesta_consulta",
                "nota": "Os identificadores esperados foram conferidos na última conexão. A presença ativa no momento requer comando ou verificação ao vivo sob solicitação.",
            },
        )

    configured_ip = confirmed_ip or settings.fire_tv_ip.strip()
    if configured_ip:
        return (
            "configurado",
            "O módulo do Fire Stick está configurado e ainda precisa de verificação. Posso verificar se ele está disponível agora.",
            {
                "ip": configured_ip,
                "verificacao_anterior": False,
                "conectividade_atual": "nao_verificada_nesta_consulta",
                "nota": "Endereço configurado, mas os identificadores de hardware ainda não foram conferidos.",
            },
        )

    return "requer_configuracao", "Requer configuração do IP inicial ou descoberta na rede.", None


def _check_youtube_status() -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Check YouTube module status locally."""
    channels_index = PROJECT_ROOT / "tokens" / "youtube_channels_index.json"
    credentials_file = PROJECT_ROOT / "credentials.json"

    if channels_index.is_file():
        try:
            with open(channels_index, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and data.get("channels"):
                    count = len(data["channels"])
                    return (
                        "disponivel",
                        f"{count} canal(is) autenticado(s) e prontos para consulta.",
                        {"canais_conectados": count},
                    )
        except Exception:
            pass

    if credentials_file.is_file():
        return "requer_configuracao", "Credenciais Google presentes, mas requer autenticação do canal (run.bat youtube-auth).", None

    return "requer_configuracao", "Requer arquivo credentials.json do Google Cloud para autenticação.", None


def _check_gmail_status() -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Check Gmail module status locally."""
    accounts_index = PROJECT_ROOT / "tokens" / "accounts_index.json"
    legacy_token = PROJECT_ROOT / "token.json"
    credentials_file = PROJECT_ROOT / "credentials.json"

    if accounts_index.is_file():
        try:
            with open(accounts_index, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and data.get("accounts"):
                    count = len(data["accounts"])
                    return (
                        "disponivel",
                        f"{count} conta(s) Gmail conectada(s) em modo somente leitura.",
                        {"contas_conectadas": count},
                    )
        except Exception:
            pass

    if legacy_token.is_file():
        return "disponivel", "Conta Gmail conectada via token de acesso.", None

    if credentials_file.is_file():
        return "requer_configuracao", "Credenciais Google presentes, mas requer autenticação de conta (run.bat gmail-auth).", None

    return "requer_configuracao", "Requer arquivo credentials.json do Google Cloud.", None


def _check_calendar_status() -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Check Google Calendar module status."""
    token_file = PROJECT_ROOT / "tokens" / "calendar_token.json"
    legacy_token = PROJECT_ROOT / "token.json"
    if token_file.is_file() or legacy_token.is_file():
        return "disponivel", "Google Calendar conectado com permissão de agenda.", None
    if (PROJECT_ROOT / "credentials.json").is_file():
        return "requer_configuracao", "Requer autenticação de acesso à agenda Google.", None
    return "requer_configuracao", "Requer arquivo credentials.json para agenda.", None


def _check_tasks_status() -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Check Google Tasks module status."""
    token_file = PROJECT_ROOT / "tokens" / "tasks_token.json"
    legacy_token = PROJECT_ROOT / "token.json"
    if token_file.is_file() or legacy_token.is_file():
        return "disponivel", "Google Tasks conectado com permissão de tarefas.", None
    if (PROJECT_ROOT / "credentials.json").is_file():
        return "requer_configuracao", "Requer autenticação de acesso às tarefas Google.", None
    return "requer_configuracao", "Requer arquivo credentials.json para tarefas.", None


def _check_phone_finder_status() -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Check Phone Finder module status."""
    if settings.phone_finder_webhook_url.strip():
        return "disponivel", "Webhook de localização de celular configurado.", None
    return "requer_configuracao", "Configure PHONE_FINDER_WEBHOOK_URL no .env com URL do MacroDroid ou Tasker.", None


def _check_smart_lights_status() -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Check Smart Lights module status."""
    if settings.smart_lights_ips.strip() or settings.philips_hue_bridge_ip.strip():
        return "disponivel", "Endereços IP dos dispositivos de iluminação configurados.", None
    return "requer_configuracao", "Configure SMART_LIGHTS_IPS ou PHILIPS_HUE_BRIDGE_IP no .env.", None


def _check_smart_tv_status() -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Check Smart TV module status."""
    return "indisponivel", "Controle direto de volume e energia da TV física não disponível nesta versão.", None


def _check_screen_perception_status() -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Check Screen Perception module status."""
    if settings.gemini_api_key.strip():
        return "disponivel", "Percepção de tela pronta com Gemini Multimodal.", None
    return "requer_configuracao", "Requer GEMINI_API_KEY no .env para análise de imagens de tela.", None


def _check_second_brain_status() -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Check Second Brain module status."""
    if settings.supabase_url.strip() and settings.supabase_key.strip():
        return "disponivel", "Segundo Cérebro conectado ao Supabase com busca híbrida pgvector e fallback SQLite local.", None
    return "disponivel", "Segundo Cérebro operando via banco de dados local SQLite (amr_memory.db).", None


def _build_module_catalog() -> List[ModuleDefinition]:
    """Build canonical list of system modules with stable identifiers."""
    return [
        ModuleDefinition(
            slug="fire_tv",
            name="Controle do Fire TV Stick",
            area="casa_smart_tv",
            area_name="Casa Inteligente e Televisão",
            description="Controle por voz do Amazon Fire TV Stick via rede local Wi-Fi, permitindo abrir aplicativos, navegar e pesquisar ou reproduzir vídeos no YouTube.",
            aliases=["fire tv", "fire stick", "firetv", "stick", "tv amazon", "aftss", "firetv stick"],
            tool_names=[
                "launch_fire_tv_app",
                "control_fire_tv",
                "get_fire_tv_status",
                "search_fire_tv_youtube",
                "play_fire_tv_youtube",
            ],
            voice_examples=[
                "Abra o YouTube no Fire Stick",
                "Pause o Fire Stick",
                "Pesquise Roberto Carlos no YouTube do Fire Stick",
                "Toque Como É Grande o Meu Amor Por Você no Fire Stick",
            ],
            limitations=[
                "Não altera o volume nem a energia física da televisão.",
                "Pedidos de música sem especificar o título perguntam qual deseja antes de tocar.",
            ],
            status_evaluator=_check_fire_tv_status,
        ),
        ModuleDefinition(
            slug="windows_apps",
            name="Aplicativos e Janelas do Windows",
            area="sistema_windows",
            area_name="Sistema e Windows",
            description="Abertura de programas do PC, fechamento inteligente em 3 camadas e listagem de aplicativos em execução.",
            aliases=["aplicativos", "janelas", "programas", "windows apps", "software", "programas do pc"],
            tool_names=["open_application", "close_application", "list_running_applications"],
            voice_examples=[
                "Abra o Bloco de Notas no computador",
                "Feche o Chrome",
                "Quais aplicativos estão abertos no computador?",
            ],
            limitations=["Abre apenas programas instalados ou registrados no Windows."],
            status_evaluator=lambda: ("disponivel", "Ferramentas do Windows operacionais localmente.", None),
        ),
        ModuleDefinition(
            slug="web_browser",
            name="Navegação Web e Pesquisa",
            area="sistema_windows",
            area_name="Sistema e Windows",
            description="Pesquisas na internet e abertura de páginas web no computador via navegador padrão ou Playwright.",
            aliases=["navegador", "browser", "internet", "web", "pesquisa web", "google web"],
            tool_names=["web_search", "search_youtube", "open_webpage"],
            voice_examples=[
                "Pesquise notícias de tecnologia no computador",
                "Abra o site do Google no navegador",
            ],
            limitations=["Abre os resultados no navegador do PC; não resolve captchas complexos."],
            status_evaluator=lambda: ("disponivel", "Navegação web operacional.", None),
        ),
        ModuleDefinition(
            slug="desktop_automation",
            name="Automação de Digitação e Documentos",
            area="sistema_windows",
            area_name="Sistema e Windows",
            description="Digitação de textos na janela ativa com suporte a acentos, envio de atalhos de teclado e criação de documentos Word e Excel.",
            aliases=["digitacao", "digitar", "office", "word", "excel", "documentos", "teclado", "atalhos"],
            tool_names=[
                "type_text_in_active_window",
                "create_and_open_document",
                "send_keyboard_shortcut",
                "focus_application_window",
            ],
            voice_examples=[
                "Digite este texto na janela ativa",
                "Crie uma planilha de despesas no Excel",
                "Envie o atalho Ctrl+S no computador",
            ],
            limitations=["A janela de destino precisa estar aberta e receber foco antes da digitação."],
            status_evaluator=lambda: ("disponivel", "Automação de teclado e documentos Word/Excel operacional.", None),
        ),
        ModuleDefinition(
            slug="system_audio",
            name="Volume e Multimídia do Windows",
            area="sistema_windows",
            area_name="Sistema e Windows",
            description="Ajuste do volume mestre do computador de 0 a 100% e controle de mídia do PC (play, pause, mudo e faixas).",
            aliases=["volume do pc", "som do windows", "audio", "volume", "midia do computador", "som"],
            tool_names=["set_system_volume", "control_system_media"],
            voice_examples=[
                "Coloque o volume do computador em 50%",
                "Mutar o áudio do computador",
                "Pause a música no computador",
            ],
            limitations=["Controla somente o som do computador; não altera o volume da televisão."],
            status_evaluator=lambda: ("disponivel", "Controle de volume do Windows operacional via pycaw.", None),
        ),
        ModuleDefinition(
            slug="system_telemetry",
            name="Telemetria e Diagnóstico de Hardware",
            area="sistema_windows",
            area_name="Sistema e Windows",
            description="Diagnóstico em tempo real de uso da CPU, memória RAM, armazenamento livre em disco e nível de bateria.",
            aliases=["hardware", "telemetria", "cpu", "memoria ram", "desempenho", "bateria", "disco"],
            tool_names=["get_system_telemetry"],
            voice_examples=[
                "Como está o uso de memória e CPU do computador?",
                "Quanto espaço livre tenho no disco rígido?",
            ],
            limitations=["Leitura diagnóstica local."],
            status_evaluator=lambda: ("disponivel", "Diagnóstico de hardware operacional via psutil.", None),
        ),
        ModuleDefinition(
            slug="screen_perception",
            name="Percepção Visual e Compreensão de Tela",
            area="visao_interacao",
            area_name="Visão Computacional e Tela",
            description="Análise visual do monitor do computador com visão computacional multimodal, leitura de conteúdos e cliques baseados em tela.",
            aliases=["visao", "tela", "olhar a tela", "print", "clicar", "preencher tela", "percepcao"],
            tool_names=[
                "descrever_tela",
                "ler_conteudo_tela",
                "localizar_e_clicar_elemento",
                "preencher_campo_na_tela",
                "rolar_tela",
            ],
            voice_examples=[
                "O que você está vendo na minha tela?",
                "Leia o texto da mensagem de erro na tela",
                "Clique no botão azul Salvar na tela",
            ],
            limitations=["Opera no monitor principal; elementos visuais muito pequenos podem requerer confirmação."],
            status_evaluator=_check_screen_perception_status,
        ),
        ModuleDefinition(
            slug="youtube",
            name="Canais e Vídeos do YouTube",
            area="google_workspace",
            area_name="Google Workspace e Produtividade",
            description="Gestão dos canais do criador no YouTube (como Alta Restauração), estatísticas de público, comentários e metadados de vídeos.",
            aliases=["youtube canal", "canal alta restauracao", "videos do youtube", "youtube studio", "comentarios youtube"],
            tool_names=[
                "list_youtube_channels",
                "get_youtube_channel_stats",
                "list_youtube_videos",
                "get_youtube_video_details",
                "list_youtube_comments",
                "reply_to_youtube_comment",
                "update_youtube_video_metadata",
                "upload_youtube_video",
                "delete_youtube_video",
                "authenticate_youtube",
                "check_youtube_connection",
                "remove_youtube_account",
            ],
            voice_examples=[
                "Quantos inscritos o canal Alta Restauração tem?",
                "Liste os últimos vídeos publicados no canal",
                "Responda ao último comentário do vídeo",
            ],
            limitations=["Publicação e exclusão exigem confirmação verbal; consome cotas da Google Data API v3."],
            status_evaluator=_check_youtube_status,
        ),
        ModuleDefinition(
            slug="gmail",
            name="Gmail (Somente Leitura)",
            area="google_workspace",
            area_name="Google Workspace e Produtividade",
            description="Consulta de e-mails não lidos e leitura de mensagens das contas Google autorizadas com total segurança.",
            aliases=["gmail", "emails", "correio", "caixa de entrada", "mensagens do gmail"],
            tool_names=[
                "list_unread_emails",
                "get_email_content",
                "authenticate_gmail",
                "check_gmail_connection",
                "remove_gmail_account",
            ],
            voice_examples=[
                "Quais são meus e-mails não lidos?",
                "Leia o último e-mail recebido",
            ],
            limitations=["Operação estritamente em modo de leitura; não envia nem exclui mensagens."],
            status_evaluator=_check_gmail_status,
        ),
        ModuleDefinition(
            slug="google_calendar",
            name="Google Agenda (Calendar)",
            area="google_workspace",
            area_name="Google Workspace e Produtividade",
            description="Consulta e agendamento de eventos e compromissos na agenda Google com parser natural de datas em português.",
            aliases=["agenda", "google calendar", "compromissos", "eventos", "calendario"],
            tool_names=["get_calendar_events", "create_calendar_event"],
            voice_examples=[
                "O que tenho na agenda para hoje?",
                "Marque uma reunião amanhã às 15 horas com cliente",
            ],
            limitations=["Requer autorização de conta Google Calendar."],
            status_evaluator=_check_calendar_status,
        ),
        ModuleDefinition(
            slug="google_tasks",
            name="Google Tarefas (Tasks)",
            area="google_workspace",
            area_name="Google Workspace e Produtividade",
            description="Criação, consulta e conclusão de afazeres na lista de tarefas do Google por comandos de voz.",
            aliases=["tarefas", "google tasks", "afazeres", "to do", "lembretes"],
            tool_names=["list_tasks", "create_task", "complete_task"],
            voice_examples=[
                "Quais são minhas tarefas pendentes?",
                "Adicione comprar peças do carro na lista de tarefas",
                "Conclua a tarefa de emitir relatório",
            ],
            limitations=["Requer autorização de conta Google Tasks."],
            status_evaluator=_check_tasks_status,
        ),
        ModuleDefinition(
            slug="google_maps",
            name="Rotas e GPS (Google Maps)",
            area="google_workspace",
            area_name="Google Workspace e Produtividade",
            description="Cálculo de tempo de trajeto com trânsito em tempo real, localização de postos e disparo de navegação passo a passo via Android Intents a custo zero.",
            aliases=["maps", "google maps", "gps", "rotas", "transito", "postos"],
            tool_names=["navigate_to", "find_places_nearby", "estimate_traffic_route"],
            voice_examples=[
                "Como está o trânsito até o centro?",
                "Encontre postos de combustível perto de mim",
                "Iniciar rota até a oficina",
            ],
            limitations=["A navegação física assistida é iniciada no smartphone Android conectado."],
            status_evaluator=lambda: ("disponivel", "Módulo de rotas pronto com Intents a custo zero.", None),
        ),
        ModuleDefinition(
            slug="phone_finder",
            name="Localizador de Celular",
            area="casa_smart_tv",
            area_name="Casa Inteligente e Televisão",
            description="Dispara alarme sonoro em volume máximo no smartphone Android conectado na rede Wi-Fi.",
            aliases=["localizar celular", "onde esta meu celular", "cade meu celular", "alarme celular"],
            tool_names=["find_phone"],
            voice_examples=[
                "Aton, onde está meu celular?",
                "Toque o alarme do meu telefone",
            ],
            limitations=["O smartphone precisa estar conectado à rede Wi-Fi com o webhook ativado."],
            status_evaluator=_check_phone_finder_status,
        ),
        ModuleDefinition(
            slug="smart_lights",
            name="Iluminação e Tomadas Inteligentes",
            area="casa_smart_tv",
            area_name="Casa Inteligente e Televisão",
            description="Controle de lâmpadas e plugs inteligentes locais via Wi-Fi (Philips Hue, Shelly, Sonoff, Tuya).",
            aliases=["luzes", "lampadas", "tomadas", "iot", "casa inteligente", "iluminacao"],
            tool_names=["control_lights", "control_smart_plug"],
            voice_examples=[
                "Ligue a luz do escritório",
                "Desligue a tomada da impressora",
            ],
            limitations=["Requer dispositivos configurados na rede local."],
            status_evaluator=_check_smart_lights_status,
        ),
        ModuleDefinition(
            slug="smart_tv",
            name="Smart TV Convencional",
            area="casa_smart_tv",
            area_name="Casa Inteligente e Televisão",
            description="Controle de Smart TVs convencionais. Funções de volume e energia informam honestamente sua indisponibilidade sem falsas confirmações.",
            aliases=["smart tv", "televisao", "tv da sala", "controle da tv"],
            tool_names=["control_tv_volume", "control_tv_power"],
            voice_examples=[
                "Aumente o volume da TV",
                "Desligue a televisão",
            ],
            limitations=["Controle direto de volume e energia física da Smart TV não disponível nesta versão."],
            status_evaluator=_check_smart_tv_status,
        ),
        ModuleDefinition(
            slug="network_devices",
            name="Rede e Dispositivos Autorizados",
            area="sistema_windows",
            area_name="Sistema e Windows",
            description="Descoberta de dispositivos via mDNS ZeroConf, pareamento seguro por PIN e controle de aparelhos autorizados no Mobile Gateway.",
            aliases=["rede", "dispositivos de rede", "pareamento", "ip local", "mdns"],
            tool_names=["get_network_info", "list_network_devices", "revoke_network_device", "scan_network_devices"],
            voice_examples=[
                "Quais dispositivos estão pareados na rede?",
                "Qual é o IP local do assistente?",
            ],
            limitations=["Varredura restrita à sub-rede local autorizada."],
            status_evaluator=lambda: ("disponivel", "Descoberta de rede mDNS e pareamento de dispositivos ativo.", None),
        ),
        ModuleDefinition(
            slug="second_brain",
            name="Segundo Cérebro e Memória Permanente",
            area="segundo_cerebro_ia",
            area_name="Segundo Cérebro e Memória",
            description="Memória relacional e semântica no Supabase PostgreSQL com pgvector e busca híbrida, com contingência local transparente em SQLite.",
            aliases=["segundo cerebro", "memoria", "lembrancas", "crm", "conhecimento", "autoconhecimento"],
            tool_names=[
                "salvar_memoria",
                "buscar_memoria",
                "perguntar_ao_cerebro",
                "criar_cliente_cerebro",
                "criar_tarefa_cerebro",
                "resumo_geral_cerebro",
                "esquecer_memoria_cerebro",
                "atualizar_memoria_cerebro",
                "consultar_autoconhecimento",
            ],
            voice_examples=[
                "Lembre que o cliente João prefere reuniões às terças",
                "O que você sabe sobre restauração do Siena?",
                "Quais clientes estão cadastrados no cérebro?",
            ],
            limitations=["Busca vetorial completa requer conexão com nuvem; opera offline via SQLite de contingência."],
            status_evaluator=_check_second_brain_status,
        ),
        ModuleDefinition(
            slug="memory",
            name="Memória Local e Briefing Diário",
            area="segundo_cerebro_ia",
            area_name="Segundo Cérebro e Memória",
            description="Banco de memória rápida local em SQLite para fatos cotidianos e resumo executivo matinal integrando agenda, tarefas e e-mails.",
            aliases=["resumo matinal", "briefing", "fatos locais", "memoria rapida"],
            tool_names=["remember_fact", "recall_memory", "forget_memory", "get_daily_briefing"],
            voice_examples=[
                "Qual é o meu briefing diário de hoje?",
                "Lembre que meu café é sem açúcar",
            ],
            limitations=["Armazenamento relacional local no computador."],
            status_evaluator=lambda: ("disponivel", "Memória SQLite e rotina de briefing matinal operacional.", None),
        ),
        ModuleDefinition(
            slug="groq",
            name="Inferência Rápida Groq LPU",
            area="inteligencia",
            area_name="Inteligência & IA",
            description="Processamento de linguagem natural e inferência ultra-rápida via LPU na API Groq oficial.",
            aliases=["groq", "grok", "groc", "lpu", "inferencia rapida"],
            tool_names=["query_groq_llm", "check_groq_connection"],
            voice_examples=[
                "Verifique a conexão com a Groq.",
                "Consulte a Groq sobre inteligência artificial.",
                "O que o módulo Groq faz?",
            ],
            limitations=[
                "Requer conexão com a internet ativa para alcançar a API oficial da Groq.",
                "Respeita os limites de requisições por minuto (RPM) da camada gratuita da Groq.",
            ],
            status_evaluator=lambda: (
                ("pronto", "API Groq configurada e pronta para consultas.", {"modelo": settings.groq_model})
                if settings.groq_api_key
                else ("precisa_configuracao", "Chave GROQ_API_KEY não configurada no .env.", None)
            ),
        ),
        ModuleDefinition(
            slug="nemotron",
            name="Planejamento Avançado NVIDIA Nemotron",
            area="inteligencia",
            area_name="Inteligência & IA",
            description="Decomposição rigorosa e planejamento analítico de tarefas complexas via modelo NVIDIA Nemotron 70B no OpenRouter.",
            aliases=["nemotron", "nvidia", "planejamento", "openrouter", "planejar tarefa"],
            tool_names=["planejar_tarefa_complexa", "consultar_nemotron", "check_nemotron_connection"],
            voice_examples=[
                "Planeje um projeto de automação no Windows.",
                "Verifique a conexão com a Nemotron.",
                "Consulte a Nemotron sobre este desafio.",
            ],
            limitations=[
                "Requer conexão com a internet ativa e chave OPENROUTER_API_KEY no .env.",
                "Focado em planejamento estruturado e raciocínio analítico com dados públicos/fictícios.",
            ],
            status_evaluator=lambda: (
                ("pronto", "OpenRouter e Nemotron configurados.", {"modelo": settings.openrouter_model})
                if settings.openrouter_api_key
                else ("precisa_configuracao", "Chave OPENROUTER_API_KEY não configurada no .env.", None)
            ),
        ),
        ModuleDefinition(
            slug="reminders", name="Timers e lembretes", area="google_workspace",
            area_name="Produtividade", description="Avisos locais persistentes, independentes da conversa.",
            aliases=["timer", "lembretes", "alarmes", "avisos"],
            tool_names=["create_timer", "create_reminder", "list_reminders", "cancel_reminder"],
            voice_examples=["Me avise daqui a um minuto", "Quais são meus lembretes?"],
            limitations=["Requer Aton executando e Windows ativo; avisos vencidos chegam ao retornar.",
                         "Som e notificação local; não envia alertas ao celular."]
        ),
    ]


class ModuleRegistry:
    """Singleton registry and query engine for Aton's functional modules."""

    _instance = None

    def __init__(self):
        self._definitions: List[ModuleDefinition] = _build_module_catalog()

    @classmethod
    def get_instance(cls) -> "ModuleRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_active_tool_names(self) -> Set[str]:
        """Dynamically inspect currently registered tools in ALL_ATON_TOOLS."""
        try:
            from src.tools import ALL_ATON_TOOLS
            return {t.get("name", "") for t in ALL_ATON_TOOLS if "name" in t}
        except Exception as exc:
            logger.warning(f"Could not import ALL_ATON_TOOLS dynamically: {exc}")
            return set()

    def list_modules_overview(self, area_filter: Optional[str] = None) -> Dict[str, Any]:
        """Generate high-level overview of available modules grouped by area."""
        active_tools = self._get_active_tool_names()
        grouped: Dict[str, Dict[str, Any]] = {}

        for mod in self._definitions:
            status, reason, last_ver = mod.evaluate_status(active_tools)
            current_tools = [t for t in mod.expected_tool_names if t in active_tools]

            if not current_tools and status == "indisponivel" and "Nenhuma ferramenta" in reason:
                continue

            area_key = mod.area
            if area_filter and area_filter.lower().strip() not in (area_key, mod.area_name.lower()):
                continue

            if area_key not in grouped:
                grouped[area_key] = {
                    "area_id": area_key,
                    "area_nome": mod.area_name,
                    "modulos": [],
                }

            grouped[area_key]["modulos"].append({
                "id": mod.slug,
                "nome": mod.name,
                "descricao_curta": mod.description,
                "status": status,
                "total_ferramentas": len(current_tools),
            })

        # Voice-friendly summary
        areas_list = list(grouped.values())
        total_modules = sum(len(a["modulos"]) for a in areas_list)

        voice_lines = [
            f"Eu possuo {total_modules} módulos organizados em {len(areas_list)} áreas principais:"
        ]
        for a in areas_list:
            mod_names = ", ".join(m["nome"] for m in a["modulos"][:3])
            voice_lines.append(f"• {a['area_nome']}: inclui {mod_names}.")

        voice_lines.append("Deseja que eu detalhe o Fire Stick, o YouTube, o Windows ou algum outro módulo?")

        return {
            "status": "success",
            "total_modulos": total_modules,
            "total_areas": len(areas_list),
            "areas": areas_list,
            "mensagem_voz": "\n".join(voice_lines),
        }

    def detail_module(self, query: str) -> Dict[str, Any]:
        """Provide detailed explanation, examples, limitations, and status for a module."""
        norm_query = query.lower().strip()
        if not norm_query:
            return {
                "status": "error",
                "message": "Por favor, informe o nome ou apelido do módulo que deseja consultar.",
            }

        # Match exact slug or alias with ambiguity detection
        exact_matches: List[ModuleDefinition] = []
        partial_matches: List[ModuleDefinition] = []

        for mod in self._definitions:
            if mod.slug == norm_query or norm_query in mod.aliases or mod.name.lower() == norm_query:
                exact_matches.append(mod)
            elif any(alias in norm_query or norm_query in alias for alias in mod.aliases):
                partial_matches.append(mod)

        matched: Optional[ModuleDefinition] = None
        if len(exact_matches) == 1:
            matched = exact_matches[0]
        elif len(exact_matches) > 1:
            names = [str(c.name) for c in exact_matches]
            return {
                "status": "ambiguous",
                "message": f"Encontrei mais de um módulo correspondente ({', '.join(names)}). Qual deles você gostaria de detalhar?",
                "opcoes": [str(c.slug) for c in exact_matches],
            }
        elif len(partial_matches) == 1:
            matched = partial_matches[0]
        elif len(partial_matches) > 1:
            names = [str(c.name) for c in partial_matches]
            return {
                "status": "ambiguous",
                "message": f"Encontrei mais de um módulo correspondente ({', '.join(names)}). Qual deles você gostaria de detalhar?",
                "opcoes": [str(c.slug) for c in partial_matches],
            }

        if not matched:
            return {
                "status": "not_found",
                "message": f"Não encontrei um módulo chamado '{query}'. Peça 'quais módulos você tem' para ver as opções disponíveis.",
            }

        active_tools = self._get_active_tool_names()
        current_tools = [t for t in matched.expected_tool_names if t in active_tools]
        status, reason, last_verified = matched.evaluate_status(active_tools)

        # Build natural spoken message
        voice_text = (
            f"O módulo {matched.name} tem como objetivo: {matched.description} "
            f"Ele conta com {len(current_tools)} ferramentas registradas e o estado atual é {status} ({reason}). "
            f"Você pode usar comandos como: '{matched.voice_examples[0]}' ou '{matched.voice_examples[1]}'. "
        )
        if matched.limitations:
            voice_text += f"Como limitação importante: {matched.limitations[0]}"

        return {
            "status": "success",
            "id": matched.slug,
            "nome": matched.name,
            "area": matched.area_name,
            "descricao": matched.description,
            "ferramentas_registradas": current_tools,
            "exemplos_comandos_voz": matched.voice_examples,
            "limitacoes": matched.limitations,
            "estado": status,
            "motivo_estado": reason,
            "ultima_verificacao": last_verified,
            "mensagem_voz": voice_text,
        }

    def list_unconfigured_or_pending(self) -> Dict[str, Any]:
        """List modules that require configuration or setup."""
        active_tools = self._get_active_tool_names()
        pending = []

        for mod in self._definitions:
            status, reason, _ = mod.evaluate_status(active_tools)
            if status in ("requer_configuracao", "indisponivel"):
                pending.append({
                    "id": mod.slug,
                    "nome": mod.name,
                    "status": status,
                    "motivo": reason,
                })

        if not pending:
            return {
                "status": "success",
                "total_pendentes": 0,
                "mensagem_voz": "Todos os módulos disponíveis estão devidamente configurados no momento.",
                "modulos_pendentes": [],
            }

        lines = [f"Atualmente, {len(pending)} recurso(s) requerem configuração ou estão indisponíveis:"]
        for p in pending:
            lines.append(f"• {p['nome']}: {p['motivo']}")

        return {
            "status": "success",
            "total_pendentes": len(pending),
            "mensagem_voz": "\n".join(lines),
            "modulos_pendentes": pending,
        }


def get_module_registry() -> ModuleRegistry:
    """Return singleton ModuleRegistry instance."""
    return ModuleRegistry.get_instance()
