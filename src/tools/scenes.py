"""
Multi-Module Verified Scenes & Custom Voice Routines for Aton (Fase 8 / Frentes 1 e 3).

Implements the 6 mandatory reliability & verification guarantees (Frente 1) plus
the 6 mandatory custom routine security & confirmation guarantees (Etapa 3):
1. Fault-Isolated Independent Step Execution:
   Every step runs in its own isolated execution block with timeout protection.
   A failure in Fire TV, Gmail, Calendar, Tasks, or Windows Audio NEVER aborts
   the remaining steps of the scene.
2. Three-Level Real Verification (`confirmed`, `sent_unverified`, `failed`):
   - `confirmed`: action executed AND state readback/confirmation verified.
   - `sent_unverified`: command sent or device connected, but final state
     could not be verified.
   - `failed`: action could not be sent, timed out, or returned an error.
3. Security Guards & Authorized Catalog Whitelist:
   - Per-step execution timeout (`step_timeout_seconds`, default 8.0s).
   - Anti-duplication lock and cooldown (`SCENE_DEDUP_COOLDOWN_SECONDS = 5.0`).
   - Secret sanitization (`_sanitize_text`).
   - Strict whitelist of allowed custom step types (`ALLOWED_CUSTOM_STEP_TYPES`)
     and allowed application identifiers (`ALLOWED_APP_IDENTIFIERS`). Never
     executes arbitrary OS/shell commands.
4. Application Protection & Sensitive Action Gate:
   - Opening/closing apps is restricted to authorized identifiers (rejecting
     shells like `cmd`, `powershell`, `regedit`, `taskmgr`, or raw paths).
   - `fechar_app_pc` is classified as a sensitive action (`is_sensitive=True`),
     warns explicitly about the risk of losing unsaved documents, and requires
     specific confirmation before execution.
5. Reliable SQLite Persistence & State Snapshot/Restoration:
   - Transactional SQLite persistence (`custom_scenes` and `scene_state_snapshots`
     in `data/reminders.sqlite3`).
   - Unique normalized slugs (`slug TEXT PRIMARY KEY`) and strict protection of
     native scenes (`bom_dia`, `modo_cinema`, `modo_foco`, `boa_noite`, `restaurar`)
     against overwrite or deletion.
   - Timers created by routines are persisted in `ReminderStore` so they survive
     Aton restarts.
   - Pre-scene state snapshots preserve previous Windows volume and proactive DND
     flags without altering permanent quiet hours (`23:00–07:00`).
6. Proposal-Bound Confirmation Manager (`SceneConfirmationManager`):
   - Confirmations ("Sim" / `confirmar_rotina_personalizada`) are bound to the
     specific pending proposal of the current interaction, enforce a 60-second
     TTL, reject duplicate confirmations, and supersede older pending proposals.
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import re
import secrets
import sqlite3
import threading
import time
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path("data/reminders.sqlite3")
DEFAULT_STEP_TIMEOUT_SECONDS = 8.0
SCENE_DEDUP_COOLDOWN_SECONDS = 5.0
PROPOSAL_TTL_SECONDS = 60.0

# Patterns that must never appear in logs or returned messages
_SECRET_PATTERNS = [
    re.compile(r"(Bearer\s+)[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE),
    re.compile(r"AIza[0-9A-Za-z\-_]{20,}"),
    re.compile(r"gsk_[0-9A-Za-z]{20,}"),
    re.compile(r"nvapi-[0-9A-Za-z\-_]{20,}"),
    re.compile(r"sk-[0-9A-Za-z\-_]{20,}"),
    re.compile(r"(api[_-]?key\s*[:=]\s*)['\"]?[A-Za-z0-9\-._~+/]{8,}['\"]?", re.IGNORECASE),
    re.compile(r"(token\s*[:=]\s*)['\"]?[A-Za-z0-9\-._~+/]{8,}['\"]?", re.IGNORECASE),
]


def _sanitize_text(text: Any) -> str:
    """Remove any accidental API keys, tokens, or credentials from logs/messages."""
    raw = str(text or "").strip()
    for pattern in _SECRET_PATTERNS:
        raw = pattern.sub("[CREDENTIAL_REDACTED]", raw)
    return raw


def _slugify_scene_name(raw_name: str) -> str:
    """Normalize a spoken scene name into an ASCII snake_case slug."""
    text = unicodedata.normalize("NFKD", str(raw_name or "").strip().lower())
    ascii_text = "".join(ch for ch in text if not unicodedata.combining(ch))
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_text).strip("_")
    return slug


@dataclass
class SceneStepResult:
    """Outcome of a single isolated step inside a multi-module scene."""

    step_id: str
    description: str
    verification_level: str  # "confirmed" | "sent_unverified" | "failed"
    message: str
    duration_ms: int = 0
    details: Optional[Dict[str, Any]] = None


# Canonical native scenes and voice aliases (Protected against overwrite/deletion)
SCENE_ALIASES: Dict[str, str] = {
    "bom_dia": "bom_dia",
    "bom dia": "bom_dia",
    "iniciar_expediente": "bom_dia",
    "iniciar expediente": "bom_dia",
    "resumo_da_manha": "bom_dia",
    "resumo da manha": "bom_dia",
    "resumo da manhã": "bom_dia",
    "modo_cinema": "modo_cinema",
    "modo cinema": "modo_cinema",
    "cinema": "modo_cinema",
    "filme": "modo_cinema",
    "modo_filme": "modo_cinema",
    "modo_foco": "modo_foco",
    "modo foco": "modo_foco",
    "foco": "modo_foco",
    "concentracao": "modo_foco",
    "concentração": "modo_foco",
    "modo_trabalho": "modo_foco",
    "boa_noite": "boa_noite",
    "boa noite": "boa_noite",
    "encerrar_expediente": "boa_noite",
    "encerrar expediente": "boa_noite",
    "encerrar_dia": "boa_noite",
    "restaurar": "restaurar",
    "restaurar_cena": "restaurar",
    "sair_modo": "restaurar",
    "sair do modo": "restaurar",
    "normal": "restaurar",
}

SCENE_CATALOG: Dict[str, Dict[str, Any]] = {
    "bom_dia": {
        "name": "bom_dia",
        "title": "Rotina Bom Dia / Iniciar Expediente",
        "description": (
            "Consulta compromissos de hoje no Google Agenda, tarefas pendentes no Google Tasks, "
            "e-mails não lidos no Gmail e telemetria/bateria do Windows."
        ),
        "modifies_state": False,
        "is_native": True,
    },
    "modo_cinema": {
        "name": "modo_cinema",
        "title": "Modo Cinema",
        "description": (
            "Salva o estado anterior de volume e avisos, silencia apenas o som dos avisos proativos "
            "(sem alterar o horário de silêncio permanente), reduz o volume do PC para 20% com leitura "
            "de confirmação e abre o YouTube no Fire TV Stick verificando o pacote em primeiro plano."
        ),
        "modifies_state": True,
        "is_native": True,
    },
    "modo_foco": {
        "name": "modo_foco",
        "title": "Modo Foco / Concentração",
        "description": (
            "Salva o estado anterior de volume e avisos, silencia o som dos avisos proativos da agenda, "
            "envia comando para pausar mídia no Windows e cria um timer persistente de foco (padrão: 45 min)."
        ),
        "modifies_state": True,
        "is_native": True,
    },
    "boa_noite": {
        "name": "boa_noite",
        "title": "Rotina Boa Noite / Encerrar Expediente",
        "description": (
            "Salva o estado anterior, silencia o som dos avisos proativos da agenda, envia pausa de mídia "
            "ao Windows e adianta os compromissos de amanhã no Google Agenda."
        ),
        "modifies_state": True,
        "is_native": True,
    },
    "restaurar": {
        "name": "restaurar",
        "title": "Restaurar Configurações Anteriores",
        "description": (
            "Restaura o volume anterior do Windows e o estado anterior do modo Não Perturbe dos avisos "
            "proativos salvos antes do Modo Cinema, Modo Foco, Boa Noite ou de uma rotina personalizada."
        ),
        "modifies_state": False,
        "is_native": True,
    },
}

PROTECTED_NATIVE_SLUGS: set[str] = set(SCENE_CATALOG.keys()) | {
    _slugify_scene_name(k) for k in SCENE_ALIASES.keys()
}

# ---------------------------------------------------------------------------
# Requirement 2 & 3: Strict Action Whitelist & Safe Application Identifiers
# ---------------------------------------------------------------------------

# Only user-level safe application identifiers are permitted in custom scenes.
# Shells, system utilities, and arbitrary paths (cmd, powershell, regedit, taskmgr, etc.) are forbidden.
ALLOWED_APP_IDENTIFIERS: Dict[str, str] = {
    "chrome": "Google Chrome",
    "google chrome": "Google Chrome",
    "edge": "Microsoft Edge",
    "microsoft edge": "Microsoft Edge",
    "navegador": "Navegador Web",
    "firefox": "Mozilla Firefox",
    "brave": "Brave Browser",
    "bloco de notas": "Bloco de Notas",
    "notepad": "Bloco de Notas",
    "calculadora": "Calculadora",
    "calc": "Calculadora",
    "explorador de arquivos": "Explorador de Arquivos",
    "explorer": "Explorador de Arquivos",
    "paint": "Paint",
    "vscode": "Visual Studio Code",
    "vs code": "Visual Studio Code",
    "spotify": "Spotify",
    "youtube": "YouTube (Navegador)",
    "whatsapp": "WhatsApp",
}

# Identifiers that cannot be closed via custom scenes to protect the Windows desktop shell
FORBIDDEN_CLOSE_APP_IDENTIFIERS: set[str] = {
    "explorador de arquivos",
    "explorer",
}

ALLOWED_FIRE_TV_APPS: set[str] = {
    "youtube",
    "netflix",
    "prime_video",
    "prime video",
    "disney",
    "spotify",
    "globoplay",
    "max",
    "crunchyroll",
}

# Authorized catalog of custom routine building blocks
ALLOWED_CUSTOM_STEP_TYPES: Dict[str, Dict[str, Any]] = {
    "silenciar_avisos": {
        "description": "Silenciar som dos avisos proativos da agenda",
        "modifies_state": True,
        "is_sensitive": False,
    },
    "ativar_avisos": {
        "description": "Ativar som dos avisos proativos da agenda",
        "modifies_state": True,
        "is_sensitive": False,
    },
    "ajustar_volume_pc": {
        "description": "Ajustar volume do Windows (0 a 100%)",
        "modifies_state": True,
        "is_sensitive": False,
    },
    "pausar_midia_pc": {
        "description": "Enviar comando de parada de mídia ao Windows",
        "modifies_state": False,
        "is_sensitive": False,
    },
    "abrir_app_pc": {
        "description": "Abrir aplicativo autorizado no Windows",
        "modifies_state": False,
        "is_sensitive": False,
    },
    "fechar_app_pc": {
        "description": "Fechar aplicativo autorizado no Windows (risco de perda de documentos não salvos)",
        "modifies_state": False,
        "is_sensitive": True,
    },
    "abrir_app_fire_tv": {
        "description": "Abrir aplicativo no Fire TV Stick",
        "modifies_state": False,
        "is_sensitive": False,
    },
    "criar_timer": {
        "description": "Criar timer local persistente em SQLite",
        "modifies_state": False,
        "is_sensitive": False,
    },
    "consultar_agenda_hoje": {
        "description": "Consultar compromissos de hoje no Google Agenda",
        "modifies_state": False,
        "is_sensitive": False,
    },
    "consultar_agenda_amanha": {
        "description": "Consultar compromissos de amanhã no Google Agenda",
        "modifies_state": False,
        "is_sensitive": False,
    },
    "consultar_tarefas": {
        "description": "Consultar tarefas pendentes no Google Tasks",
        "modifies_state": False,
        "is_sensitive": False,
    },
    "consultar_emails": {
        "description": "Consultar e-mails não lidos no Gmail",
        "modifies_state": False,
        "is_sensitive": False,
    },
    "consultar_telemetria_pc": {
        "description": "Verificar telemetria de CPU, RAM e bateria do Windows",
        "modifies_state": False,
        "is_sensitive": False,
    },
    "consultar_canal_youtube": {
        "description": "Consultar estatísticas do canal autenticado no YouTube",
        "modifies_state": False,
        "is_sensitive": False,
    },
}


def validate_custom_steps(raw_steps: Any) -> Tuple[bool, List[Dict[str, Any]], str]:
    """
    Validate and normalize a list of custom routine steps against the strict
    whitelist of allowed actions and parameters. Never permits arbitrary commands.
    """
    if not isinstance(raw_steps, list) or not raw_steps:
        return (
            False,
            [],
            "A rotina personalizada precisa conter pelo menos uma etapa válida em formato de lista.",
        )
    if len(raw_steps) > 10:
        return (
            False,
            [],
            "Por segurança, cada rotina personalizada pode conter no máximo 10 etapas.",
        )

    normalized_steps: List[Dict[str, Any]] = []
    for idx, item in enumerate(raw_steps, start=1):
        if not isinstance(item, dict):
            return False, [], f"A etapa {idx} é inválida (deve ser um objeto com 'acao')."

        action_type = str(item.get("acao") or item.get("action") or item.get("type") or "").strip().lower()
        if not action_type or action_type not in ALLOWED_CUSTOM_STEP_TYPES:
            allowed_str = ", ".join(sorted(ALLOWED_CUSTOM_STEP_TYPES.keys()))
            return (
                False,
                [],
                (
                    f"Ação '{_sanitize_text(action_type)}' na etapa {idx} não é permitida pelo catálogo de segurança. "
                    f"Ações autorizadas: {allowed_str}."
                ),
            )

        step_clean: Dict[str, Any] = {"acao": action_type}

        if action_type == "ajustar_volume_pc":
            raw_vol = item.get("nivel") if item.get("nivel") is not None else item.get("level")
            try:
                vol = int(raw_vol)
            except (TypeError, ValueError):
                return False, [], f"Na etapa {idx} ('ajustar_volume_pc'), informe um 'nivel' inteiro entre 0 e 100."
            if vol < 0 or vol > 100:
                return False, [], f"Na etapa {idx} ('ajustar_volume_pc'), o volume deve estar entre 0 e 100%."
            step_clean["nivel"] = vol

        elif action_type in ("abrir_app_pc", "fechar_app_pc"):
            raw_app = str(item.get("aplicativo") or item.get("app") or "").strip().lower()
            # Reject paths, slashes, shell metacharacters, or unapproved identifiers
            if (
                not raw_app
                or any(ch in raw_app for ch in ("\\", "/", ";", "&", "|", "`", "$", ">", "<", ".exe", ".bat", ".cmd", ".ps1"))
                or raw_app not in ALLOWED_APP_IDENTIFIERS
            ):
                allowed_apps = ", ".join(sorted(set(ALLOWED_APP_IDENTIFIERS.keys())))
                return (
                    False,
                    [],
                    (
                        f"O aplicativo '{_sanitize_text(raw_app)}' na etapa {idx} não está na lista de identificadores "
                        f"autorizados. Identificadores permitidos: {allowed_apps}."
                    ),
                )
            if action_type == "fechar_app_pc" and raw_app in FORBIDDEN_CLOSE_APP_IDENTIFIERS:
                return (
                    False,
                    [],
                    f"O aplicativo '{raw_app}' não pode ser fechado por uma rotina automática para proteger o shell do Windows.",
                )
            step_clean["aplicativo"] = raw_app

        elif action_type == "abrir_app_fire_tv":
            raw_tv_app = str(item.get("aplicativo") or item.get("app") or "youtube").strip().lower()
            if raw_tv_app not in ALLOWED_FIRE_TV_APPS:
                allowed_tv = ", ".join(sorted(ALLOWED_FIRE_TV_APPS))
                return (
                    False,
                    [],
                    f"O aplicativo de Fire TV '{_sanitize_text(raw_tv_app)}' na etapa {idx} não é autorizado. Permitidos: {allowed_tv}.",
                )
            step_clean["aplicativo"] = raw_tv_app

        elif action_type == "criar_timer":
            raw_min = item.get("minutos") if item.get("minutos") is not None else item.get("duration_minutes")
            try:
                mins = int(raw_min)
            except (TypeError, ValueError):
                return False, [], f"Na etapa {idx} ('criar_timer'), informe 'minutos' como número inteiro positivo."
            if mins < 1 or mins > 720:
                return False, [], f"Na etapa {idx} ('criar_timer'), a duração deve estar entre 1 e 720 minutos."
            raw_title = str(item.get("titulo") or item.get("title") or f"Timer ({mins} min)").strip()
            step_clean["minutos"] = mins
            step_clean["titulo"] = _sanitize_text(raw_title[:80])

        normalized_steps.append(step_clean)

    return True, normalized_steps, "OK"


def describe_custom_step(step: Dict[str, Any]) -> str:
    """Build a human-readable Portuguese description for a validated custom step."""
    action = step.get("acao", "")
    if action == "silenciar_avisos":
        return "Silenciar som dos avisos proativos da agenda"
    if action == "ativar_avisos":
        return "Ativar som dos avisos proativos da agenda"
    if action == "ajustar_volume_pc":
        return f"Ajustar volume do Windows para {step.get('nivel')}%"
    if action == "pausar_midia_pc":
        return "Parar reprodução de mídia no Windows"
    if action == "abrir_app_pc":
        app_id = str(step.get("aplicativo", ""))
        friendly = ALLOWED_APP_IDENTIFIERS.get(app_id, app_id)
        return f"Abrir {friendly} no Windows"
    if action == "fechar_app_pc":
        app_id = str(step.get("aplicativo", ""))
        friendly = ALLOWED_APP_IDENTIFIERS.get(app_id, app_id)
        return f"Fechar {friendly} no Windows (ação sensível: atenção a documentos não salvos)"
    if action == "abrir_app_fire_tv":
        return f"Abrir {str(step.get('aplicativo', 'youtube')).capitalize()} no Fire TV Stick"
    if action == "criar_timer":
        return f"Criar timer persistente '{step.get('titulo', 'Timer')}' de {step.get('minutos')} minuto(s)"
    return ALLOWED_CUSTOM_STEP_TYPES.get(action, {}).get("description", action)


# ---------------------------------------------------------------------------
# Requirement 1: Proposal-Bound Confirmation Manager (60s TTL, Single-Use)
# ---------------------------------------------------------------------------


@dataclass
class SceneProposal:
    proposal_id: str
    operation: str  # "create_custom_scene" | "delete_custom_scene" | "execute_sensitive_scene"
    scene_slug: str
    scene_title: str
    payload: Dict[str, Any]
    summary_pt: str
    session_id: str
    created_at_mono: float
    expires_at_mono: float
    status: str = "pending"  # "pending" | "confirmed" | "superseded" | "expired"


class SceneConfirmationManager:
    """
    Server-side two-phase confirmation gate for creating, deleting, or executing
    sensitive custom routines. Enforces:
    - Binding to the current interaction/session (`session_id`),
    - 60-second TTL (`PROPOSAL_TTL_SECONDS = 60.0`),
    - Superseding older pending proposals in the same session,
    - Single-use consumption (rejects duplicate confirmations).
    """

    def __init__(self, ttl_seconds: float = PROPOSAL_TTL_SECONDS, clock: Callable[[], float] = time.monotonic):
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._proposals: Dict[str, SceneProposal] = {}
        self._active_session_id: str = "default_voice_session"

    def set_active_session(self, session_id: str) -> None:
        with self._lock:
            self._active_session_id = str(session_id or "default_voice_session")

    def get_active_session(self) -> str:
        with self._lock:
            return self._active_session_id

    def reset(self) -> None:
        with self._lock:
            self._proposals.clear()
            self._active_session_id = "default_voice_session"

    def create_proposal(
        self,
        operation: str,
        scene_slug: str,
        scene_title: str,
        payload: Dict[str, Any],
        summary_pt: str,
        session_id: Optional[str] = None,
    ) -> SceneProposal:
        now = self._clock()
        with self._lock:
            sess = str(session_id or self._active_session_id)
            # Supersede any prior pending proposal in the same session
            for existing in self._proposals.values():
                if existing.session_id == sess and existing.status == "pending":
                    existing.status = "superseded"

            prop_id = f"scene_prop_{secrets.token_hex(6)}"
            proposal = SceneProposal(
                proposal_id=prop_id,
                operation=operation,
                scene_slug=scene_slug,
                scene_title=scene_title,
                payload=payload,
                summary_pt=summary_pt,
                session_id=sess,
                created_at_mono=now,
                expires_at_mono=now + self._ttl_seconds,
                status="pending",
            )
            self._proposals[prop_id] = proposal
            return proposal

    def consume_proposal(
        self,
        proposal_id: str,
        session_id: Optional[str] = None,
    ) -> Tuple[Optional[SceneProposal], str, str]:
        now = self._clock()
        clean_id = str(proposal_id or "").strip()
        with self._lock:
            sess = str(session_id or self._active_session_id)
            prop = self._proposals.get(clean_id)
            if prop is None:
                return (
                    None,
                    "proposal_not_found",
                    "Proposta de confirmação não encontrada. Solicite a ação novamente antes de confirmar.",
                )
            if prop.session_id != sess:
                return (
                    None,
                    "session_mismatch",
                    "Esta proposta pertence a uma sessão de voz anterior e não pode mais ser confirmada.",
                )
            if prop.status == "confirmed":
                return (
                    None,
                    "duplicate_confirmation",
                    "Esta proposta já foi confirmada anteriormente. Comandos duplicados são bloqueados por segurança.",
                )
            if prop.status == "superseded":
                return (
                    None,
                    "proposal_superseded",
                    "Esta proposta foi substituída por um pedido mais recente na conversa atual.",
                )
            if now > prop.expires_at_mono or prop.status == "expired":
                prop.status = "expired"
                return (
                    None,
                    "proposal_expired",
                    "O prazo de 60 segundos para confirmar esta rotina expirou. Faça o pedido novamente se desejar prosseguir.",
                )

            prop.status = "confirmed"
            return prop, "confirmed", "OK"


_SCENE_CONFIRMATION_MANAGER = SceneConfirmationManager()


def get_scene_confirmation_manager() -> SceneConfirmationManager:
    return _SCENE_CONFIRMATION_MANAGER


# Anti-duplication state
_scene_guard_lock = threading.Lock()
_active_scenes: set[str] = set()
_last_scene_finished_at: Dict[str, float] = {}


def reset_scene_guards() -> None:
    """Reset deduplication and confirmation state (used by unit tests)."""
    with _scene_guard_lock:
        _active_scenes.clear()
        _last_scene_finished_at.clear()
    _SCENE_CONFIRMATION_MANAGER.reset()


def _normalize_scene_name(raw_name: str) -> Optional[str]:
    cleaned = (raw_name or "").strip().lower()
    if cleaned in SCENE_ALIASES:
        return SCENE_ALIASES[cleaned]
    slug = _slugify_scene_name(cleaned)
    if slug in SCENE_ALIASES:
        return SCENE_ALIASES[slug]
    for alias, canonical in SCENE_ALIASES.items():
        if alias == cleaned or _slugify_scene_name(alias) == slug:
            return canonical
    return None


# ---------------------------------------------------------------------------
# Requirement 4: Transactional SQLite Persistence for Snapshots & Custom Scenes
# ---------------------------------------------------------------------------


def _ensure_scene_tables(db_path: Path = DEFAULT_DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path), timeout=5.0) as conn:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS scene_state_snapshots (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    scene_name TEXT NOT NULL,
                    previous_volume_percent INTEGER,
                    previous_is_muted INTEGER,
                    previous_dnd_mute_sound INTEGER NOT NULL,
                    previous_dnd_block_visual INTEGER NOT NULL,
                    quiet_start_hour INTEGER NOT NULL,
                    quiet_end_hour INTEGER NOT NULL,
                    saved_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS custom_scenes (
                    slug TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    steps_json TEXT NOT NULL,
                    modifies_state INTEGER NOT NULL DEFAULT 0,
                    has_sensitive_actions INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduled_scenes (
                    schedule_id TEXT PRIMARY KEY,
                    scene_slug TEXT NOT NULL,
                    scene_title TEXT NOT NULL,
                    time_hhmm TEXT NOT NULL,
                    days_of_week TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    last_triggered_date TEXT,
                    last_result_summary TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )


def _save_custom_scene_to_db(
    slug: str,
    title: str,
    description: str,
    steps: List[Dict[str, Any]],
    db_path: Path = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    """Persist a validated custom scene atomically inside a SQLite transaction."""
    _ensure_scene_tables(db_path)
    if slug in PROTECTED_NATIVE_SLUGS:
        raise ValueError(f"O nome '{slug}' pertence a uma cena nativa protegida e não pode ser sobrescrito.")

    modifies_state = any(
        ALLOWED_CUSTOM_STEP_TYPES.get(s.get("acao", ""), {}).get("modifies_state", False)
        for s in steps
    )
    has_sensitive = any(
        ALLOWED_CUSTOM_STEP_TYPES.get(s.get("acao", ""), {}).get("is_sensitive", False)
        for s in steps
    )
    now_iso = datetime.now().astimezone().isoformat()
    steps_serialized = json.dumps(steps, ensure_ascii=False)

    with sqlite3.connect(str(db_path), timeout=5.0) as conn:
        with conn:
            conn.execute(
                """
                INSERT INTO custom_scenes (
                    slug, title, description, steps_json,
                    modifies_state, has_sensitive_actions, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(slug) DO UPDATE SET
                    title = excluded.title,
                    description = excluded.description,
                    steps_json = excluded.steps_json,
                    modifies_state = excluded.modifies_state,
                    has_sensitive_actions = excluded.has_sensitive_actions,
                    updated_at = excluded.updated_at
                """,
                (
                    slug,
                    title,
                    description,
                    steps_serialized,
                    1 if modifies_state else 0,
                    1 if has_sensitive else 0,
                    now_iso,
                    now_iso,
                ),
            )

    return get_custom_scene_from_db(slug, db_path=db_path) or {}


def get_custom_scene_from_db(slug_or_name: str, db_path: Path = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    """Lookup a custom scene by slug or spoken name from SQLite."""
    _ensure_scene_tables(db_path)
    slug = _slugify_scene_name(slug_or_name)
    if not slug:
        return None
    with sqlite3.connect(str(db_path), timeout=5.0) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM custom_scenes WHERE slug = ?",
            (slug,),
        ).fetchone()
    if not row:
        return None
    try:
        steps = json.loads(str(row["steps_json"]))
    except Exception:
        steps = []
    return {
        "name": str(row["slug"]),
        "slug": str(row["slug"]),
        "title": str(row["title"]),
        "description": str(row["description"]),
        "steps": steps,
        "modifies_state": bool(row["modifies_state"]),
        "has_sensitive_actions": bool(row["has_sensitive_actions"]),
        "is_native": False,
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }


def list_custom_scenes_from_db(db_path: Path = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    """Return all user-created custom scenes stored in SQLite."""
    _ensure_scene_tables(db_path)
    with sqlite3.connect(str(db_path), timeout=5.0) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM custom_scenes ORDER BY slug ASC"
        ).fetchall()
    out: List[Dict[str, Any]] = []
    for row in rows:
        try:
            steps = json.loads(str(row["steps_json"]))
        except Exception:
            steps = []
        out.append(
            {
                "name": str(row["slug"]),
                "slug": str(row["slug"]),
                "title": str(row["title"]),
                "description": str(row["description"]),
                "steps": steps,
                "modifies_state": bool(row["modifies_state"]),
                "has_sensitive_actions": bool(row["has_sensitive_actions"]),
                "is_native": False,
            }
        )
    return out


def _delete_custom_scene_from_db(slug: str, db_path: Path = DEFAULT_DB_PATH) -> bool:
    """Delete a custom scene inside a SQLite transaction (never deletes native scenes)."""
    if slug in PROTECTED_NATIVE_SLUGS:
        return False
    _ensure_scene_tables(db_path)
    with sqlite3.connect(str(db_path), timeout=5.0) as conn:
        with conn:
            cur = conn.execute("DELETE FROM custom_scenes WHERE slug = ?", (slug,))
            return cur.rowcount > 0


def get_saved_scene_snapshot(db_path: Path = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    """Read the currently stored pre-scene state snapshot from SQLite, if any."""
    _ensure_scene_tables(db_path)
    with sqlite3.connect(str(db_path), timeout=5.0) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM scene_state_snapshots WHERE id = 1"
        ).fetchone()
    if not row:
        return None
    return {
        "scene_name": str(row["scene_name"]),
        "previous_volume_percent": (
            int(row["previous_volume_percent"])
            if row["previous_volume_percent"] is not None
            else None
        ),
        "previous_is_muted": (
            bool(row["previous_is_muted"])
            if row["previous_is_muted"] is not None
            else None
        ),
        "previous_dnd_mute_sound": bool(row["previous_dnd_mute_sound"]),
        "previous_dnd_block_visual": bool(row["previous_dnd_block_visual"]),
        "quiet_start_hour": int(row["quiet_start_hour"]),
        "quiet_end_hour": int(row["quiet_end_hour"]),
        "saved_at": str(row["saved_at"]),
    }


def save_pre_scene_snapshot(
    scene_name: str,
    db_path: Path = DEFAULT_DB_PATH,
    overwrite_existing: bool = False,
) -> Dict[str, Any]:
    """
    Capture current Windows volume and Proactive Calendar DND flags before a scene
    modifies them. Preserves the original baseline snapshot when nested scenes run.
    """
    _ensure_scene_tables(db_path)
    existing = get_saved_scene_snapshot(db_path)
    if existing is not None and not overwrite_existing:
        return existing

    from src.core.proactive_calendar import get_proactive_calendar_monitor
    from src.tools.system_audio import set_system_volume

    prev_vol: Optional[int] = None
    prev_muted: Optional[bool] = None
    try:
        audio_state = set_system_volume()
        if isinstance(audio_state, dict) and audio_state.get("status") == "success":
            if audio_state.get("volume_percent") is not None:
                prev_vol = int(audio_state["volume_percent"])
            if audio_state.get("is_muted") is not None:
                prev_muted = bool(audio_state["is_muted"])
    except Exception as exc:
        logger.warning("Could not read current volume for snapshot: %s", _sanitize_text(exc))

    dnd_mute_sound = False
    dnd_block_visual = False
    quiet_start = 23
    quiet_end = 7
    try:
        monitor = get_proactive_calendar_monitor()
        settings = monitor.get_settings()
        dnd_mute_sound = bool(settings.dnd_mute_sound)
        dnd_block_visual = bool(settings.dnd_block_visual)
        quiet_start = int(settings.quiet_start_hour)
        quiet_end = int(settings.quiet_end_hour)
    except Exception as exc:
        logger.warning("Could not read proactive settings for snapshot: %s", _sanitize_text(exc))

    saved_at = datetime.now().astimezone().isoformat()
    with sqlite3.connect(str(db_path), timeout=5.0) as conn:
        with conn:
            conn.execute(
                """
                INSERT INTO scene_state_snapshots (
                    id, scene_name, previous_volume_percent, previous_is_muted,
                    previous_dnd_mute_sound, previous_dnd_block_visual,
                    quiet_start_hour, quiet_end_hour, saved_at
                ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    scene_name = excluded.scene_name,
                    previous_volume_percent = excluded.previous_volume_percent,
                    previous_is_muted = excluded.previous_is_muted,
                    previous_dnd_mute_sound = excluded.previous_dnd_mute_sound,
                    previous_dnd_block_visual = excluded.previous_dnd_block_visual,
                    quiet_start_hour = excluded.quiet_start_hour,
                    quiet_end_hour = excluded.quiet_end_hour,
                    saved_at = excluded.saved_at
                """,
                (
                    scene_name,
                    prev_vol,
                    (1 if prev_muted else 0) if prev_muted is not None else None,
                    1 if dnd_mute_sound else 0,
                    1 if dnd_block_visual else 0,
                    quiet_start,
                    quiet_end,
                    saved_at,
                ),
            )

    return get_saved_scene_snapshot(db_path) or {}


def _clear_scene_snapshot(db_path: Path = DEFAULT_DB_PATH) -> None:
    _ensure_scene_tables(db_path)
    with sqlite3.connect(str(db_path), timeout=5.0) as conn:
        with conn:
            conn.execute("DELETE FROM scene_state_snapshots WHERE id = 1")


def _run_step_isolated(
    step_id: str,
    description: str,
    action_fn: Callable[[], Tuple[str, str, Optional[Dict[str, Any]]]],
    timeout_seconds: float = DEFAULT_STEP_TIMEOUT_SECONDS,
) -> SceneStepResult:
    """
    Execute a single scene step in an isolated worker with strict timeout protection,
    catching any exception so it never aborts subsequent steps, and sanitizing output.
    """
    started = time.monotonic()
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = executor.submit(action_fn)
    try:
        level, msg, details = future.result(timeout=timeout_seconds)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        if level not in ("confirmed", "sent_unverified", "failed"):
            level = "failed"
        return SceneStepResult(
            step_id=step_id,
            description=description,
            verification_level=level,
            message=_sanitize_text(msg),
            duration_ms=elapsed_ms,
            details=details,
        )
    except concurrent.futures.TimeoutError:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        logger.warning("Scene step '%s' timed out after %.1fs", step_id, timeout_seconds)
        return SceneStepResult(
            step_id=step_id,
            description=description,
            verification_level="failed",
            message=f"{description}: tempo limite excedido ({timeout_seconds:.1f}s).",
            duration_ms=elapsed_ms,
            details={"reason": "timeout"},
        )
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        clean_err = _sanitize_text(exc)
        logger.warning("Scene step '%s' failed with error: %s", step_id, clean_err)
        return SceneStepResult(
            step_id=step_id,
            description=description,
            verification_level="failed",
            message=f"{description}: falhou ({clean_err}).",
            duration_ms=elapsed_ms,
            details={"reason": "exception", "error": clean_err},
        )
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _build_scene_report(
    scene_name: str,
    scene_title: str,
    steps: List[SceneStepResult],
    snapshot: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build structured per-step verification report and natural spoken Portuguese summary."""
    confirmed_steps = [s for s in steps if s.verification_level == "confirmed"]
    unverified_steps = [s for s in steps if s.verification_level == "sent_unverified"]
    failed_steps = [s for s in steps if s.verification_level == "failed"]

    parts: List[str] = [f"Cena '{scene_title}' executada."]
    if confirmed_steps:
        confirmed_text = "; ".join(s.message for s in confirmed_steps)
        parts.append(f"Confirmado: {confirmed_text}")
    if unverified_steps:
        unverified_text = "; ".join(s.message for s in unverified_steps)
        parts.append(f"Comando enviado sem confirmação final: {unverified_text}")
    if failed_steps:
        failed_text = "; ".join(s.message for s in failed_steps)
        parts.append(f"Não concluído: {failed_text}")

    if failed_steps and not confirmed_steps and not unverified_steps:
        overall_status = "error"
    elif failed_steps or unverified_steps:
        overall_status = "partial"
    else:
        overall_status = "success"

    report: Dict[str, Any] = {
        "status": overall_status,
        "scene": scene_name,
        "title": scene_title,
        "counts": {
            "total": len(steps),
            "confirmed": len(confirmed_steps),
            "sent_unverified": len(unverified_steps),
            "failed": len(failed_steps),
        },
        "steps": [asdict(s) for s in steps],
        "message": " ".join(parts),
    }
    if snapshot is not None:
        report["snapshot_saved"] = snapshot
    return report


# ---------------------------------------------------------------------------
# Individual Step Implementations with Real 3-Level Verification
# ---------------------------------------------------------------------------


def _step_set_proactive_sound(mute: bool) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    from src.core.proactive_calendar import get_proactive_calendar_monitor
    from src.tools.proactive_tools import configurar_avisos_proativos

    res = configurar_avisos_proativos(silenciar_som=mute)
    monitor = get_proactive_calendar_monitor()
    readback = monitor.get_settings()
    if isinstance(res, dict) and res.get("status") == "success" and bool(readback.dnd_mute_sound) is bool(mute):
        label = "silenciado" if mute else "ativado"
        return (
            "confirmed",
            f"som dos avisos proativos da agenda {label} (horário de silêncio permanente preservado)",
            {
                "dnd_mute_sound": readback.dnd_mute_sound,
                "quiet_hours": f"{readback.quiet_start_hour:02d}:00-{readback.quiet_end_hour:02d}:00",
            },
        )
    return (
        "failed",
        _sanitize_text(res.get("message", "não foi possível atualizar os avisos proativos")),
        res if isinstance(res, dict) else None,
    )


def _step_mute_proactive_sound() -> Tuple[str, str, Optional[Dict[str, Any]]]:
    return _step_set_proactive_sound(True)


def _step_set_windows_volume(target_level: int) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    from src.tools.system_audio import set_system_volume

    res = set_system_volume(level=target_level, mute=False)
    if not isinstance(res, dict) or res.get("status") != "success":
        return (
            "failed",
            _sanitize_text(
                res.get("message", f"falha ao ajustar volume do Windows para {target_level}%")
                if isinstance(res, dict)
                else "falha ao ajustar volume do Windows"
            ),
            res if isinstance(res, dict) else None,
        )

    actual_vol = res.get("volume_percent")
    if actual_vol is not None and abs(int(actual_vol) - int(target_level)) <= 2:
        return (
            "confirmed",
            f"volume do Windows ajustado e verificado em {actual_vol}%",
            {"volume_percent": actual_vol, "is_muted": res.get("is_muted")},
        )
    return (
        "sent_unverified",
        f"comando de volume ({target_level}%) enviado ao Windows, mas a leitura retornou {actual_vol}%",
        {"volume_percent": actual_vol},
    )


def _step_pause_windows_media() -> Tuple[str, str, Optional[Dict[str, Any]]]:
    from src.tools.system_audio import control_system_media

    res = control_system_media("stop")
    if isinstance(res, dict) and res.get("status") == "success":
        return (
            "sent_unverified",
            "comando de parada de mídia enviado ao Windows (tecla multimídia sem leitura de player ativo)",
            {"action": "stop"},
        )
    return (
        "failed",
        _sanitize_text(
            res.get("message", "falha ao enviar tecla de parada de mídia")
            if isinstance(res, dict)
            else "falha ao enviar tecla de parada de mídia"
        ),
        res if isinstance(res, dict) else None,
    )


def _step_open_windows_app(app_identifier: str) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    clean_app = str(app_identifier or "").strip().lower()
    if clean_app not in ALLOWED_APP_IDENTIFIERS:
        return (
            "failed",
            f"identificador de aplicativo '{_sanitize_text(clean_app)}' não autorizado pelo catálogo de segurança",
            {"reason": "unauthorized_app"},
        )

    from src.tools.windows_apps import open_application

    res = open_application(clean_app)
    if not isinstance(res, dict):
        return ("failed", f"falha ao abrir {clean_app} no Windows", None)
    status = res.get("status")
    friendly = ALLOWED_APP_IDENTIFIERS[clean_app]
    if status == "success" and res.get("confirmed", True) is not False:
        return (
            "confirmed",
            f"aplicativo {friendly} aberto e confirmado no Windows",
            {"app": clean_app},
        )
    if status in ("inconclusive", "uncertain") or (res.get("action_sent") and not res.get("confirmed")):
        return (
            "sent_unverified",
            f"comando para abrir {friendly} enviado ao Windows, sem confirmação de janela ativa",
            {"app": clean_app},
        )
    return (
        "failed",
        _sanitize_text(res.get("message", f"não foi possível abrir {friendly}")),
        res,
    )


def _step_close_windows_app(app_identifier: str) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    clean_app = str(app_identifier or "").strip().lower()
    if clean_app not in ALLOWED_APP_IDENTIFIERS or clean_app in FORBIDDEN_CLOSE_APP_IDENTIFIERS:
        return (
            "failed",
            f"identificador de aplicativo '{_sanitize_text(clean_app)}' não autorizado para fechamento",
            {"reason": "unauthorized_app"},
        )

    from src.tools.windows_apps import close_application

    res = close_application(clean_app)
    if not isinstance(res, dict):
        return ("failed", f"falha ao fechar {clean_app} no Windows", None)
    status = res.get("status")
    friendly = ALLOWED_APP_IDENTIFIERS[clean_app]
    if status == "success":
        return (
            "confirmed",
            f"aplicativo {friendly} fechado e confirmado no Windows",
            {"app": clean_app},
        )
    if status in ("inconclusive", "uncertain"):
        return (
            "sent_unverified",
            f"sinal de fechamento enviado para {friendly}, mas o processo permaneceu aberto (possível documento não salvo aguardando confirmação na janela)",
            {"app": clean_app},
        )
    return (
        "failed",
        _sanitize_text(res.get("message", f"não foi possível fechar {friendly}")),
        res,
    )


def _step_launch_fire_tv_app(app_name: str = "youtube") -> Tuple[str, str, Optional[Dict[str, Any]]]:
    from src.tools.fire_tv import launch_fire_tv_app

    res = launch_fire_tv_app(app_name)
    if not isinstance(res, dict):
        return ("failed", f"falha ao acionar {app_name} no Fire TV Stick", None)

    status = res.get("status")
    confirmed = res.get("confirmed")
    action_sent = res.get("action_sent")

    if status == "success" and confirmed is True:
        fg_pkg = res.get("foreground_package") or app_name
        return (
            "confirmed",
            f"aplicativo {app_name.capitalize()} aberto e confirmado em primeiro plano no Fire TV Stick ({fg_pkg})",
            {"foreground_package": fg_pkg, "confirmed": True},
        )

    if status in ("inconclusive", "uncertain") or (action_sent is True and not confirmed):
        fg_pkg = res.get("foreground_package")
        return (
            "sent_unverified",
            (
                f"comando para abrir {app_name.capitalize()} foi enviado ao Fire TV Stick conectado, "
                f"mas não foi possível confirmar que o aplicativo entrou em primeiro plano"
            ),
            {"foreground_package": fg_pkg, "confirmed": False, "action_sent": True},
        )

    return (
        "failed",
        _sanitize_text(res.get("message", f"Fire TV Stick indisponível ao tentar abrir {app_name}")),
        res,
    )


def _step_create_persistent_timer(
    duration_minutes: int,
    title: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    seconds = max(60, int(duration_minutes) * 60)
    timer_title = _sanitize_text(title or f"Modo Foco ({duration_minutes} min)")

    if db_path is not None and db_path != DEFAULT_DB_PATH:
        # When an isolated SQLite DB is provided, persist directly in ReminderStore at db_path
        # so tests and restarts on that DB path can verify timer recovery across restarts.
        from src.core.reminders import ReminderStore

        store = ReminderStore(path=db_path)
        item = store.create(timer_title, seconds=seconds)
        return (
            "confirmed",
            f"timer '{timer_title}' de {duration_minutes} minutos criado e salvo no banco (ID {item.get('id', 'ok')})",
            {"reminder_id": item.get("id"), "seconds": seconds, "title": timer_title},
        )

    from src.tools.reminders import dispatch_reminder_tool

    res = dispatch_reminder_tool(
        "create_timer",
        {"seconds": seconds, "title": timer_title},
    )
    if isinstance(res, dict) and res.get("status") == "success" and res.get("reminder"):
        rem = res["reminder"]
        return (
            "confirmed",
            f"timer de foco de {duration_minutes} minutos criado e salvo no banco (ID {rem.get('id', 'ok')})",
            {"reminder_id": rem.get("id"), "seconds": seconds, "title": timer_title},
        )
    return (
        "failed",
        _sanitize_text(
            res.get("message", "não foi possível criar o timer de foco")
            if isinstance(res, dict)
            else "não foi possível criar o timer de foco"
        ),
        res if isinstance(res, dict) else None,
    )


def _step_calendar_events(day_keyword: str, label: str) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    from src.tools.google_calendar import list_events

    res = list_events(time_min=day_keyword, max_results=10)
    if not isinstance(res, dict) or res.get("status") != "success":
        return (
            "failed",
            _sanitize_text(
                res.get("message", f"não foi possível consultar a agenda ({label})")
                if isinstance(res, dict)
                else f"não foi possível consultar a agenda ({label})"
            ),
            res if isinstance(res, dict) else None,
        )

    events = res.get("events") or []
    if not events:
        return (
            "confirmed",
            f"Google Agenda consultada ({label}): nenhum compromisso agendado",
            {"count": 0, "events": []},
        )
    titles = [str(ev.get("summary") or "Sem título") for ev in events[:3]]
    summary_list = ", ".join(titles)
    return (
        "confirmed",
        f"Google Agenda consultada ({label}): {len(events)} compromisso(s) ({summary_list})",
        {"count": len(events), "events": events[:5]},
    )


def _step_pending_tasks() -> Tuple[str, str, Optional[Dict[str, Any]]]:
    from src.tools.google_tasks import list_tasks

    res = list_tasks(max_results=10, show_completed=False)
    if not isinstance(res, dict) or res.get("status") != "success":
        return (
            "failed",
            _sanitize_text(
                res.get("message", "não foi possível consultar o Google Tasks")
                if isinstance(res, dict)
                else "não foi possível consultar o Google Tasks"
            ),
            res if isinstance(res, dict) else None,
        )

    tasks = res.get("tasks") or []
    if not tasks:
        return (
            "confirmed",
            "Google Tasks consultado: nenhuma tarefa pendente",
            {"count": 0},
        )
    titles = [str(t.get("title") or "Tarefa") for t in tasks[:3]]
    return (
        "confirmed",
        f"Google Tasks consultado: {len(tasks)} tarefa(s) pendente(s) ({', '.join(titles)})",
        {"count": len(tasks), "tasks": tasks[:5]},
    )


def _step_unread_emails() -> Tuple[str, str, Optional[Dict[str, Any]]]:
    from src.tools.gmail import list_unread_emails

    res = list_unread_emails(max_results=5)
    if not isinstance(res, dict) or res.get("status") not in ("success", "partial"):
        return (
            "failed",
            _sanitize_text(
                res.get("message", "não foi possível consultar o Gmail")
                if isinstance(res, dict)
                else "não foi possível consultar o Gmail"
            ),
            res if isinstance(res, dict) else None,
        )

    emails = res.get("emails") or []
    count = res.get("count", len(emails))
    if not count:
        return (
            "confirmed",
            "Gmail consultado: nenhum e-mail não lido importante",
            {"count": 0},
        )
    return (
        "confirmed",
        f"Gmail consultado: {count} e-mail(s) não lido(s) recente(s)",
        {"count": count},
    )


def _step_system_telemetry() -> Tuple[str, str, Optional[Dict[str, Any]]]:
    from src.tools.system_telemetry import get_system_telemetry

    res = get_system_telemetry()
    if not isinstance(res, dict) or res.get("status") != "success":
        return (
            "failed",
            _sanitize_text(
                res.get("message", "não foi possível ler a telemetria do Windows")
                if isinstance(res, dict)
                else "não foi possível ler a telemetria do Windows"
            ),
            res if isinstance(res, dict) else None,
        )

    cpu = res.get("cpu_percent")
    ram = res.get("ram_percent")
    battery = res.get("battery") or {}
    bat_pct = battery.get("percent") if isinstance(battery, dict) else None
    bat_str = f", bateria em {bat_pct}%" if bat_pct is not None else ""
    return (
        "confirmed",
        f"telemetria do PC verificada (CPU {cpu}%, RAM {ram}%{bat_str})",
        {"cpu_percent": cpu, "ram_percent": ram, "battery": battery},
    )


def _step_youtube_channel_summary() -> Tuple[str, str, Optional[Dict[str, Any]]]:
    from src.tools.youtube import list_youtube_channels

    res = list_youtube_channels()
    if not isinstance(res, dict) or res.get("status") not in ("connected", "success"):
        return (
            "failed",
            _sanitize_text(
                res.get("message", "não foi possível consultar os canais do YouTube")
                if isinstance(res, dict)
                else "não foi possível consultar os canais do YouTube"
            ),
            res if isinstance(res, dict) else None,
        )
    channels = res.get("channels") or []
    if not channels:
        return ("confirmed", "YouTube consultado: nenhum canal vinculado", {"count": 0})
    ch = channels[0]
    return (
        "confirmed",
        (
            f"canal do YouTube '{ch.get('title')}' verificado "
            f"({ch.get('subscriber_count', 0)} inscritos, {ch.get('video_count', 0)} vídeos)"
        ),
        {"channel_id": ch.get("channel_id"), "title": ch.get("title")},
    )


def _execute_custom_step_list(
    custom_steps: List[Dict[str, Any]],
    step_timeout_seconds: float,
    db_path: Path,
) -> List[SceneStepResult]:
    """Execute a validated list of custom scene steps with fault isolation and 3-level verification."""
    results: List[SceneStepResult] = []
    for idx, step in enumerate(custom_steps, start=1):
        action = str(step.get("acao") or "").strip().lower()
        step_id = f"step_{idx}_{action}"
        desc = describe_custom_step(step)

        if action not in ALLOWED_CUSTOM_STEP_TYPES:
            results.append(
                SceneStepResult(
                    step_id=step_id,
                    description=desc,
                    verification_level="failed",
                    message=f"Ação '{_sanitize_text(action)}' bloqueada por não pertencer ao catálogo autorizado.",
                )
            )
            continue

        if action == "silenciar_avisos":
            fn = lambda: _step_set_proactive_sound(True)
        elif action == "ativar_avisos":
            fn = lambda: _step_set_proactive_sound(False)
        elif action == "ajustar_volume_pc":
            lvl = int(step.get("nivel", 20))
            fn = lambda lvl=lvl: _step_set_windows_volume(lvl)
        elif action == "pausar_midia_pc":
            fn = _step_pause_windows_media
        elif action == "abrir_app_pc":
            app_id = str(step.get("aplicativo", ""))
            fn = lambda app_id=app_id: _step_open_windows_app(app_id)
        elif action == "fechar_app_pc":
            app_id = str(step.get("aplicativo", ""))
            fn = lambda app_id=app_id: _step_close_windows_app(app_id)
        elif action == "abrir_app_fire_tv":
            tv_app = str(step.get("aplicativo", "youtube"))
            fn = lambda tv_app=tv_app: _step_launch_fire_tv_app(tv_app)
        elif action == "criar_timer":
            mins = int(step.get("minutos", 30))
            title = str(step.get("titulo") or f"Timer ({mins} min)")
            fn = lambda mins=mins, title=title: _step_create_persistent_timer(mins, title=title, db_path=db_path)
        elif action == "consultar_agenda_hoje":
            fn = lambda: _step_calendar_events("today", "hoje")
        elif action == "consultar_agenda_amanha":
            fn = lambda: _step_calendar_events("tomorrow", "amanhã")
        elif action == "consultar_tarefas":
            fn = _step_pending_tasks
        elif action == "consultar_emails":
            fn = _step_unread_emails
        elif action == "consultar_telemetria_pc":
            fn = _step_system_telemetry
        elif action == "consultar_canal_youtube":
            fn = _step_youtube_channel_summary
        else:
            continue

        results.append(
            _run_step_isolated(
                step_id=step_id,
                description=desc,
                action_fn=fn,
                timeout_seconds=step_timeout_seconds,
            )
        )
    return results


# ---------------------------------------------------------------------------
# Public Voice Tools: Custom Routine Proposal, Confirmation & Deletion
# ---------------------------------------------------------------------------


def propor_cena_personalizada(
    nome_cena: str,
    etapas: List[Dict[str, Any]],
    descricao: Optional[str] = None,
    session_id: Optional[str] = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    """
    Validate a proposed custom routine against the authorized action catalog and
    create a 60-second confirmation proposal (`proposal_id`). Never saves without
    explicit user confirmation via `confirmar_rotina_personalizada`.
    """
    raw_title = _sanitize_text(nome_cena)
    slug = _slugify_scene_name(raw_title)
    if not slug or len(slug) < 2:
        return {
            "status": "error",
            "message": "Por favor, informe um nome válido para a rotina personalizada.",
        }

    # Requirement 4: Protect native scenes against overwrite
    if slug in PROTECTED_NATIVE_SLUGS or _normalize_scene_name(raw_title) is not None:
        return {
            "status": "protected_native_scene",
            "message": (
                f"O nome '{raw_title}' pertence a uma cena nativa protegida do Aton e não pode "
                "ser sobrescrito. Escolha um nome diferente para a sua rotina personalizada."
            ),
        }

    is_valid, clean_steps, err_msg = validate_custom_steps(etapas)
    if not is_valid:
        return {
            "status": "invalid_steps",
            "message": err_msg,
        }

    step_descriptions = [describe_custom_step(s) for s in clean_steps]
    has_sensitive = any(
        ALLOWED_CUSTOM_STEP_TYPES.get(s.get("acao", ""), {}).get("is_sensitive", False)
        for s in clean_steps
    )
    sensitive_warning = (
        " Atenção: esta rotina inclui fechamento de aplicativo no Windows, o que pode causar "
        "perda de documentos não salvos."
        if has_sensitive
        else ""
    )

    existing = get_custom_scene_from_db(slug, db_path=db_path)
    action_verb = "atualizar" if existing else "salvar"
    clean_desc = _sanitize_text(descricao or "; ".join(step_descriptions))

    summary_pt = (
        f"Proposta para {action_verb} a rotina personalizada '{raw_title}' com {len(clean_steps)} etapa(s): "
        f"{'; '.join(step_descriptions)}.{sensitive_warning} "
        f"Você confirma {action_verb} esta rotina? (Responda Sim para confirmar em até 60 segundos)."
    )

    proposal = get_scene_confirmation_manager().create_proposal(
        operation="create_custom_scene",
        scene_slug=slug,
        scene_title=raw_title,
        payload={
            "slug": slug,
            "title": raw_title,
            "description": clean_desc,
            "steps": clean_steps,
            "db_path": str(db_path),
        },
        summary_pt=summary_pt,
        session_id=session_id,
    )

    return {
        "status": "confirmation_required",
        "operation": "create_custom_scene",
        "proposal_id": proposal.proposal_id,
        "scene": slug,
        "title": raw_title,
        "steps_preview": step_descriptions,
        "has_sensitive_actions": has_sensitive,
        "expires_in_seconds": int(PROPOSAL_TTL_SECONDS),
        "message": summary_pt,
    }


def remover_cena_personalizada(
    nome_cena: str,
    session_id: Optional[str] = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    """
    Create a mandatory confirmation proposal to delete a custom routine.
    Native scenes cannot be deleted.
    """
    raw_title = _sanitize_text(nome_cena)
    slug = _slugify_scene_name(raw_title)

    if slug in PROTECTED_NATIVE_SLUGS or _normalize_scene_name(raw_title) is not None:
        return {
            "status": "protected_native_scene",
            "message": (
                f"A cena '{raw_title}' é uma rotina nativa do Aton e está protegida contra exclusão."
            ),
        }

    existing = get_custom_scene_from_db(slug, db_path=db_path)
    if not existing:
        return {
            "status": "not_found",
            "message": f"Não encontrei nenhuma rotina personalizada chamada '{raw_title}'.",
        }

    summary_pt = (
        f"Você confirma a exclusão permanente da rotina personalizada '{existing['title']}'? "
        "(Responda Sim em até 60 segundos para confirmar)."
    )
    proposal = get_scene_confirmation_manager().create_proposal(
        operation="delete_custom_scene",
        scene_slug=slug,
        scene_title=existing["title"],
        payload={"slug": slug, "title": existing["title"], "db_path": str(db_path)},
        summary_pt=summary_pt,
        session_id=session_id,
    )

    return {
        "status": "confirmation_required",
        "operation": "delete_custom_scene",
        "proposal_id": proposal.proposal_id,
        "scene": slug,
        "title": existing["title"],
        "expires_in_seconds": int(PROPOSAL_TTL_SECONDS),
        "message": summary_pt,
    }


def confirmar_rotina_personalizada(
    proposal_id: str,
    session_id: Optional[str] = None,
    db_path: Optional[Path] = None,
    step_timeout_seconds: float = DEFAULT_STEP_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
    """
    Confirm and execute a pending custom scene proposal (save, delete, or sensitive execution)
    bound to the current session within the 60-second TTL.
    """
    prop, code, err_msg = get_scene_confirmation_manager().consume_proposal(
        proposal_id=proposal_id,
        session_id=session_id,
    )
    if prop is None:
        return {
            "status": code,
            "message": err_msg,
        }

    target_db = db_path or Path(prop.payload.get("db_path", str(DEFAULT_DB_PATH)))

    if prop.operation == "create_custom_scene":
        saved = _save_custom_scene_to_db(
            slug=prop.payload["slug"],
            title=prop.payload["title"],
            description=prop.payload["description"],
            steps=prop.payload["steps"],
            db_path=target_db,
        )
        return {
            "status": "success",
            "operation": "create_custom_scene",
            "scene": saved.get("slug"),
            "custom_scene": saved,
            "message": (
                f"Rotina personalizada '{saved.get('title')}' confirmada e salva com sucesso no banco de dados "
                f"com {len(saved.get('steps', []))} etapa(s)."
            ),
        }

    if prop.operation == "delete_custom_scene":
        deleted = _delete_custom_scene_from_db(prop.scene_slug, db_path=target_db)
        if deleted:
            return {
                "status": "success",
                "operation": "delete_custom_scene",
                "scene": prop.scene_slug,
                "message": f"Rotina personalizada '{prop.scene_title}' excluída com sucesso.",
            }
        return {
            "status": "not_found",
            "message": f"A rotina '{prop.scene_title}' já não estava mais cadastrada.",
        }

    if prop.operation == "execute_sensitive_scene":
        return executar_cena(
            nome_cena=prop.scene_slug,
            db_path=target_db,
            step_timeout_seconds=step_timeout_seconds,
            _sensitive_confirmed=True,
        )

    if prop.operation == "create_scene_schedule":
        sched = _save_scene_schedule_to_db(
            schedule_id=prop.payload["schedule_id"],
            scene_slug=prop.payload["scene_slug"],
            scene_title=prop.payload["scene_title"],
            time_hhmm=prop.payload["time_hhmm"],
            days_of_week=prop.payload["days_of_week"],
            db_path=target_db,
        )
        return {
            "status": "success",
            "operation": "create_scene_schedule",
            "schedule": sched,
            "message": (
                f"Agendamento confirmado e salvo: a cena '{sched.get('scene_title')}' será executada "
                f"automaticamente às {sched.get('time_hhmm')} ({_format_days_pt(sched.get('days_of_week', 'all'))})."
            ),
        }

    if prop.operation == "delete_scene_schedule":
        deleted = _delete_scene_schedule_from_db(
            schedule_id=prop.payload["schedule_id"],
            db_path=target_db,
        )
        if deleted:
            return {
                "status": "success",
                "operation": "delete_scene_schedule",
                "schedule_id": prop.payload["schedule_id"],
                "message": (
                    f"Agendamento da cena '{prop.scene_title}' ({prop.payload.get('time_hhmm', '')}) "
                    "removido com sucesso."
                ),
            }
        return {
            "status": "not_found",
            "message": f"O agendamento da cena '{prop.scene_title}' já não estava mais cadastrado.",
        }

    return {"status": "error", "message": f"Operação de proposta desconhecida: {prop.operation}"}


# ---------------------------------------------------------------------------
# Public Voice Tools: executar_cena, restaurar_cena, listar_cenas
# ---------------------------------------------------------------------------


def restaurar_cena(
    db_path: Path = DEFAULT_DB_PATH,
    step_timeout_seconds: float = DEFAULT_STEP_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
    """
    Restore Windows volume and Proactive Calendar DND flags from the saved pre-scene
    snapshot in SQLite, without altering permanent quiet hours.
    """
    snapshot = get_saved_scene_snapshot(db_path=db_path)
    if not snapshot:
        return {
            "status": "error",
            "scene": "restaurar",
            "title": SCENE_CATALOG["restaurar"]["title"],
            "counts": {"total": 0, "confirmed": 0, "sent_unverified": 0, "failed": 0},
            "steps": [],
            "message": (
                "Não há nenhum estado anterior de Modo Cinema, Modo Foco, Boa Noite "
                "ou rotina personalizada salvo para restaurar no momento."
            ),
        }

    steps: List[SceneStepResult] = []

    def _restore_dnd() -> Tuple[str, str, Optional[Dict[str, Any]]]:
        from src.core.proactive_calendar import get_proactive_calendar_monitor
        from src.tools.proactive_tools import configurar_avisos_proativos

        target_mute = bool(snapshot["previous_dnd_mute_sound"])
        target_visual = bool(snapshot["previous_dnd_block_visual"])
        res = configurar_avisos_proativos(
            silenciar_som=target_mute,
            bloquear_notificacao_visual=target_visual,
        )
        monitor = get_proactive_calendar_monitor()
        readback = monitor.get_settings()
        if (
            isinstance(res, dict)
            and res.get("status") == "success"
            and bool(readback.dnd_mute_sound) == target_mute
            and bool(readback.dnd_block_visual) == target_visual
        ):
            estado_som = "silenciado" if target_mute else "ativo"
            return (
                "confirmed",
                f"avisos proativos da agenda restaurados (som {estado_som}, horário de silêncio permanente intacto)",
                {
                    "dnd_mute_sound": readback.dnd_mute_sound,
                    "dnd_block_visual": readback.dnd_block_visual,
                    "quiet_hours": f"{readback.quiet_start_hour:02d}:00-{readback.quiet_end_hour:02d}:00",
                },
            )
        return (
            "failed",
            "não foi possível confirmar a restauração dos avisos proativos da agenda",
            res if isinstance(res, dict) else None,
        )

    steps.append(
        _run_step_isolated(
            "restore_proactive_dnd",
            "Restaurar configuração de avisos proativos da agenda",
            _restore_dnd,
            timeout_seconds=step_timeout_seconds,
        )
    )

    prev_vol = snapshot.get("previous_volume_percent")
    prev_muted = snapshot.get("previous_is_muted")
    if prev_vol is not None or prev_muted is not None:
        def _restore_volume() -> Tuple[str, str, Optional[Dict[str, Any]]]:
            from src.tools.system_audio import set_system_volume

            res = set_system_volume(level=prev_vol, mute=prev_muted)
            if not isinstance(res, dict) or res.get("status") != "success":
                return (
                    "failed",
                    "não foi possível restaurar o volume anterior do Windows",
                    res if isinstance(res, dict) else None,
                )
            actual_vol = res.get("volume_percent")
            if prev_vol is None or (
                actual_vol is not None and abs(int(actual_vol) - int(prev_vol)) <= 2
            ):
                return (
                    "confirmed",
                    f"volume do Windows restaurado e confirmado em {actual_vol}%",
                    {"volume_percent": actual_vol, "is_muted": res.get("is_muted")},
                )
            return (
                "sent_unverified",
                f"comando para restaurar volume ({prev_vol}%) enviado, leitura atual em {actual_vol}%",
                {"volume_percent": actual_vol},
            )

        steps.append(
            _run_step_isolated(
                "restore_windows_volume",
                "Restaurar volume anterior do Windows",
                _restore_volume,
                timeout_seconds=step_timeout_seconds,
            )
        )

    if all(s.verification_level == "confirmed" for s in steps):
        _clear_scene_snapshot(db_path=db_path)

    return _build_scene_report(
        scene_name="restaurar",
        scene_title=SCENE_CATALOG["restaurar"]["title"],
        steps=steps,
        snapshot=snapshot,
    )


def executar_cena(
    nome_cena: str,
    duracao_foco_minutos: int = 45,
    app_tv: str = "youtube",
    volume_cinema: int = 20,
    db_path: Path = DEFAULT_DB_PATH,
    step_timeout_seconds: float = DEFAULT_STEP_TIMEOUT_SECONDS,
    session_id: Optional[str] = None,
    _sensitive_confirmed: bool = False,
) -> Dict[str, Any]:
    """
    Execute a coordinated native or custom multi-module scene with independent fault
    isolation, per-step timeout, anti-duplication guard, state snapshot preservation,
    sensitive-action confirmation gate, and 3-level outcome verification.
    """
    canonical = _normalize_scene_name(nome_cena)
    custom_scene: Optional[Dict[str, Any]] = None
    if not canonical:
        custom_scene = get_custom_scene_from_db(nome_cena, db_path=db_path)
        if custom_scene:
            canonical = custom_scene["slug"]

    if not canonical:
        custom_names = [c["slug"] for c in list_custom_scenes_from_db(db_path=db_path)]
        all_avail = sorted(list(SCENE_CATALOG.keys()) + custom_names)
        return {
            "status": "error",
            "message": (
                f"Cena '{_sanitize_text(nome_cena)}' não reconhecida. "
                f"As cenas disponíveis são: {', '.join(all_avail)}."
            ),
        }

    if canonical == "restaurar":
        return restaurar_cena(db_path=db_path, step_timeout_seconds=step_timeout_seconds)

    # Requirement 3: Sensitive actions in custom scenes require specific confirmation before execution
    if custom_scene and custom_scene.get("has_sensitive_actions") and not _sensitive_confirmed:
        sensitive_steps = [
            describe_custom_step(s)
            for s in custom_scene.get("steps", [])
            if ALLOWED_CUSTOM_STEP_TYPES.get(s.get("acao", ""), {}).get("is_sensitive", False)
        ]
        summary_pt = (
            f"A rotina personalizada '{custom_scene['title']}' contém ação sensível "
            f"({'; '.join(sensitive_steps)}), com risco de perda de documentos não salvos. "
            "Você confirma a execução desta rotina agora? (Responda Sim em até 60 segundos)."
        )
        prop = get_scene_confirmation_manager().create_proposal(
            operation="execute_sensitive_scene",
            scene_slug=canonical,
            scene_title=custom_scene["title"],
            payload={"slug": canonical, "db_path": str(db_path)},
            summary_pt=summary_pt,
            session_id=session_id,
        )
        return {
            "status": "confirmation_required",
            "operation": "execute_sensitive_scene",
            "proposal_id": prop.proposal_id,
            "scene": canonical,
            "title": custom_scene["title"],
            "sensitive_steps": sensitive_steps,
            "expires_in_seconds": int(PROPOSAL_TTL_SECONDS),
            "message": summary_pt,
        }

    now_mono = time.monotonic()
    with _scene_guard_lock:
        if canonical in _active_scenes:
            return {
                "status": "duplicate_blocked",
                "scene": canonical,
                "message": f"A cena '{canonical}' já está em execução neste momento. Aguarde a conclusão.",
            }
        last_finished = _last_scene_finished_at.get(canonical)
        if last_finished is not None and (now_mono - last_finished) < SCENE_DEDUP_COOLDOWN_SECONDS:
            return {
                "status": "duplicate_blocked",
                "scene": canonical,
                "message": (
                    f"A cena '{canonical}' acabou de ser executada há menos de "
                    f"{int(SCENE_DEDUP_COOLDOWN_SECONDS)} segundos. Comando duplicado ignorado por segurança."
                ),
            }
        _active_scenes.add(canonical)

    try:
        meta = custom_scene if custom_scene is not None else SCENE_CATALOG[canonical]
        snapshot: Optional[Dict[str, Any]] = None
        if meta.get("modifies_state"):
            snapshot = save_pre_scene_snapshot(canonical, db_path=db_path)

        steps: List[SceneStepResult] = []

        if custom_scene is not None:
            steps = _execute_custom_step_list(
                custom_steps=custom_scene.get("steps", []),
                step_timeout_seconds=step_timeout_seconds,
                db_path=db_path,
            )

        elif canonical == "bom_dia":
            steps.append(
                _run_step_isolated(
                    "calendar_today",
                    "Consultar compromissos de hoje no Google Agenda",
                    lambda: _step_calendar_events("today", "hoje"),
                    timeout_seconds=step_timeout_seconds,
                )
            )
            steps.append(
                _run_step_isolated(
                    "tasks_pending",
                    "Consultar tarefas pendentes no Google Tasks",
                    _step_pending_tasks,
                    timeout_seconds=step_timeout_seconds,
                )
            )
            steps.append(
                _run_step_isolated(
                    "gmail_unread",
                    "Consultar e-mails não lidos no Gmail",
                    _step_unread_emails,
                    timeout_seconds=step_timeout_seconds,
                )
            )
            steps.append(
                _run_step_isolated(
                    "windows_telemetry",
                    "Verificar telemetria e bateria do Windows",
                    _step_system_telemetry,
                    timeout_seconds=step_timeout_seconds,
                )
            )

        elif canonical == "modo_cinema":
            target_vol = max(0, min(100, int(volume_cinema)))
            target_app = (app_tv or "youtube").strip().lower()
            steps.append(
                _run_step_isolated(
                    "proactive_dnd_sound",
                    "Silenciar som dos avisos proativos da agenda",
                    _step_mute_proactive_sound,
                    timeout_seconds=step_timeout_seconds,
                )
            )
            steps.append(
                _run_step_isolated(
                    "windows_volume_cinema",
                    f"Ajustar volume do Windows para {target_vol}%",
                    lambda: _step_set_windows_volume(target_vol),
                    timeout_seconds=step_timeout_seconds,
                )
            )
            steps.append(
                _run_step_isolated(
                    "fire_tv_app",
                    f"Abrir {target_app.capitalize()} no Fire TV Stick",
                    lambda: _step_launch_fire_tv_app(target_app),
                    timeout_seconds=step_timeout_seconds,
                )
            )

        elif canonical == "modo_foco":
            focus_mins = max(1, min(480, int(duracao_foco_minutos or 45)))
            steps.append(
                _run_step_isolated(
                    "proactive_dnd_sound",
                    "Silenciar som dos avisos proativos da agenda",
                    _step_mute_proactive_sound,
                    timeout_seconds=step_timeout_seconds,
                )
            )
            steps.append(
                _run_step_isolated(
                    "windows_media_stop",
                    "Pausar reprodução de mídia no Windows",
                    _step_pause_windows_media,
                    timeout_seconds=step_timeout_seconds,
                )
            )
            steps.append(
                _run_step_isolated(
                    "focus_timer",
                    f"Criar timer persistente de foco ({focus_mins} minutos)",
                    lambda: _step_create_persistent_timer(focus_mins, db_path=db_path),
                    timeout_seconds=step_timeout_seconds,
                )
            )

        elif canonical == "boa_noite":
            steps.append(
                _run_step_isolated(
                    "proactive_dnd_sound",
                    "Silenciar som dos avisos proativos da agenda",
                    _step_mute_proactive_sound,
                    timeout_seconds=step_timeout_seconds,
                )
            )
            steps.append(
                _run_step_isolated(
                    "windows_media_stop",
                    "Parar reprodução de mídia no Windows",
                    _step_pause_windows_media,
                    timeout_seconds=step_timeout_seconds,
                )
            )
            steps.append(
                _run_step_isolated(
                    "calendar_tomorrow",
                    "Consultar compromissos de amanhã no Google Agenda",
                    lambda: _step_calendar_events("tomorrow", "amanhã"),
                    timeout_seconds=step_timeout_seconds,
                )
            )

        return _build_scene_report(
            scene_name=canonical,
            scene_title=meta["title"],
            steps=steps,
            snapshot=snapshot,
        )
    finally:
        with _scene_guard_lock:
            _active_scenes.discard(canonical)
            _last_scene_finished_at[canonical] = time.monotonic()


def listar_cenas(db_path: Path = DEFAULT_DB_PATH) -> Dict[str, Any]:
    """Return all available native and custom scenes and whether a snapshot is ready to restore."""
    snapshot = get_saved_scene_snapshot(db_path=db_path)
    native_list = [
        {
            "name": k,
            "title": v["title"],
            "description": v["description"],
            "modifies_state": v["modifies_state"],
            "is_native": True,
        }
        for k, v in SCENE_CATALOG.items()
    ]
    custom_list = list_custom_scenes_from_db(db_path=db_path)
    scenes_list = native_list + custom_list

    names_spoken = ", ".join(s["title"] for s in scenes_list)
    snap_msg = (
        f" Há um estado salvo da cena '{snapshot['scene_name']}' pronto para restaurar."
        if snapshot
        else ""
    )
    return {
        "status": "success",
        "scenes": scenes_list,
        "native_count": len(native_list),
        "custom_count": len(custom_list),
        "has_saved_snapshot": snapshot is not None,
        "saved_snapshot": snapshot,
        "message": f"Cenas disponíveis no Aton: {names_spoken}.{snap_msg}",
    }


# ---------------------------------------------------------------------------
# Scheduled Routines & Automatic Time-Based Scene Execution
# ---------------------------------------------------------------------------

SCHEDULE_WINDOW_MINUTES = 15

_DAY_TOKEN_MAP: Dict[str, str] = {
    "mon": "mon",
    "seg": "mon",
    "segunda": "mon",
    "segunda-feira": "mon",
    "tue": "tue",
    "ter": "tue",
    "terca": "tue",
    "terça": "tue",
    "terca-feira": "tue",
    "wed": "wed",
    "qua": "wed",
    "quarta": "wed",
    "quarta-feira": "wed",
    "thu": "thu",
    "qui": "thu",
    "quinta": "thu",
    "quinta-feira": "thu",
    "fri": "fri",
    "sex": "fri",
    "sexta": "fri",
    "sexta-feira": "fri",
    "sat": "sat",
    "sab": "sat",
    "sábado": "sat",
    "sabado": "sat",
    "sun": "sun",
    "dom": "sun",
    "domingo": "sun",
}

_DAY_NAMES_PT: Dict[str, str] = {
    "mon": "segunda",
    "tue": "terça",
    "wed": "quarta",
    "thu": "quinta",
    "fri": "sexta",
    "sat": "sábado",
    "sun": "domingo",
}

_WEEKDAY_INDEX_TO_CODE: Tuple[str, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _normalize_schedule_time_hhmm(raw_time: str) -> Optional[str]:
    """Validate and normalize a time string into strict 24-hour 'HH:MM' format."""
    cleaned = str(raw_time or "").strip().lower().replace("h", ":")
    if cleaned.endswith(":"):
        cleaned += "00"
    m = re.match(r"^(\d{1,2}):(\d{2})$", cleaned)
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return f"{hour:02d}:{minute:02d}"


def _normalize_schedule_days(raw_days: Optional[str]) -> Optional[str]:
    """Normalize spoken/written days of week into canonical comma-separated codes or 'all'."""
    cleaned = _slugify_scene_name(raw_days or "segunda_a_sexta")
    if cleaned in ("all", "todos", "todos_os_dias", "diario", "diariamente", "todo_dia"):
        return "all"
    if cleaned in ("segunda_a_sexta", "dias_uteis", "uteis", "weekdays", "mon_tue_wed_thu_fri"):
        return "mon,tue,wed,thu,fri"
    if cleaned in ("fim_de_semana", "final_de_semana", "weekend", "sat_sun"):
        return "sat,sun"

    tokens = [t.strip() for t in re.split(r"[,_\s]+", str(raw_days or "").strip().lower()) if t.strip()]
    resolved: List[str] = []
    for tok in tokens:
        code = _DAY_TOKEN_MAP.get(tok)
        if not code:
            return None
        if code not in resolved:
            resolved.append(code)
    if not resolved:
        return None
    if len(resolved) == 7:
        return "all"
    return ",".join(resolved)


def _format_days_pt(days_code: str) -> str:
    if days_code == "all":
        return "todos os dias"
    if days_code == "mon,tue,wed,thu,fri":
        return "de segunda a sexta"
    if days_code == "sat,sun":
        return "aos sábados e domingos"
    parts = [_DAY_NAMES_PT.get(c, c) for c in days_code.split(",") if c]
    return ", ".join(parts)


def _save_scene_schedule_to_db(
    schedule_id: str,
    scene_slug: str,
    scene_title: str,
    time_hhmm: str,
    days_of_week: str,
    db_path: Path = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    _ensure_scene_tables(db_path)
    now_iso = datetime.now().astimezone().isoformat()
    with sqlite3.connect(str(db_path), timeout=5.0) as conn:
        with conn:
            conn.execute(
                """
                INSERT INTO scheduled_scenes (
                    schedule_id, scene_slug, scene_title, time_hhmm,
                    days_of_week, enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(schedule_id) DO UPDATE SET
                    scene_slug = excluded.scene_slug,
                    scene_title = excluded.scene_title,
                    time_hhmm = excluded.time_hhmm,
                    days_of_week = excluded.days_of_week,
                    enabled = 1,
                    updated_at = excluded.updated_at
                """,
                (
                    schedule_id,
                    scene_slug,
                    scene_title,
                    time_hhmm,
                    days_of_week,
                    now_iso,
                    now_iso,
                ),
            )
    schedules = list_scene_schedules_from_db(db_path=db_path)
    for s in schedules:
        if s["schedule_id"] == schedule_id:
            return s
    return {}


def list_scene_schedules_from_db(db_path: Path = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    _ensure_scene_tables(db_path)
    with sqlite3.connect(str(db_path), timeout=5.0) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM scheduled_scenes ORDER BY time_hhmm ASC, scene_slug ASC"
        ).fetchall()
    out: List[Dict[str, Any]] = []
    for row in rows:
        days_code = str(row["days_of_week"])
        out.append(
            {
                "schedule_id": str(row["schedule_id"]),
                "scene_slug": str(row["scene_slug"]),
                "scene_title": str(row["scene_title"]),
                "time_hhmm": str(row["time_hhmm"]),
                "days_of_week": days_code,
                "days_spoken": _format_days_pt(days_code),
                "enabled": bool(row["enabled"]),
                "last_triggered_date": row["last_triggered_date"],
                "last_result_summary": row["last_result_summary"],
            }
        )
    return out


def _delete_scene_schedule_from_db(schedule_id: str, db_path: Path = DEFAULT_DB_PATH) -> bool:
    _ensure_scene_tables(db_path)
    with sqlite3.connect(str(db_path), timeout=5.0) as conn:
        with conn:
            cur = conn.execute(
                "DELETE FROM scheduled_scenes WHERE schedule_id = ?",
                (schedule_id,),
            )
            return cur.rowcount > 0


def propor_agendamento_cena(
    nome_cena: str,
    horario_hhmm: str,
    dias_semana: str = "segunda_a_sexta",
    session_id: Optional[str] = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    """
    Validate and propose a recurring time-based schedule for a native or custom scene.
    Blocks routines with sensitive actions (`fechar_app_pc`) from unattended execution
    and requires two-phase confirmation via `confirmar_rotina_personalizada`.
    """
    canonical = _normalize_scene_name(nome_cena)
    custom_scene: Optional[Dict[str, Any]] = None
    if not canonical:
        custom_scene = get_custom_scene_from_db(nome_cena, db_path=db_path)
        if custom_scene:
            canonical = custom_scene["slug"]

    if not canonical:
        return {
            "status": "not_found",
            "message": f"A cena '{_sanitize_text(nome_cena)}' não foi encontrada para agendamento.",
        }

    if canonical == "restaurar":
        return {
            "status": "invalid_scene",
            "message": "A ação 'restaurar' serve para reverter o estado anterior sob demanda e não pode ser agendada.",
        }

    if custom_scene and custom_scene.get("has_sensitive_actions"):
        return {
            "status": "sensitive_scene_blocked",
            "message": (
                f"Por segurança, a rotina personalizada '{custom_scene['title']}' não pode ser agendada "
                "para execução automática sem supervisão porque contém ação sensível (fechamento de aplicativo "
                "com risco de perda de documentos não salvos)."
            ),
        }

    norm_time = _normalize_schedule_time_hhmm(horario_hhmm)
    if not norm_time:
        return {
            "status": "invalid_time",
            "message": (
                f"Horário '{_sanitize_text(horario_hhmm)}' inválido. Informe no formato 24h HH:MM (ex.: '08:00' ou '18:30')."
            ),
        }

    norm_days = _normalize_schedule_days(dias_semana)
    if not norm_days:
        return {
            "status": "invalid_days",
            "message": (
                f"Dias da semana '{_sanitize_text(dias_semana)}' não reconhecidos. Use 'segunda_a_sexta', "
                "'todos_os_dias', 'fim_de_semana' ou dias separados por vírgula (ex.: 'seg,qua,sex')."
            ),
        }

    scene_title = custom_scene["title"] if custom_scene else SCENE_CATALOG[canonical]["title"]
    schedule_id = f"sched_{canonical}_{norm_time.replace(':', '')}"
    days_pt = _format_days_pt(norm_days)

    summary_pt = (
        f"Proposta para agendar a cena '{scene_title}' automaticamente às {norm_time} ({days_pt}). "
        "Você confirma este agendamento? (Responda Sim em até 60 segundos)."
    )

    prop = get_scene_confirmation_manager().create_proposal(
        operation="create_scene_schedule",
        scene_slug=canonical,
        scene_title=scene_title,
        payload={
            "schedule_id": schedule_id,
            "scene_slug": canonical,
            "scene_title": scene_title,
            "time_hhmm": norm_time,
            "days_of_week": norm_days,
            "db_path": str(db_path),
        },
        summary_pt=summary_pt,
        session_id=session_id,
    )

    return {
        "status": "confirmation_required",
        "operation": "create_scene_schedule",
        "proposal_id": prop.proposal_id,
        "schedule_id": schedule_id,
        "scene": canonical,
        "title": scene_title,
        "time_hhmm": norm_time,
        "days_of_week": norm_days,
        "days_spoken": days_pt,
        "expires_in_seconds": int(PROPOSAL_TTL_SECONDS),
        "message": summary_pt,
    }


def listar_agendamentos_cenas(db_path: Path = DEFAULT_DB_PATH) -> Dict[str, Any]:
    """List all scheduled routines and their last execution status."""
    schedules = list_scene_schedules_from_db(db_path=db_path)
    if not schedules:
        return {
            "status": "success",
            "schedules": [],
            "count": 0,
            "message": "Não há nenhuma rotina ou cena agendada por horário no momento.",
        }

    spoken_items = [
        f"'{s['scene_title']}' às {s['time_hhmm']} ({s['days_spoken']})"
        for s in schedules
    ]
    return {
        "status": "success",
        "schedules": schedules,
        "count": len(schedules),
        "message": f"Há {len(schedules)} agendamento(s) ativo(s): {'; '.join(spoken_items)}.",
    }


def remover_agendamento_cena(
    identificador_ou_cena: str,
    session_id: Optional[str] = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    """Create a 60-second confirmation proposal to delete a scheduled scene."""
    q = str(identificador_ou_cena or "").strip().lower()
    slug_q = _slugify_scene_name(q)
    canonical_q = _normalize_scene_name(q) or slug_q

    schedules = list_scene_schedules_from_db(db_path=db_path)
    matches = [
        s for s in schedules
        if s["schedule_id"].lower() == q
        or s["scene_slug"].lower() == canonical_q
        or _slugify_scene_name(s["scene_title"]) == slug_q
    ]
    if not matches:
        return {
            "status": "not_found",
            "message": f"Nenhum agendamento encontrado para '{_sanitize_text(identificador_ou_cena)}'.",
        }

    target = matches[0]
    summary_pt = (
        f"Você confirma a remoção do agendamento da cena '{target['scene_title']}' às {target['time_hhmm']} "
        f"({target['days_spoken']})? (Responda Sim em até 60 segundos)."
    )
    prop = get_scene_confirmation_manager().create_proposal(
        operation="delete_scene_schedule",
        scene_slug=target["scene_slug"],
        scene_title=target["scene_title"],
        payload={
            "schedule_id": target["schedule_id"],
            "time_hhmm": target["time_hhmm"],
            "db_path": str(db_path),
        },
        summary_pt=summary_pt,
        session_id=session_id,
    )
    return {
        "status": "confirmation_required",
        "operation": "delete_scene_schedule",
        "proposal_id": prop.proposal_id,
        "schedule_id": target["schedule_id"],
        "scene": target["scene_slug"],
        "title": target["scene_title"],
        "expires_in_seconds": int(PROPOSAL_TTL_SECONDS),
        "message": summary_pt,
    }


def evaluate_due_scheduled_scenes(
    now_dt: Optional[datetime] = None,
    is_voice_session_busy: bool = False,
    db_path: Path = DEFAULT_DB_PATH,
    step_timeout_seconds: float = DEFAULT_STEP_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
    """
    Evaluate all enabled scheduled scenes against the current time (`America/Fortaleza`).
    Enforces:
    - Do not interrupt an active voice session (`is_voice_session_busy=True` defers execution);
    - Do not execute during permanent quiet hours (`23:00–07:00`) or when `dnd_mute_sound` is True
      if the scene would produce sound or raise volume;
    - Only trigger within the 15-minute window (`0 <= minutes_elapsed <= 15`) after `time_hhmm`;
    - If `minutes_elapsed > 15` and `last_triggered_date != today`, mark `last_triggered_date = today`
      as skipped so a PC turned on hours later never fires a stale morning routine;
    - Record `last_triggered_date` in SQLite immediately so restarting Aton never triggers twice.
    """
    if is_voice_session_busy:
        return {"status": "deferred_busy", "executed": [], "skipped": []}

    current_dt = now_dt or datetime.now().astimezone()
    today_str = current_dt.strftime("%Y-%m-%d")
    weekday_code = _WEEKDAY_INDEX_TO_CODE[current_dt.weekday()]
    current_minutes = current_dt.hour * 60 + current_dt.minute

    from src.core.proactive_calendar import get_proactive_calendar_monitor

    monitor = get_proactive_calendar_monitor()
    proactive_cfg = monitor.get_settings()
    in_quiet_hours = monitor.is_in_quiet_hours(
        current_dt,
        proactive_cfg.quiet_start_hour,
        proactive_cfg.quiet_end_hour,
    )

    schedules = list_scene_schedules_from_db(db_path=db_path)
    executed_reports: List[Dict[str, Any]] = []
    skipped_reports: List[Dict[str, Any]] = []

    for sched in schedules:
        if not sched.get("enabled", True):
            continue
        if sched.get("last_triggered_date") == today_str:
            continue

        days_code = str(sched.get("days_of_week", "all"))
        if days_code != "all" and weekday_code not in days_code.split(","):
            continue

        hh, mm = [int(x) for x in str(sched["time_hhmm"]).split(":")]
        sched_minutes = hh * 60 + mm
        elapsed_minutes = current_minutes - sched_minutes

        if elapsed_minutes < 0:
            # Not due yet today
            continue

        sched_id = sched["schedule_id"]
        scene_slug = sched["scene_slug"]

        if elapsed_minutes > SCHEDULE_WINDOW_MINUTES:
            # Stale schedule (e.g. PC was off at 08:00 and booted at 14:00): mark skipped for today
            summary = (
                f"Ignorado em {today_str}: horário agendado ({sched['time_hhmm']}) ultrapassou a "
                f"janela de {SCHEDULE_WINDOW_MINUTES} minutos."
            )
            with sqlite3.connect(str(db_path), timeout=5.0) as conn:
                with conn:
                    conn.execute(
                        """
                        UPDATE scheduled_scenes
                        SET last_triggered_date = ?, last_result_summary = ?, updated_at = ?
                        WHERE schedule_id = ?
                        """,
                        (today_str, summary, current_dt.isoformat(), sched_id),
                    )
            skipped_reports.append({"schedule_id": sched_id, "scene": scene_slug, "reason": "window_expired"})
            continue

        if in_quiet_hours or proactive_cfg.dnd_mute_sound:
            summary = (
                f"Adiamento/silêncio em {today_str}: horário de silêncio ou modo Não Perturbe ativo no momento do disparo ({sched['time_hhmm']})."
            )
            with sqlite3.connect(str(db_path), timeout=5.0) as conn:
                with conn:
                    conn.execute(
                        """
                        UPDATE scheduled_scenes
                        SET last_triggered_date = ?, last_result_summary = ?, updated_at = ?
                        WHERE schedule_id = ?
                        """,
                        (today_str, summary, current_dt.isoformat(), sched_id),
                    )
            skipped_reports.append({"schedule_id": sched_id, "scene": scene_slug, "reason": "quiet_or_dnd"})
            continue

        # Mark triggered date BEFORE running to guarantee at-most-once execution per day
        with sqlite3.connect(str(db_path), timeout=5.0) as conn:
            with conn:
                conn.execute(
                    """
                    UPDATE scheduled_scenes
                    SET last_triggered_date = ?, updated_at = ?
                    WHERE schedule_id = ?
                    """,
                    (today_str, current_dt.isoformat(), sched_id),
                )

        res = executar_cena(
            nome_cena=scene_slug,
            db_path=db_path,
            step_timeout_seconds=step_timeout_seconds,
        )
        summary_msg = _sanitize_text(res.get("message", ""))
        with sqlite3.connect(str(db_path), timeout=5.0) as conn:
            with conn:
                conn.execute(
                    """
                    UPDATE scheduled_scenes
                    SET last_result_summary = ?, updated_at = ?
                    WHERE schedule_id = ?
                    """,
                    (summary_msg, current_dt.isoformat(), sched_id),
                )
        executed_reports.append(
            {
                "schedule_id": sched_id,
                "scene": scene_slug,
                "status": res.get("status"),
                "message": summary_msg,
            }
        )

    return {
        "status": "ok",
        "executed": executed_reports,
        "skipped": skipped_reports,
    }


SCENES_FUNCTION_DECLARATIONS: List[Dict[str, Any]] = [
    {
        "name": "executar_cena",
        "description": (
            "Executa uma rotina ou cena coordenada multi-módulo do Aton (nativa ou personalizada) com "
            "verificação real por etapa (confirmado, comando enviado sem confirmação ou falha) e isolamento "
            "de falhas entre dispositivos. Cenas nativas: 'bom_dia', 'modo_cinema', 'modo_foco', "
            "'boa_noite' e 'restaurar', além de qualquer rotina personalizada salva pelo usuário. "
            "Se a rotina personalizada contiver ação sensível (como fechar aplicativo), solicita confirmação antes de executar."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "nome_cena": {
                    "type": "STRING",
                    "description": (
                        "Nome da cena nativa ('bom_dia', 'modo_cinema', 'modo_foco', 'boa_noite', 'restaurar') "
                        "ou nome da rotina personalizada salva."
                    ),
                },
                "duracao_foco_minutos": {
                    "type": "INTEGER",
                    "description": "Duração em minutos para o timer do Modo Foco (padrão: 45).",
                },
                "app_tv": {
                    "type": "STRING",
                    "description": "Aplicativo a abrir no Fire TV durante o Modo Cinema (padrão: 'youtube').",
                },
                "volume_cinema": {
                    "type": "INTEGER",
                    "description": "Volume percentual do Windows no Modo Cinema (padrão: 20).",
                },
            },
            "required": ["nome_cena"],
        },
    },
    {
        "name": "restaurar_cena",
        "description": (
            "Restaura o volume anterior do Windows e o estado anterior dos avisos proativos da agenda "
            "que foram salvos antes de ativar o Modo Cinema, Modo Foco, Boa Noite ou uma rotina personalizada, "
            "sem alterar o horário de silêncio permanente."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "listar_cenas",
        "description": (
            "Lista as rotinas e cenas multi-módulo disponíveis no Aton (tanto nativas quanto personalizadas) "
            "e informa se existe um estado anterior salvo para restauração."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "propor_cena_personalizada",
        "description": (
            "Propõe a criação ou atualização de uma rotina personalizada por voz, validando as etapas contra "
            "o catálogo autorizado e gerando um 'proposal_id' com validade de 60 segundos. "
            "NUNCA salva sem confirmação: após chamar esta ferramenta, leia as etapas para o usuário e peça "
            "para ele responder 'Sim', chamando em seguida 'confirmar_rotina_personalizada'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "nome_cena": {
                    "type": "STRING",
                    "description": "Nome falado da nova rotina personalizada (ex.: 'Modo Estudo', 'Hora da Leitura'). Não pode usar nomes das 5 cenas nativas.",
                },
                "descricao": {
                    "type": "STRING",
                    "description": "Descrição curta opcional do objetivo da rotina.",
                },
                "etapas": {
                    "type": "ARRAY",
                    "description": (
                        "Lista ordenada de etapas autorizadas. Cada item deve ter 'acao' escolhida estritamente entre: "
                        "'silenciar_avisos', 'ativar_avisos', 'ajustar_volume_pc' (requer 'nivel' 0-100), "
                        "'pausar_midia_pc', 'abrir_app_pc' (requer 'aplicativo' autorizado como 'notepad', 'calculator', 'chrome', 'edge', 'vscode', 'spotify'), "
                        "'fechar_app_pc' (ação sensível: requer 'aplicativo' autorizado, exceto explorer), "
                        "'abrir_app_fire_tv' (requer 'aplicativo' como 'youtube', 'netflix', 'prime_video'), "
                        "'criar_timer' (requer 'minutos' 1-720 e 'titulo' opcional), 'consultar_agenda_hoje', "
                        "'consultar_agenda_amanha', 'consultar_tarefas', 'consultar_emails', 'consultar_telemetria_pc' ou 'consultar_canal_youtube'."
                    ),
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "acao": {"type": "STRING", "description": "Identificador da ação do catálogo autorizado."},
                            "nivel": {"type": "INTEGER", "description": "Volume percentual (0 a 100) para 'ajustar_volume_pc'."},
                            "aplicativo": {"type": "STRING", "description": "Identificador autorizado do app para 'abrir_app_pc', 'fechar_app_pc' ou 'abrir_app_fire_tv'."},
                            "minutos": {"type": "INTEGER", "description": "Duração em minutos (1 a 720) para 'criar_timer'."},
                            "titulo": {"type": "STRING", "description": "Título curto opcional para 'criar_timer'."},
                        },
                        "required": ["acao"],
                    },
                },
            },
            "required": ["nome_cena", "etapas"],
        },
    },
    {
        "name": "confirmar_rotina_personalizada",
        "description": (
            "Confirma e efetiva uma proposta pendente de rotina personalizada (criação, exclusão ou execução "
            "de rotina com ação sensível) usando o 'proposal_id' gerado nos últimos 60 segundos. "
            "Chame somente após o usuário responder 'Sim' explicitamente."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "proposal_id": {
                    "type": "STRING",
                    "description": "ID exato da proposta pendente retornado por propor_cena_personalizada, remover_cena_personalizada ou executar_cena.",
                },
            },
            "required": ["proposal_id"],
        },
    },
    {
        "name": "remover_cena_personalizada",
        "description": (
            "Solicita a exclusão de uma rotina personalizada criada pelo usuário, gerando um 'proposal_id' "
            "que exige confirmação verbal ('Sim') via 'confirmar_rotina_personalizada'. Cenas nativas são protegidas."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "nome_cena": {
                    "type": "STRING",
                    "description": "Nome da rotina personalizada que o usuário deseja excluir.",
                },
            },
            "required": ["nome_cena"],
        },
    },
    {
        "name": "propor_agendamento_cena",
        "description": (
            "Propõe agendar uma cena nativa ou rotina personalizada para executar automaticamente em um horário "
            "(HH:MM) e dias da semana específicos, gerando um 'proposal_id' com validade de 60 segundos para "
            "confirmação via 'confirmar_rotina_personalizada'. Bloqueia rotinas com ações sensíveis."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "nome_cena": {
                    "type": "STRING",
                    "description": "Nome da cena nativa ('bom_dia', 'modo_foco', 'boa_noite') ou rotina personalizada.",
                },
                "horario_hhmm": {
                    "type": "STRING",
                    "description": "Horário no formato 24h HH:MM (ex.: '08:00', '18:30').",
                },
                "dias_semana": {
                    "type": "STRING",
                    "description": (
                        "Dias da semana: 'segunda_a_sexta', 'todos_os_dias', 'fim_de_semana' ou dias separados por vírgula (ex.: 'seg,qua,sex')."
                    ),
                },
            },
            "required": ["nome_cena", "horario_hhmm"],
        },
    },
    {
        "name": "listar_agendamentos_cenas",
        "description": (
            "Lista todas as rotinas e cenas agendadas por horário no Aton, informando dias da semana e o "
            "resultado da última execução automática."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "remover_agendamento_cena",
        "description": (
            "Solicita a exclusão de um agendamento automático de cena por horário, gerando um 'proposal_id' "
            "que exige confirmação verbal ('Sim') via 'confirmar_rotina_personalizada'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "identificador_ou_cena": {
                    "type": "STRING",
                    "description": "Nome da cena agendada ou ID do agendamento que deseja remover.",
                },
            },
            "required": ["identificador_ou_cena"],
        },
    },
]

SCENE_TOOL_NAMES = {entry["name"] for entry in SCENES_FUNCTION_DECLARATIONS}


def dispatch_scene_tool(tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatch voice tool calls for Multi-Module Verified Scenes, Custom Routines, and Schedules."""
    if tool_name == "executar_cena":
        return executar_cena(
            nome_cena=str(tool_args.get("nome_cena") or ""),
            duracao_foco_minutos=int(tool_args.get("duracao_foco_minutos") or 45),
            app_tv=str(tool_args.get("app_tv") or "youtube"),
            volume_cinema=int(tool_args.get("volume_cinema") if tool_args.get("volume_cinema") is not None else 20),
        )
    if tool_name == "restaurar_cena":
        return restaurar_cena()
    if tool_name == "listar_cenas":
        return listar_cenas()
    if tool_name == "propor_cena_personalizada":
        return propor_cena_personalizada(
            nome_cena=str(tool_args.get("nome_cena") or ""),
            etapas=list(tool_args.get("etapas") or []),
            descricao=tool_args.get("descricao"),
        )
    if tool_name == "confirmar_rotina_personalizada":
        return confirmar_rotina_personalizada(
            proposal_id=str(tool_args.get("proposal_id") or ""),
        )
    if tool_name == "remover_cena_personalizada":
        return remover_cena_personalizada(
            nome_cena=str(tool_args.get("nome_cena") or ""),
        )
    if tool_name == "propor_agendamento_cena":
        return propor_agendamento_cena(
            nome_cena=str(tool_args.get("nome_cena") or ""),
            horario_hhmm=str(tool_args.get("horario_hhmm") or ""),
            dias_semana=str(tool_args.get("dias_semana") or "segunda_a_sexta"),
        )
    if tool_name == "listar_agendamentos_cenas":
        return listar_agendamentos_cenas()
    if tool_name == "remover_agendamento_cena":
        return remover_agendamento_cena(
            identificador_ou_cena=str(tool_args.get("identificador_ou_cena") or ""),
        )
    return {"status": "error", "message": f"Ferramenta de cena desconhecida: {tool_name}"}
