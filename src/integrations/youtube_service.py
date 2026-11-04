"""YouTube Data API v3 & YouTube Analytics API v2 Multi-Account / Multi-Channel Service for Aton.

Provides:
- Separate OAuth 2.0 Desktop token storage per (account_email, channel_id) pair using 64-char SHA-256 filenames.
- Complete isolation from Gmail tokens and index.
- Real channel discovery via channels.list(mine=True) without assuming automatic Brand Account discovery.
- Explicit check for target channel UCYCmXtIR-tbWCyrwbLdczyA (authorized vs public metadata only).
- Separate 'readonly' and 'manage' OAuth scope profiles with atomic replacement and safe mode switching.
- Granular error classification distinguishing YouTube Data API v3 vs YouTube Analytics API v2, quota limits, and scope errors.
- Fail-closed, server-side two-phase confirmation state machine (YouTubeConfirmationManager) for all write/delete operations.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import logging
import os
from pathlib import Path
import secrets
import time
from typing import Any, Dict, List, Optional, Tuple
import urllib.error
import urllib.parse
import urllib.request

from src.config import settings
from src.integrations.gmail_service import (
    _atomic_write_text,
    _extract_scopes_from_token_json,
    validate_client_credentials_file,
)

logger = logging.getLogger(__name__)

# Target channel explicitly requested by the user for verification
KNOWN_TARGET_CHANNEL_IDS: List[str] = [
    "UCYCmXtIR-tbWCyrwbLdczyA",
]

# Minimal Read-Only Scopes Profile
YOUTUBE_READONLY_SCOPES: List[str] = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
]

# Minimal Manage & Publish Scopes Profile (no redundant 'youtube' scope alongside 'youtube.force-ssl')
YOUTUBE_MANAGE_SCOPES: List[str] = [
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
]

# Official acceptable scopes per API operation category
REQUIRED_SCOPES_BY_OPERATION: Dict[str, List[str]] = {
    "read_data": [
        "https://www.googleapis.com/auth/youtube.readonly",
        "https://www.googleapis.com/auth/youtube.force-ssl",
        "https://www.googleapis.com/auth/youtube",
    ],
    "read_analytics": [
        "https://www.googleapis.com/auth/yt-analytics.readonly",
        "https://www.googleapis.com/auth/youtube.readonly",
        "https://www.googleapis.com/auth/youtube",
    ],
    "manage_comments": [
        "https://www.googleapis.com/auth/youtube.force-ssl",
        "https://www.googleapis.com/auth/youtube",
    ],
    "manage_videos": [
        "https://www.googleapis.com/auth/youtube.force-ssl",
        "https://www.googleapis.com/auth/youtube",
    ],
    "upload_videos": [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube.force-ssl",
        "https://www.googleapis.com/auth/youtube",
    ],
}

# Documented YouTube Data API v3 Quota Costs (Default project allocation: 10,000 units/day)
YOUTUBE_API_QUOTA_COSTS: Dict[str, int] = {
    "channels.list": 1,
    "videos.list": 1,
    "playlists.list": 1,
    "commentThreads.list": 1,
    "comments.list": 1,
    "comments.insert": 50,
    "videos.update": 50,
    "videos.delete": 50,
    "search.list": 100,
    "videos.insert": 1600,
}


def has_any_required_scope(
    creds: Any,
    acceptable_scopes: List[str],
    token_data: Optional[Dict[str, Any]] = None,
) -> bool:
    """Return True if credentials grant at least one of the acceptable scopes for an operation."""
    if creds is None:
        return False
    acceptable_set = set(acceptable_scopes)
    if not acceptable_set:
        return True

    granted_set = set()
    if token_data is not None:
        granted_set.update(_extract_scopes_from_token_json(token_data))

    granted = getattr(creds, "granted_scopes", None)
    declared = getattr(creds, "scopes", None)
    active = granted if isinstance(granted, (list, set, tuple)) else declared
    if isinstance(active, (list, set, tuple)):
        granted_set.update(str(s).strip() for s in active if str(s).strip())

    return bool(granted_set & acceptable_set)


def validate_youtube_mode_scopes(
    creds: Any,
    mode: str = "manage",
    token_data: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, List[str]]:
    """Verify that credentials contain the minimum scopes required for 'readonly' or 'manage' mode.

    Returns:
        Tuple of (is_valid, missing_capabilities_descriptions).
    """
    missing: List[str] = []
    if not has_any_required_scope(creds, REQUIRED_SCOPES_BY_OPERATION["read_data"], token_data):
        missing.append("leitura de dados do YouTube (youtube.readonly ou youtube.force-ssl)")
    if not has_any_required_scope(creds, REQUIRED_SCOPES_BY_OPERATION["read_analytics"], token_data):
        missing.append("relatórios do YouTube Analytics (yt-analytics.readonly)")

    if mode == "manage":
        if not has_any_required_scope(creds, REQUIRED_SCOPES_BY_OPERATION["manage_videos"], token_data):
            missing.append("gerenciamento de vídeos e comentários (youtube.force-ssl)")
        if not has_any_required_scope(creds, REQUIRED_SCOPES_BY_OPERATION["upload_videos"], token_data):
            missing.append("envio/upload de vídeos (youtube.upload)")

    return len(missing) == 0, missing


def classify_youtube_http_error(
    err: urllib.error.HTTPError,
    api_source: str = "data_v3",
    operation_name: str = "",
) -> Tuple[str, str, bool]:
    """Classify YouTube Data API v3 and YouTube Analytics API v2 HTTP errors accurately.

    Args:
        err: The HTTPError raised by urllib.
        api_source: 'data_v3' (YouTube Data API v3) or 'analytics_v2' (YouTube Analytics API).
        operation_name: Name of the method being invoked (e.g. 'videos.insert', 'search.list').

    Returns:
        Tuple of (status_slug, user_friendly_ptbr_message, should_invalidate_token).
    """
    http_code = getattr(err, "code", 0)
    api_label = "YouTube Analytics API v2" if api_source == "analytics_v2" else "YouTube Data API v3"

    raw_body = ""
    try:
        raw_bytes = err.read()
        if raw_bytes:
            raw_body = raw_bytes.decode("utf-8", errors="ignore")
    except Exception:
        pass

    error_json: Dict[str, Any] = {}
    if raw_body:
        try:
            parsed = json.loads(raw_body)
            if isinstance(parsed, dict):
                error_json = parsed.get("error", {}) if isinstance(parsed.get("error"), dict) else parsed
        except Exception:
            pass

    api_message = str(error_json.get("message", "") or getattr(err, "reason", ""))
    api_status = str(error_json.get("status", ""))

    reasons: List[str] = []
    for item in error_json.get("errors", []) if isinstance(error_json.get("errors"), list) else []:
        if isinstance(item, dict) and item.get("reason"):
            reasons.append(str(item["reason"]))
    for detail in error_json.get("details", []) if isinstance(error_json.get("details"), list) else []:
        if isinstance(detail, dict) and detail.get("reason"):
            reasons.append(str(detail["reason"]))

    reasons_lower = {r.lower() for r in reasons}
    msg_lower = api_message.lower()

    # 1. HTTP 401 Unauthorized -> Token expired/revoked
    if http_code == 401 or "autherror" in reasons_lower or api_status == "UNAUTHENTICATED":
        return (
            "token_revoked",
            (
                f"A sessão OAuth da {api_label} expirou ou foi revogada (HTTP 401). "
                "Reconecte a conta correspondente com 'run.bat youtube-auth <email>'."
            ),
            True,
        )

    # 2. HTTP 404 Not Found
    if http_code == 404 or "notfound" in "".join(reasons_lower):
        return (
            "not_found",
            f"Recurso não encontrado na {api_label} (HTTP 404): {api_message or 'verifique o ID do canal, vídeo ou comentário.'}",
            False,
        )

    # 3. HTTP 403 Forbidden -> Granular classification
    if http_code == 403:
        if (
            "accessnotconfigured" in reasons_lower
            or "service_disabled" in reasons_lower
            or "has not been used in project" in msg_lower
            or "it is disabled" in msg_lower
        ):
            disabled_slug = (
                "youtube_analytics_api_disabled"
                if api_source == "analytics_v2"
                else "youtube_data_api_disabled"
            )
            return (
                disabled_slug,
                (
                    f"A **{api_label}** não está ativada no seu projeto do Google Cloud Console (accessNotConfigured). "
                    f"Acesse 'APIs e Serviços > Biblioteca' no Google Cloud Console, pesquise por '{api_label}' e clique em 'Ativar'."
                ),
                False,
            )

        if (
            "insufficientpermissions" in reasons_lower
            or "access_token_scope_insufficient" in reasons_lower
            or "insufficient authentication scopes" in msg_lower
        ):
            return (
                "insufficient_scopes",
                (
                    f"Permissão OAuth insuficiente na {api_label} para a operação '{operation_name or 'solicitada'}' "
                    "(insufficientPermissions). Se a conta estiver conectada em modo 'readonly' (somente leitura) ou sem o escopo "
                    "necessário, reconecte com 'run.bat youtube-auth <email> --mode manage'."
                ),
                False,
            )

        if "commentsdisabled" in reasons_lower or "comments are disabled" in msg_lower:
            return (
                "comments_disabled",
                "Os comentários estão desativados para este vídeo no YouTube.",
                False,
            )

        if (
            "quotaexceeded" in reasons_lower
            or "dailylimitexceeded" in reasons_lower
            or "ratelimitexceeded" in reasons_lower
            or "userRateLimitExceeded".lower() in reasons_lower
            or "quota" in msg_lower
        ):
            cost_info = ""
            if operation_name in YOUTUBE_API_QUOTA_COSTS:
                cost_info = f" (custo da operação '{operation_name}': {YOUTUBE_API_QUOTA_COSTS[operation_name]} unidades)"
            return (
                "youtube_quota_exceeded",
                (
                    f"Limite de cota atingido na {api_label} ao executar '{operation_name or 'requisição'}'{cost_info}. "
                    "A alocação diária padrão da YouTube Data API v3 é reiniciada à meia-noite no horário do Pacífico (PT / UTC-8 ou UTC-7)."
                ),
                False,
            )

        if (
            "forbidden" in reasons_lower
            or "channelforbidden" in reasons_lower
            or "insufficientacls" in reasons_lower
            or api_status == "PERMISSION_DENIED"
        ):
            return (
                "channel_forbidden",
                (
                    f"A conta autenticada não possui permissão de proprietário/administrador para realizar esta ação na {api_label} "
                    f"({api_message or 'acesso negado ao canal ou relatório'})."
                ),
                False,
            )

        return (
            "forbidden",
            f"Acesso negado pela {api_label} (HTTP 403): {api_message or 'verifique as permissões do canal.'}",
            False,
        )

    return (
        "http_error",
        f"Erro na {api_label} (HTTP {http_code}): {api_message or 'erro desconhecido'}.",
        False,
    )


# =============================================================================
# Fail-Closed Server-Side Confirmation State Machine (Two-Phase Commit)
# =============================================================================


class ConfirmationState(str, Enum):
    """Server-side lifecycle states for YouTube write/delete confirmations."""

    CREATED = "CREATED"
    SUMMARY_PRESENTED = "SUMMARY_PRESENTED"
    USER_AFFIRMED = "USER_AFFIRMED"
    CONSUMED = "CONSUMED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    SUPERSEDED = "SUPERSEDED"
    SPEECH_INTERRUPTED = "SPEECH_INTERRUPTED"
    TERMINATED_ON_RESTART = "TERMINATED_ON_RESTART"


TERMINAL_CONFIRMATION_STATES = {
    ConfirmationState.CONSUMED,
    ConfirmationState.CANCELLED,
    ConfirmationState.EXPIRED,
    ConfirmationState.SUPERSEDED,
    ConfirmationState.SPEECH_INTERRUPTED,
    ConfirmationState.TERMINATED_ON_RESTART,
}


def compute_operation_payload_digest(operation: str, payload: Dict[str, Any]) -> str:
    """Compute a deterministic SHA-256 digest of the operation name and canonicalized parameters."""
    canonical = json.dumps(
        {"operation": operation, "payload": payload},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class PendingYouTubeConfirmation:
    """In-memory server record for a single pending write/delete operation."""

    confirmation_token: str
    service_instance_id: str
    operation: str
    payload: Dict[str, Any]
    payload_digest: str
    summary_text: str
    state: ConfirmationState
    created_at: float
    expires_at: float
    summary_presented_at: Optional[float] = None
    user_affirmed_at: Optional[float] = None
    delivery_channel: Optional[str] = None
    affirmation_source: Optional[str] = None
    terminal_reason: Optional[str] = None


class YouTubeConfirmationManager:
    """Fail-closed server-side confirmation manager for YouTube write, upload, and delete actions.

    Guarantees:
    1. Ephemeral in-memory storage bound to a unique `service_instance_id`; restarting the process or service
       invalidates all pending confirmations.
    2. Creating a new proposal automatically supersedes any previous non-terminal proposal (even one in USER_AFFIRMED),
       so at most ONE pending action can ever be active at a time.
    3. Monotonic server clocks enforce: created_at <= summary_presented_at <= user_affirmed_at <= execution_time <= expires_at.
    4. Model-supplied flags cannot bypass `SUMMARY_PRESENTED` or `USER_AFFIRMED`; only out-of-band host events
       (after voice playback completion without interruption, or CLI/Gateway post-summary user turn) can advance states.
    5. Tokens are single-use and bound to the exact SHA-256 digest of the operation and all parameters.
    """

    def __init__(self, ttl_seconds: float = 300.0, time_fn: Any = None):
        self.ttl_seconds = ttl_seconds
        self._time_fn = time_fn if callable(time_fn) else time.monotonic
        self.service_instance_id: str = secrets.token_hex(16)
        self._records: Dict[str, PendingYouTubeConfirmation] = {}
        self._active_token: Optional[str] = None
        self._awaiting_voice_finish_token: Optional[str] = None
        self._voice_playback_started: bool = False

    def reset_service_session(self) -> str:
        """Generate a new service_instance_id on service restart/re-init and invalidate all prior confirmations."""
        self._records.clear()
        self.service_instance_id = secrets.token_hex(16)
        self._active_token = None
        self._awaiting_voice_finish_token = None
        self._voice_playback_started = False
        return self.service_instance_id

    def create_proposal(
        self,
        operation: str,
        payload: Dict[str, Any],
        summary_text: str = "",
        summary_pt_br: str = "",
        channel_id: str = "",
        channel_title: str = "",
        account_email: str = "",
        auto_present_for_cli: bool = False,
    ) -> PendingYouTubeConfirmation:
        """Create a Step 1 confirmation proposal and supersede any previous non-terminal proposal."""
        now = float(self._time_fn())
        effective_summary = summary_text or summary_pt_br

        # Supersede any existing non-terminal proposal (including USER_AFFIRMED not yet consumed)
        for existing in self._records.values():
            if existing.state not in TERMINAL_CONFIRMATION_STATES:
                existing.state = ConfirmationState.SUPERSEDED
                existing.terminal_reason = (
                    "Esta confirmação foi substituída por uma nova solicitação mais recente e não pode mais ser executada."
                )

        token = f"ytconf_{secrets.token_hex(8)}"
        digest = compute_operation_payload_digest(operation, payload)
        rec = PendingYouTubeConfirmation(
            confirmation_token=token,
            service_instance_id=self.service_instance_id,
            operation=operation,
            payload=dict(payload),
            payload_digest=digest,
            summary_text=effective_summary,
            state=ConfirmationState.CREATED,
            created_at=now,
            expires_at=now + self.ttl_seconds,
        )
        self._records[token] = rec
        self._active_token = token
        self._awaiting_voice_finish_token = token
        self._voice_playback_started = False

        if auto_present_for_cli:
            self.mark_summary_presented(token, delivery_channel="cli")

        return rec

    def notify_voice_playback_started(self) -> None:
        """Called by AMRAssistant when Aton starts speaking the pending confirmation summary."""
        if self._awaiting_voice_finish_token:
            self._voice_playback_started = True

    def notify_voice_playback_completed_cleanly(self) -> bool:
        """Called by AMRAssistant after Aton finishes speaking the summary and echo buffer is flushed."""
        tok = self._awaiting_voice_finish_token
        if not tok or not self._voice_playback_started:
            return False
        self._awaiting_voice_finish_token = None
        self._voice_playback_started = False
        return self.mark_summary_presented(tok, delivery_channel="voice")

    def mark_speech_interrupted(self) -> None:
        """Invalidate pending confirmation if Aton's spoken summary was interrupted before completion."""
        tok = self._awaiting_voice_finish_token or self._active_token
        if tok and tok in self._records:
            rec = self._records[tok]
            if rec.state in (ConfirmationState.CREATED, ConfirmationState.SUMMARY_PRESENTED):
                rec.state = ConfirmationState.SPEECH_INTERRUPTED
                rec.terminal_reason = (
                    "A leitura do resumo de confirmação foi interrompida antes do fim. "
                    "Solicite a operação novamente para ouvir o resumo completo antes de confirmar."
                )
        self._awaiting_voice_finish_token = None
        self._voice_playback_started = False
        if self._active_token == tok:
            self._active_token = None

    def mark_summary_presented(self, confirmation_token: str, delivery_channel: str = "voice") -> bool:
        """Record on the server that the Step 1 summary has been completely delivered to the user."""
        now = float(self._time_fn())
        rec = self._records.get(confirmation_token)
        if rec is None:
            return False
        if rec.service_instance_id != self.service_instance_id:
            rec.state = ConfirmationState.TERMINATED_ON_RESTART
            return False
        if rec.state in TERMINAL_CONFIRMATION_STATES:
            return False
        if now > rec.expires_at:
            rec.state = ConfirmationState.EXPIRED
            rec.terminal_reason = "O token de confirmação expirou."
            return False

        rec.state = ConfirmationState.SUMMARY_PRESENTED
        rec.summary_presented_at = now
        rec.delivery_channel = delivery_channel
        return True

    def get_active_pending_confirmation(self) -> Optional[PendingYouTubeConfirmation]:
        """Return the single active non-terminal confirmation, or None."""
        if not self._active_token:
            return None
        rec = self._records.get(self._active_token)
        if not rec:
            return None
        if rec.service_instance_id != self.service_instance_id:
            rec.state = ConfirmationState.TERMINATED_ON_RESTART
            self._active_token = None
            return None
        if float(self._time_fn()) > rec.expires_at and rec.state not in TERMINAL_CONFIRMATION_STATES:
            rec.state = ConfirmationState.EXPIRED
            rec.terminal_reason = "O tempo limite de confirmação (5 minutos) expirou."
            self._active_token = None
            return None
        if rec.state in TERMINAL_CONFIRMATION_STATES:
            self._active_token = None
            return None
        return rec

    def cancel_active_proposal(self, reason: str = "Operação cancelada pelo usuário.") -> Optional[str]:
        """Cancel and permanently invalidate the currently active pending confirmation."""
        rec = self.get_active_pending_confirmation()
        if rec is None:
            return None
        rec.state = ConfirmationState.CANCELLED
        rec.terminal_reason = reason
        self._active_token = None
        self._awaiting_voice_finish_token = None
        self._voice_playback_started = False
        return rec.confirmation_token

    def record_user_affirmative_turn(
        self,
        confirmation_token: Optional[str] = None,
        source: str = "voice",
    ) -> Tuple[bool, str, Optional[str]]:
        """Record an out-of-band affirmative user response after the summary was presented.

        Fails closed if:
        - More than one non-terminal confirmation exists (ambiguity protection);
        - No confirmation is active or the token was superseded/cancelled/expired/restarted;
        - The summary was not yet presented (`state != SUMMARY_PRESENTED`).
        """
        now = float(self._time_fn())
        non_terminal = [
            r for r in self._records.values()
            if r.state not in TERMINAL_CONFIRMATION_STATES
            and r.service_instance_id == self.service_instance_id
            and now <= r.expires_at
        ]

        if len(non_terminal) > 1:
            for r in non_terminal:
                r.state = ConfirmationState.CANCELLED
                r.terminal_reason = "Múltiplas confirmações pendentes simultâneas foram canceladas por segurança."
            self._active_token = None
            return (
                False,
                "ambiguous_pending_confirmations",
                "Havia mais de uma ação pendente; por segurança, todas foram canceladas. Solicite apenas uma ação por vez.",
            )

        target_token = confirmation_token or self._active_token
        if not target_token or target_token not in self._records:
            return False, "no_active_proposal", "Não há nenhuma operação pendente aguardando confirmação."

        rec = self._records[target_token]
        if rec.service_instance_id != self.service_instance_id:
            rec.state = ConfirmationState.TERMINATED_ON_RESTART
            return False, "restarted_session", "O serviço foi reiniciado; solicite a operação novamente."

        if now > rec.expires_at and rec.state not in TERMINAL_CONFIRMATION_STATES:
            rec.state = ConfirmationState.EXPIRED
            rec.terminal_reason = "O token de confirmação expirou."

        if rec.state in TERMINAL_CONFIRMATION_STATES:
            return (
                False,
                f"invalid_state_{rec.state.value.lower()}",
                rec.terminal_reason or f"A confirmação '{target_token}' não está mais válida ({rec.state.value}).",
            )

        if rec.state != ConfirmationState.SUMMARY_PRESENTED or rec.summary_presented_at is None:
            return (
                False,
                "summary_not_presented",
                "O resumo da operação ainda não terminou de ser apresentado ao usuário. Aguarde a conclusão do resumo antes de confirmar.",
            )

        if now < rec.summary_presented_at:
            return (
                False,
                "invalid_timestamp_order",
                "A resposta de confirmação não pode ter horário anterior à apresentação do resumo.",
            )

        rec.state = ConfirmationState.USER_AFFIRMED
        rec.user_affirmed_at = now
        rec.affirmation_source = source
        return True, "user_affirmed", rec.confirmation_token

    def validate_and_consume(
        self,
        confirmation_token: str,
        operation: str,
        payload: Dict[str, Any],
    ) -> Tuple[bool, str, str]:
        """Validate a Step 2 confirmation token, state sequence, and exact parameter digest, then consume it once."""
        now = float(self._time_fn())
        if not confirmation_token or not confirmation_token.strip():
            return (
                False,
                "missing_confirmation_token",
                "Token de confirmação ausente. A operação exige primeiro apresentar o resumo ao usuário.",
            )

        rec = self._records.get(confirmation_token.strip())
        if rec is None:
            return (
                False,
                "invalid_confirmation_token",
                f"O token de confirmação '{confirmation_token}' não existe ou foi invalidado após reinicialização do Aton.",
            )

        if rec.service_instance_id != self.service_instance_id:
            rec.state = ConfirmationState.TERMINATED_ON_RESTART
            return (
                False,
                "restarted_session",
                "O Aton foi reiniciado desde a emissão deste resumo. Gere um novo resumo e peça nova confirmação ao usuário.",
            )

        if now > rec.expires_at and rec.state not in TERMINAL_CONFIRMATION_STATES:
            rec.state = ConfirmationState.EXPIRED
            rec.terminal_reason = "O token de confirmação expirou (limite de 5 minutos)."

        if rec.state in TERMINAL_CONFIRMATION_STATES:
            reason_msg = rec.terminal_reason or f"O token '{confirmation_token}' já foi encerrado ({rec.state.value})."
            return False, f"token_{rec.state.value.lower()}", reason_msg

        # Verify operation and exact payload digest BEFORE checking affirmation state
        expected_digest = compute_operation_payload_digest(operation, payload)
        if rec.operation != operation or rec.payload_digest != expected_digest:
            rec.state = ConfirmationState.CANCELLED
            rec.terminal_reason = (
                "Os parâmetros da operação mudaram em relação ao resumo confirmado. "
                "O token anterior foi cancelado; gere um novo resumo com os novos dados."
            )
            if self._active_token == rec.confirmation_token:
                self._active_token = None
            return False, "payload_mismatch", rec.terminal_reason

        if rec.state != ConfirmationState.USER_AFFIRMED:
            return (
                False,
                "unverified_user_confirmation",
                (
                    "Bloqueio de segurança (fail-closed): o resumo foi gerado, mas o servidor ainda não registrou "
                    "uma resposta afirmativa real do usuário ('Sim' / 'Confirmo') posterior à leitura completa do resumo."
                ),
            )

        if (
            rec.summary_presented_at is None
            or rec.user_affirmed_at is None
            or not (rec.created_at <= rec.summary_presented_at <= rec.user_affirmed_at <= now)
        ):
            rec.state = ConfirmationState.CANCELLED
            rec.terminal_reason = "Sequência temporal de confirmação inválida no servidor."
            return False, "invalid_confirmation_sequence", rec.terminal_reason

        # Consume single-use token
        rec.state = ConfirmationState.CONSUMED
        rec.terminal_reason = "Token de confirmação já utilizado (uso único)."
        if self._active_token == rec.confirmation_token:
            self._active_token = None
        return True, "confirmed", "Confirmação validada com sucesso."

    verify_and_consume = validate_and_consume


# =============================================================================
# YouTube Connection & Multi-Channel Service
# =============================================================================


class YouTubeConnectionService:
    """Manages OAuth 2.0 Desktop tokens, channel discovery, and API requests for YouTube Data v3 & Analytics v2."""

    def __init__(
        self,
        credentials_path: Optional[Path] = None,
        tokens_dir: Optional[Path] = None,
        confirmation_manager: Optional[YouTubeConfirmationManager] = None,
    ):
        self.credentials_path: Path = (
            Path(credentials_path) if credentials_path is not None else settings.get_youtube_credentials_file()
        )
        self.tokens_dir: Path = (
            Path(tokens_dir) if tokens_dir is not None else settings.get_youtube_tokens_dir()
        )
        self.index_path: Path = self.tokens_dir / "youtube_channels_index.json"
        self.confirmations: YouTubeConfirmationManager = (
            confirmation_manager if confirmation_manager is not None else YouTubeConfirmationManager()
        )

    def reset_session(self) -> str:
        """Reset ephemeral confirmation session state upon service restart."""
        return self.confirmations.reset_service_session()

    # -------------------------------------------------------------------------
    # Index & Collision-Safe (account_email, channel_id) File Resolution
    # -------------------------------------------------------------------------

    def _load_channels_index(self) -> Dict[str, Dict[str, Any]]:
        """Load the YouTube multi-account/multi-channel index mapping entry_key -> metadata."""
        if not self.index_path.exists():
            return {}
        try:
            raw = self.index_path.read_text(encoding="utf-8")
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and isinstance(parsed.get("entries"), dict):
                return parsed["entries"]
        except Exception as exc:
            logger.warning(f"Erro ao ler índice de canais do YouTube '{self.index_path.name}': {exc}")
        return {}

    def _save_channels_index(self, entries: Dict[str, Dict[str, Any]]) -> None:
        """Atomically persist the YouTube multi-channel index to disk."""
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "entries": entries,
        }
        _atomic_write_text(self.index_path, json.dumps(payload, indent=2, ensure_ascii=False))

    @staticmethod
    def make_entry_key(account_email: str, channel_id: Optional[str]) -> str:
        """Build canonical composite key distinguishing different channels under the same Google Account."""
        email_norm = account_email.strip().lower()
        chan_norm = (channel_id or "unlinked").strip()
        return f"{email_norm}::{chan_norm}"

    def _resolve_collision_safe_token_file(
        self,
        account_email: str,
        channel_id: Optional[str],
        entries: Dict[str, Dict[str, Any]],
    ) -> Tuple[str, str, Path]:
        """Compute full 64-char SHA-256 token filename from (account_email, channel_id) with collision detection."""
        email_norm = account_email.strip().lower()
        chan_norm = (channel_id or "unlinked").strip()
        entry_key = self.make_entry_key(email_norm, chan_norm)

        existing = entries.get(entry_key)
        if isinstance(existing, dict) and existing.get("account_id") and existing.get("token_file"):
            cand_id = str(existing["account_id"])
            cand_path = self.tokens_dir / str(existing["token_file"])
            if cand_path.exists():
                try:
                    disk_data = json.loads(cand_path.read_text(encoding="utf-8"))
                    disk_email = str(disk_data.get("account_email", "")).strip().lower()
                    disk_chan = str(disk_data.get("channel_id", "")).strip() or "unlinked"
                    if (not disk_email or disk_email == email_norm) and (disk_chan == chan_norm):
                        return entry_key, cand_id, cand_path
                except Exception:
                    pass
            else:
                return entry_key, cand_id, cand_path

        full_sha256 = hashlib.sha256(entry_key.encode("utf-8")).hexdigest()
        used_ids = {
            str(meta.get("account_id", ""))
            for k, meta in entries.items()
            if k != entry_key and isinstance(meta, dict)
        }
        used_files = {
            str(meta.get("token_file", ""))
            for k, meta in entries.items()
            if k != entry_key and isinstance(meta, dict)
        }

        suffix = 0
        while True:
            cand_id = f"youtube_acct_{full_sha256}" if suffix == 0 else f"youtube_acct_{full_sha256}_{suffix}"
            cand_filename = f"{cand_id}.json"
            cand_path = self.tokens_dir / cand_filename

            disk_conflict = False
            if cand_path.exists():
                try:
                    existing_json = json.loads(cand_path.read_text(encoding="utf-8"))
                    bound_email = str(existing_json.get("account_email", "")).strip().lower()
                    bound_chan = str(existing_json.get("channel_id", "")).strip() or "unlinked"
                    if (bound_email and bound_email != email_norm) or (bound_chan != chan_norm):
                        disk_conflict = True
                except Exception:
                    pass

            if cand_id not in used_ids and cand_filename not in used_files and not disk_conflict:
                return entry_key, cand_id, cand_path

            suffix += 1

    def _serialize_credentials(
        self,
        creds: Any,
        account_email: str,
        channel_id: Optional[str],
        access_mode: str,
        default_scopes: List[str],
    ) -> str:
        """Serialize OAuth credentials with verified account_email, channel_id, access_mode, and scopes."""
        token_json = creds.to_json()
        parsed = json.loads(token_json)
        raw_granted = getattr(creds, "granted_scopes", None)
        raw_declared = getattr(creds, "scopes", None)
        if isinstance(raw_granted, (list, set, tuple)) and raw_granted:
            granted = list(raw_granted)
        elif isinstance(raw_declared, (list, set, tuple)) and raw_declared:
            granted = list(raw_declared)
        elif isinstance(parsed.get("scopes"), list) and parsed.get("scopes"):
            granted = list(parsed["scopes"])
        else:
            granted = list(default_scopes)
        parsed["scopes"] = list(granted)
        parsed["account_email"] = account_email.strip().lower()
        parsed["channel_id"] = (channel_id or "unlinked").strip()
        parsed["access_mode"] = access_mode
        return json.dumps(parsed)

    def _save_channel_entry_token(
        self,
        creds: Any,
        account_email: str,
        channel_info: Optional[Dict[str, Any]],
        access_mode: str,
        scopes: List[str],
    ) -> Tuple[str, Path]:
        """Atomically save token for a verified (account_email, channel_id) pair and update the index."""
        email_norm = account_email.strip().lower()
        chan_id = str(channel_info.get("channel_id", "")).strip() if channel_info else "unlinked"
        if not chan_id:
            chan_id = "unlinked"

        entries = self._load_channels_index()
        entry_key, account_id, token_file_path = self._resolve_collision_safe_token_file(
            email_norm, chan_id, entries
        )

        serialized = self._serialize_credentials(
            creds=creds,
            account_email=email_norm,
            channel_id=chan_id,
            access_mode=access_mode,
            default_scopes=scopes,
        )
        _atomic_write_text(token_file_path, serialized)

        granted_scopes = json.loads(serialized).get("scopes", scopes)
        entries[entry_key] = {
            "entry_key": entry_key,
            "account_id": account_id,
            "account_email": email_norm,
            "channel_id": chan_id,
            "channel_title": channel_info.get("title", "Sem canal vinculado") if channel_info else "Sem canal vinculado",
            "custom_url": channel_info.get("custom_url", "") if channel_info else "",
            "description": channel_info.get("description", "") if channel_info else "",
            "uploads_playlist_id": channel_info.get("uploads_playlist_id", "") if channel_info else "",
            "subscriber_count": channel_info.get("subscriber_count", 0) if channel_info else 0,
            "video_count": channel_info.get("video_count", 0) if channel_info else 0,
            "view_count": channel_info.get("view_count", 0) if channel_info else 0,
            "hidden_subscriber_count": channel_info.get("hidden_subscriber_count", False) if channel_info else False,
            "token_file": token_file_path.name,
            "access_mode": access_mode,
            "scopes": list(granted_scopes),
            "status": "authenticated",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save_channels_index(entries)
        logger.info(
            f"Token do YouTube salvo com segurança para '{email_norm}' / canal '{chan_id}' ({token_file_path.name})."
        )
        return entry_key, token_file_path

    def get_all_configured_channels(self, require_real_channel: bool = True) -> List[Dict[str, Any]]:
        """Return all configured channel entries from the index."""
        entries = self._load_channels_index()
        out: List[Dict[str, Any]] = []
        for meta in entries.values():
            if not isinstance(meta, dict):
                continue
            if require_real_channel and meta.get("channel_id") in (None, "", "unlinked"):
                continue
            out.append(dict(meta))
        return out

    def invalidate_entry_token(self, entry_key: str) -> None:
        """Delete local token file for a specific entry_key and mark it as reauth_required in the index."""
        entries = self._load_channels_index()
        meta = entries.get(entry_key)
        if isinstance(meta, dict):
            fname = meta.get("token_file")
            if fname:
                fpath = self.tokens_dir / str(fname)
                if fpath.exists():
                    try:
                        fpath.unlink()
                    except Exception as exc:
                        logger.warning(f"Não foi possível remover arquivo de token {fpath.name}: {exc}")
            meta["status"] = "reauth_required"
            meta["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._save_channels_index(entries)

    # -------------------------------------------------------------------------
    # In-Memory Verification Helpers (Userinfo & Channel Discovery)
    # -------------------------------------------------------------------------

    def _fetch_userinfo_email(self, access_token: str, timeout: int = 10) -> Tuple[Optional[str], str, str]:
        """Confirm the authorized Google Account email address using OAuth2 userinfo endpoint."""
        url = "https://www.googleapis.com/oauth2/v2/userinfo"
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                email = str(data.get("email", "")).strip().lower()
                if email and "@" in email:
                    return email, "success", "OK"
                return None, "missing_email", "A resposta de userinfo do Google não retornou um endereço de e-mail válido."
        except urllib.error.HTTPError as http_err:
            slug, msg, _ = classify_youtube_http_error(http_err, api_source="data_v3", operation_name="userinfo")
            return None, slug, msg
        except Exception as exc:
            return None, "network_error", f"Não foi possível confirmar o e-mail autorizado no Google: {exc}"

    @staticmethod
    def _parse_channel_item(item: Dict[str, Any]) -> Dict[str, Any]:
        """Extract normalized channel metadata from a YouTube Data API v3 channel resource."""
        snippet = item.get("snippet", {}) or {}
        stats = item.get("statistics", {}) or {}
        content_details = item.get("contentDetails", {}) or {}
        related_playlists = content_details.get("relatedPlaylists", {}) or {}
        status_obj = item.get("status", {}) or {}

        def _to_int(val: Any) -> int:
            try:
                return int(val)
            except (TypeError, ValueError):
                return 0

        return {
            "channel_id": str(item.get("id", "")).strip(),
            "title": str(snippet.get("title", "Sem título")).strip(),
            "custom_url": str(snippet.get("customUrl", "")).strip(),
            "description": str(snippet.get("description", "")).strip(),
            "published_at": str(snippet.get("publishedAt", "")).strip(),
            "country": str(snippet.get("country", "")).strip(),
            "subscriber_count": _to_int(stats.get("subscriberCount", 0)),
            "video_count": _to_int(stats.get("videoCount", 0)),
            "view_count": _to_int(stats.get("viewCount", 0)),
            "hidden_subscriber_count": bool(stats.get("hiddenSubscriberCount", False)),
            "uploads_playlist_id": str(related_playlists.get("uploads", "")).strip(),
            "privacy_status": str(status_obj.get("privacyStatus", "")).strip(),
            "is_linked": bool(status_obj.get("isLinked", True)),
        }

    def _discover_mine_channels_with_token(
        self,
        access_token: str,
        timeout: int = 10,
    ) -> Tuple[Optional[List[Dict[str, Any]]], str, str]:
        """Query YouTube Data API v3 channels.list(mine=True) using an in-memory access token."""
        params = urllib.parse.urlencode(
            {
                "part": "snippet,statistics,contentDetails,status",
                "mine": "true",
                "maxResults": 50,
            }
        )
        url = f"https://www.googleapis.com/youtube/v3/channels?{params}"
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                items = data.get("items", []) if isinstance(data, dict) else []
                channels = [self._parse_channel_item(it) for it in items if isinstance(it, dict) and it.get("id")]
                return channels, "success", "OK"
        except urllib.error.HTTPError as http_err:
            slug, msg, _ = classify_youtube_http_error(
                http_err, api_source="data_v3", operation_name="channels.list"
            )
            return None, slug, msg
        except Exception as exc:
            return None, "network_error", f"Falha de rede ao consultar canais na YouTube Data API v3: {exc}"

    def fetch_public_channel_metadata(
        self,
        channel_id: str,
        access_token: Optional[str] = None,
        timeout: int = 10,
    ) -> Tuple[Optional[Dict[str, Any]], str, str]:
        """Query public metadata of a specific channel ID via channels.list(id=...) without assuming ownership."""
        if not access_token:
            entries = self._load_channels_index()
            for entry_key in entries.keys():
                data, code, msg = self.request_data_api(
                    "channels",
                    entry_key=entry_key,
                    query_params={"part": "snippet,statistics", "id": channel_id.strip()},
                    required_operation="read_data",
                    operation_name="channels.list",
                    timeout=timeout,
                )
                if data is not None and code == "success":
                    items = data.get("items", []) if isinstance(data, dict) else []
                    if not items:
                        return None, "not_found", f"O canal '{channel_id}' não foi encontrado na YouTube Data API v3."
                    return self._parse_channel_item(items[0]), "success", "OK"
            return (
                None,
                "not_authenticated",
                "Nenhuma credencial ativa disponível para consultar os metadados públicos do canal.",
            )

        token = access_token

        params = urllib.parse.urlencode(
            {
                "part": "snippet,statistics",
                "id": channel_id.strip(),
            }
        )
        url = f"https://www.googleapis.com/youtube/v3/channels?{params}"
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {token}"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                items = data.get("items", []) if isinstance(data, dict) else []
                if not items:
                    return None, "not_found", f"O canal '{channel_id}' não foi encontrado na YouTube Data API v3."
                return self._parse_channel_item(items[0]), "success", "OK"
        except urllib.error.HTTPError as http_err:
            slug, msg, _ = classify_youtube_http_error(
                http_err, api_source="data_v3", operation_name="channels.list"
            )
            return None, slug, msg
        except Exception as exc:
            return None, "network_error", f"Erro ao consultar metadados públicos do canal '{channel_id}': {exc}"

    # -------------------------------------------------------------------------
    # Credential Loading, Scope Verification & Silent Refresh
    # -------------------------------------------------------------------------

    def _load_and_validate_entry_credentials(
        self,
        entry_key: str,
        required_operation: str = "read_data",
    ) -> Tuple[Optional[Any], str, str]:
        """Load, validate operation scopes, and silently refresh token for a specific index entry_key (never opens browser)."""
        try:
            from google.auth.exceptions import RefreshError
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
        except ImportError:
            return (
                None,
                "missing_dependency",
                "As bibliotecas 'google-auth' e 'google-auth-oauthlib' não estão instaladas. Execute 'run.bat install'.",
            )

        entries = self._load_channels_index()
        meta = entries.get(entry_key)
        if not isinstance(meta, dict):
            return None, "channel_not_found", f"Registro '{entry_key}' não encontrado no índice do YouTube."

        account_email = str(meta.get("account_email", "")).strip()
        channel_id = str(meta.get("channel_id", "")).strip()
        channel_title = str(meta.get("channel_title", channel_id)).strip()
        access_mode = str(meta.get("access_mode", "manage")).strip()
        label = f"da conta '{account_email}' (canal '{channel_title}' [{channel_id}])"

        token_file = self.tokens_dir / str(meta.get("token_file", ""))
        if not token_file.exists():
            return (
                None,
                "not_authenticated",
                f"O token local {label} não foi encontrado. Reconecte com 'run.bat youtube-auth {account_email}'.",
            )

        try:
            raw_text = token_file.read_text(encoding="utf-8")
            token_data = json.loads(raw_text)
            if not isinstance(token_data, dict):
                raise ValueError("Root is not dict")
        except Exception:
            self.invalidate_entry_token(entry_key)
            return (
                None,
                "corrupted_token",
                f"O arquivo de token {label} estava corrompido e foi removido. Reconecte pelo navegador.",
            )

        try:
            creds = Credentials.from_authorized_user_info(token_data)
        except Exception:
            self.invalidate_entry_token(entry_key)
            return (
                None,
                "corrupted_token",
                f"A estrutura do token {label} é inválida e foi removida. Reconecte pelo navegador.",
            )

        acceptable_scopes = REQUIRED_SCOPES_BY_OPERATION.get(
            required_operation, REQUIRED_SCOPES_BY_OPERATION["read_data"]
        )
        if not has_any_required_scope(creds, acceptable_scopes, token_data=token_data):
            # Do NOT delete a valid readonly token when a write operation is attempted!
            return (
                None,
                "insufficient_scopes",
                (
                    f"O token {label} está no modo '{access_mode}' e não possui o escopo exigido para a operação "
                    f"'{required_operation}' (requer um de: {', '.join(acceptable_scopes)}). "
                    f"Para habilitar gerenciamento/publicação, execute 'run.bat youtube-auth {account_email} --mode manage'."
                ),
            )

        if creds.expired:
            if not creds.refresh_token:
                self.invalidate_entry_token(entry_key)
                return (
                    None,
                    "token_expired",
                    f"A sessão do YouTube {label} expirou e não possui refresh_token. Reconecte com 'run.bat youtube-auth {account_email}'.",
                )
            try:
                creds.refresh(Request())
                serialized = self._serialize_credentials(
                    creds=creds,
                    account_email=account_email,
                    channel_id=channel_id,
                    access_mode=access_mode,
                    default_scopes=meta.get("scopes", YOUTUBE_MANAGE_SCOPES),
                )
                _atomic_write_text(token_file, serialized)
                meta["status"] = "authenticated"
                meta["updated_at"] = datetime.now(timezone.utc).isoformat()
                self._save_channels_index(entries)
                logger.info(f"Token OAuth2 do YouTube {label} renovado silenciosamente.")
            except RefreshError:
                self.invalidate_entry_token(entry_key)
                return (
                    None,
                    "token_revoked",
                    (
                        f"O acesso ao YouTube {label} expirou ou foi revogado (invalid_grant — em modo 'Testando' do Google Cloud, "
                        f"tokens expiram após 7 dias). Reconecte com 'run.bat youtube-auth {account_email}'."
                    ),
                )
            except Exception as exc:
                return (
                    None,
                    "refresh_network_error",
                    f"Erro de rede ao renovar o token do YouTube {label}: {exc}",
                )

        if not creds.valid:
            self.invalidate_entry_token(entry_key)
            return (
                None,
                "not_authenticated",
                f"As credenciais do YouTube {label} não estão válidas. Reconecte com 'run.bat youtube-auth {account_email}'.",
            )

        return creds, "authenticated", f"Credenciais válidas para {label}."

    # -------------------------------------------------------------------------
    # Channel Resolution & Ambiguity Detection
    # -------------------------------------------------------------------------

    def resolve_channel_entry(
        self,
        channel_query: Optional[str] = None,
        account_query: Optional[str] = None,
        require_real_channel: bool = True,
    ) -> Tuple[Optional[Dict[str, Any]], str, str]:
        """Resolve a single unambiguous channel entry by channel ID, title, @handle, or account email.

        Never silently guesses when multiple channels match! Returns 'ambiguous_channel' listing candidates.
        """
        entries = self._load_channels_index()
        if not entries:
            return (
                None,
                "not_authenticated",
                (
                    "Nenhuma conta ou canal do YouTube está conectado ao Aton ainda. "
                    "Execute 'run.bat youtube-auth cursopb@gmail.com' e 'run.bat youtube-auth servpb@gmail.com'."
                ),
            )

        candidates: List[Dict[str, Any]] = []
        for meta in entries.values():
            if not isinstance(meta, dict):
                continue
            if require_real_channel and meta.get("channel_id") in (None, "", "unlinked"):
                continue
            candidates.append(meta)

        if account_query and account_query.strip():
            aq = account_query.strip().lower()
            candidates = [
                m for m in candidates
                if m.get("account_email", "").lower() == aq
                or m.get("account_email", "").lower().split("@")[0] == aq
            ]

        if channel_query and channel_query.strip():
            cq_raw = channel_query.strip()
            cq = cq_raw.lower()

            # 1. Exact channel_id or entry_key match
            exact_id = [
                m for m in candidates
                if str(m.get("channel_id", "")).strip() == cq_raw
                or str(m.get("channel_id", "")).strip().lower() == cq
                or str(m.get("entry_key", "")).strip().lower() == cq
            ]
            if len(exact_id) == 1:
                return exact_id[0], "resolved", "OK"
            if len(exact_id) > 1:
                accounts_str = ", ".join(f"{m.get('channel_title')} ({m.get('account_email')})" for m in exact_id)
                return (
                    None,
                    "ambiguous_channel",
                    f"O canal '{cq_raw}' está associado a mais de uma conta ({accounts_str}). Especifique a conta ou chave exata.",
                )

            # 2. Exact title or @custom_url match
            exact_title = [
                m for m in candidates
                if str(m.get("channel_title", "")).strip().lower() == cq
                or str(m.get("custom_url", "")).strip().lower() == cq
                or str(m.get("custom_url", "")).strip().lower().lstrip("@") == cq.lstrip("@")
            ]
            if len(exact_title) == 1:
                return exact_title[0], "resolved", "OK"
            if len(exact_title) > 1:
                opts = ", ".join(f"{m.get('channel_title')} [{m.get('channel_id')}] ({m.get('account_email')})" for m in exact_title)
                return (
                    None,
                    "ambiguous_channel",
                    f"Mais de um canal corresponde a '{cq_raw}': {opts}. Informe o ID exato do canal.",
                )

            # 3. Substring match on title, custom_url, or account_email
            partial = [
                m for m in candidates
                if cq in str(m.get("channel_title", "")).lower()
                or cq in str(m.get("custom_url", "")).lower()
                or cq == str(m.get("account_email", "")).lower()
                or cq == str(m.get("account_email", "")).lower().split("@")[0]
            ]
            if len(partial) == 1:
                return partial[0], "resolved", "OK"
            if len(partial) > 1:
                opts = ", ".join(f"{m.get('channel_title')} [{m.get('channel_id')}] ({m.get('account_email')})" for m in partial)
                return (
                    None,
                    "ambiguous_channel",
                    f"Foram encontrados múltiplos canais para '{cq_raw}': {opts}. Especifique o nome completo ou o ID do canal.",
                )

            available = ", ".join(
                f"{m.get('channel_title')} [{m.get('channel_id')}] ({m.get('account_email')})" for m in candidates
            ) or "nenhum canal autenticado"
            return (
                None,
                "channel_not_found",
                (
                    f"O canal '{cq_raw}' não está entre os canais autenticados no Aton. "
                    f"Canais disponíveis: {available}."
                ),
            )

        # No channel_query provided:
        if len(candidates) == 1:
            return candidates[0], "resolved", "OK"
        if len(candidates) > 1:
            opts = ", ".join(
                f"{m.get('channel_title')} [{m.get('channel_id')}] ({m.get('account_email')})" for m in candidates
            )
            return (
                None,
                "ambiguous_channel",
                f"Há {len(candidates)} canais conectados ({opts}). Por favor, especifique qual canal deseja utilizar.",
            )

        return (
            None,
            "channel_not_found",
            "Nenhum canal do YouTube vinculado foi encontrado nas contas conectadas.",
        )

    # -------------------------------------------------------------------------
    # Interactive OAuth 2.0 Flow (With Safe Mode Transition & Channel Discovery)
    # -------------------------------------------------------------------------

    def authenticate_interactive(
        self,
        open_browser: bool = True,
        expected_email: Optional[str] = None,
        mode: str = "manage",
    ) -> Dict[str, Any]:
        """Run interactive OAuth 2.0 Desktop flow for YouTube, preserving existing tokens until validation succeeds.

        Does NOT automatically revoke tokens on downgrade to readonly (avoiding invalidating the new grant).
        """
        mode_norm = mode.strip().lower() if mode else "manage"
        if mode_norm not in ("readonly", "manage"):
            return {
                "status": "invalid_mode",
                "message": f"Modo de acesso inválido '{mode}'. Use 'readonly' ou 'manage'.",
            }

        requested_scopes = list(YOUTUBE_READONLY_SCOPES if mode_norm == "readonly" else YOUTUBE_MANAGE_SCOPES)

        is_valid_file, file_code, file_msg = validate_client_credentials_file(self.credentials_path)
        if not is_valid_file:
            return {
                "status": file_code,
                "message": file_msg,
            }

        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError:
            return {
                "status": "missing_dependency",
                "message": "A biblioteca 'google-auth-oauthlib' não está instalada. Execute 'run.bat install'.",
            }

        expected_norm = expected_email.strip().lower() if expected_email and expected_email.strip() else None

        try:
            # Prevent oauthlib from raising an exception when Google adds 'openid'/'email' or changes scope order;
            # strict scope validation is performed immediately below via validate_youtube_mode_scopes().
            os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
            flow = InstalledAppFlow.from_client_secrets_file(
                str(self.credentials_path),
                scopes=requested_scopes,
            )
            auth_kwargs: Dict[str, Any] = {
                "port": 0,
                "open_browser": open_browser,
                "prompt": "select_account consent",
                "access_type": "offline",
                "include_granted_scopes": "false",
            }
            if expected_norm:
                auth_kwargs["login_hint"] = expected_norm

            creds = flow.run_local_server(**auth_kwargs)
        except Exception as exc:
            logger.error(f"Falha durante autenticação OAuth 2.0 do YouTube no navegador: {exc}")
            return {
                "status": "auth_failed",
                "message": (
                    f"Não foi possível concluir a autenticação do YouTube no navegador: {exc}. "
                    "Nenhum token anterior foi alterado."
                ),
            }

        # 1. Validate granted scopes in memory BEFORE touching any file on disk
        scopes_ok, missing_caps = validate_youtube_mode_scopes(creds, mode=mode_norm, token_data=None)
        if not scopes_ok:
            return {
                "status": "insufficient_scopes",
                "missing_capabilities": missing_caps,
                "message": (
                    "A autorização no navegador não concedeu todos os escopos necessários para o modo "
                    f"'{mode_norm}' (faltando: {', '.join(missing_caps)}). "
                    "Na tela do Google, marque TODAS as caixinhas de permissão do YouTube ('Selecionar tudo') antes de clicar em Continuar. "
                    "O token anterior foi preservado intacto."
                ),
            }

        # 2. Confirm the authorized Google Account email in memory via userinfo
        access_tok = getattr(creds, "token", "") or ""
        confirmed_email, email_status, email_msg = self._fetch_userinfo_email(access_tok)
        if not confirmed_email or email_status != "success":
            return {
                "status": email_status if email_status != "success" else "userinfo_failed",
                "message": (
                    f"Não foi possível confirmar o endereço de e-mail da conta autorizada ({email_msg}). "
                    "Nenhum token foi salvo ou alterado."
                ),
            }

        if expected_norm and confirmed_email != expected_norm:
            logger.warning(
                f"Conta Google autorizada ('{confirmed_email}') diverge da conta esperada ('{expected_norm}'). Cancelando salvamento."
            )
            return {
                "status": "account_mismatch",
                "expected_email": expected_norm,
                "authorized_email": confirmed_email,
                "message": (
                    f"Atenção: a conta Google selecionada no navegador foi '{confirmed_email}', "
                    f"mas você solicitou autenticar '{expected_norm}'. "
                    "Nenhum token foi salvo ou sobrescrito."
                ),
            }

        # 3. Discover accessible YouTube channels for this authorization via channels.list(mine=True)
        discovered_channels, disc_status, disc_msg = self._discover_mine_channels_with_token(access_tok)
        previous_entries = self._load_channels_index()
        if discovered_channels is None or disc_status != "success":
            # Save the granted token as 'unlinked' if no previous entry exists for this email so the user
            # does not lose their browser authorization if YouTube Data API v3 is not enabled yet.
            has_existing_for_email = any(
                isinstance(m, dict) and str(m.get("account_email", "")).lower() == confirmed_email
                for m in previous_entries.values()
            )
            if not has_existing_for_email:
                self._save_channel_entry_token(
                    creds=creds,
                    account_email=confirmed_email,
                    channel_info=None,
                    access_mode=mode_norm,
                    scopes=requested_scopes,
                )
            return {
                "status": disc_status,
                "email_address": confirmed_email,
                "message": (
                    f"Conta '{confirmed_email}' autenticada, mas falhou ao consultar canais na YouTube Data API v3: {disc_msg}. "
                    "O token OAuth foi salvo localmente; assim que a YouTube Data API v3 estiver ativada no Google Cloud, "
                    "basta executar 'run.bat youtube-status'."
                ),
            }

        # Check if any existing entry for the same (email, channel_id) was previously in 'manage' mode
        downgrade_notice = ""

        saved_channels_summary: List[Dict[str, Any]] = []
        if not discovered_channels:
            # Account has no YouTube channel linked to the selected identity
            entry_key = self.make_entry_key(confirmed_email, "unlinked")
            prev = previous_entries.get(entry_key)
            if isinstance(prev, dict) and prev.get("access_mode") == "manage" and mode_norm == "readonly":
                downgrade_notice = (
                    " Nota: o token local foi substituído pelo modo 'readonly' (somente leitura) sem acionar "
                    "revogação remota automática para não invalidar a nova concessão. Para revogar no Google antes, "
                    "use 'run.bat youtube-remove <email> --revoke'."
                )
            self._save_channel_entry_token(
                creds=creds,
                account_email=confirmed_email,
                channel_info=None,
                access_mode=mode_norm,
                scopes=requested_scopes,
            )
            return {
                "status": "authenticated_no_channels",
                "email_address": confirmed_email,
                "access_mode": mode_norm,
                "channels": [],
                "message": (
                    f"A conta '{confirmed_email}' foi autenticada (modo '{mode_norm}'), mas `channels.list(mine=True)` "
                    "não retornou nenhum canal vinculado a esta identidade. Se o canal desejado estiver em uma Conta de Marca "
                    f"(Brand Account), execute 'run.bat youtube-auth {confirmed_email}' novamente e selecione a Conta de Marca "
                    f"correspondente na tela do Google.{downgrade_notice}"
                ),
            }

        for ch in discovered_channels:
            ch_id = ch.get("channel_id", "unlinked")
            entry_key = self.make_entry_key(confirmed_email, ch_id)
            prev = previous_entries.get(entry_key)
            if isinstance(prev, dict) and prev.get("access_mode") == "manage" and mode_norm == "readonly":
                downgrade_notice = (
                    " O token local deste canal foi atualizado para 'readonly' (somente leitura). "
                    "A revogação remota não é acionada automaticamente no downgrade para não invalidar o novo token; "
                    "caso queira revogar concessões anteriores nos servidores do Google, utilize a ação separada "
                    "'run.bat youtube-remove <canal_ou_email> --revoke'."
                )
            self._save_channel_entry_token(
                creds=creds,
                account_email=confirmed_email,
                channel_info=ch,
                access_mode=mode_norm,
                scopes=requested_scopes,
            )
            saved_channels_summary.append({
                "channel_id": ch_id,
                "title": ch.get("title", ""),
                "custom_url": ch.get("custom_url", ""),
                "account_email": confirmed_email,
                "access_mode": mode_norm,
                "subscriber_count": ch.get("subscriber_count", 0),
                "video_count": ch.get("video_count", 0),
            })

        chan_names = ", ".join(
            f"'{c['title']}' ({c['channel_id']})" for c in saved_channels_summary
        )
        brand_note = (
            " Caso esta conta Google administre outros canais/Contas de Marca que não apareceram nesta autorização, "
            f"execute 'run.bat youtube-auth {confirmed_email}' novamente e escolha a outra identidade de canal no seletor do Google."
        )

        return {
            "status": "authenticated",
            "email_address": confirmed_email,
            "access_mode": mode_norm,
            "channels": saved_channels_summary,
            "message": (
                f"Autenticação do YouTube concluída para '{confirmed_email}' (modo '{mode_norm}')! "
                f"Canal(is) autorizado(s) nesta sessão: {chan_names}.{downgrade_notice}{brand_note}"
            ),
        }

    # -------------------------------------------------------------------------
    # Account / Channel Removal (Local vs Explicit Remote Revocation)
    # -------------------------------------------------------------------------

    def remove_account_or_channel(self, target: str, revoke_remote: bool = False) -> Dict[str, Any]:
        """Remove local YouTube token(s) matching an email address, channel ID, or entry_key.

        Remote revocation on Google's servers is only performed when revoke_remote=True.
        """
        if not target or not target.strip():
            return {
                "status": "error",
                "message": "Informe o e-mail da conta ou o ID do canal do YouTube que deseja desconectar.",
            }

        q = target.strip().lower()
        entries = self._load_channels_index()
        matching_keys = [
            k for k, meta in entries.items()
            if k.lower() == q
            or str(meta.get("account_email", "")).lower() == q
            or str(meta.get("channel_id", "")).lower() == q
            or str(meta.get("channel_title", "")).lower() == q
        ]

        if not matching_keys:
            return {
                "status": "not_found",
                "message": f"Nenhuma conta ou canal conectado corresponde a '{target}'.",
            }

        removed_items: List[str] = []
        revoked_count = 0

        for key in matching_keys:
            meta = entries[key]
            token_file = self.tokens_dir / str(meta.get("token_file", ""))
            if revoke_remote and token_file.exists():
                try:
                    token_data = json.loads(token_file.read_text(encoding="utf-8"))
                    tok_to_revoke = token_data.get("refresh_token") or token_data.get("token")
                    if tok_to_revoke:
                        rev_url = f"https://oauth2.googleapis.com/revoke?token={urllib.parse.quote(str(tok_to_revoke))}"
                        req = urllib.request.Request(
                            rev_url,
                            headers={"Content-Type": "application/x-www-form-urlencoded"},
                            method="POST",
                        )
                        with urllib.request.urlopen(req, timeout=8) as resp:
                            if resp.status == 200:
                                revoked_count += 1
                except Exception as exc:
                    logger.warning(f"Aviso ao revogar token do YouTube remotamente para '{key}': {exc}")

            if token_file.exists():
                try:
                    token_file.unlink()
                except Exception as exc:
                    logger.warning(f"Erro ao remover arquivo de token '{token_file.name}': {exc}")

            removed_items.append(
                f"{meta.get('channel_title', 'Sem canal')} [{meta.get('channel_id')}] ({meta.get('account_email')})"
            )
            del entries[key]

        self._save_channels_index(entries)

        if revoke_remote:
            revoke_msg = (
                f"Token(s) local(is) apagado(s) e revogação remota solicitada ao Google ({revoked_count} concessão(ões) revogada(s) para o Aton; "
                "isso não afeta permissões concedidas a outros aplicativos)."
            )
        else:
            revoke_msg = (
                "Token(s) local(is) apagado(s) no Aton. Nota: isso não revoga a autorização nos servidores da Conta Google "
                "(use '--revoke' se desejar revogar remotamente a autorização concedida ao Aton)."
            )

        return {
            "status": "removed",
            "removed": removed_items,
            "remote_revoked": revoked_count > 0,
            "remaining_count": len(entries),
            "message": f"Desconectado do Aton: {', '.join(removed_items)}. {revoke_msg}",
        }

    # -------------------------------------------------------------------------
    # Authenticated API Requests (Data API v3, Analytics API v2 & Upload)
    # -------------------------------------------------------------------------

    def request_data_api(
        self,
        endpoint: str,
        entry_key: str,
        method: str = "GET",
        query_params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        required_operation: str = "read_data",
        operation_name: str = "",
        timeout: int = 15,
    ) -> Tuple[Optional[Dict[str, Any]], str, str]:
        """Execute an authenticated HTTP request against YouTube Data API v3 for a specific channel entry_key."""
        creds, code, msg = self._load_and_validate_entry_credentials(
            entry_key=entry_key,
            required_operation=required_operation,
        )
        if creds is None:
            return None, code, msg

        base_url = f"https://www.googleapis.com/youtube/v3/{endpoint.lstrip('/')}"
        if query_params:
            clean_params = {k: v for k, v in query_params.items() if v is not None}
            url = f"{base_url}?{urllib.parse.urlencode(clean_params)}"
        else:
            url = base_url

        headers: Dict[str, str] = {"Authorization": f"Bearer {creds.token}"}
        body_bytes: Optional[bytes] = None
        if json_body is not None:
            headers["Content-Type"] = "application/json; charset=utf-8"
            body_bytes = json.dumps(json_body, ensure_ascii=False).encode("utf-8")

        req = urllib.request.Request(url, data=body_bytes, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                if not raw.strip():
                    return {}, "success", "OK"
                return json.loads(raw), "success", "OK"
        except urllib.error.HTTPError as http_err:
            slug, err_msg, should_inv = classify_youtube_http_error(
                http_err,
                api_source="data_v3",
                operation_name=operation_name or endpoint,
            )
            if should_inv:
                self.invalidate_entry_token(entry_key)
            return None, slug, err_msg
        except Exception as exc:
            return None, "network_error", f"Erro de rede ao consultar YouTube Data API v3 ({endpoint}): {exc}"

    def request_analytics_api(
        self,
        entry_key: str,
        query_params: Dict[str, Any],
        timeout: int = 15,
    ) -> Tuple[Optional[Dict[str, Any]], str, str]:
        """Execute an authenticated HTTP GET against YouTube Analytics API v2 (reports.query)."""
        creds, code, msg = self._load_and_validate_entry_credentials(
            entry_key=entry_key,
            required_operation="read_analytics",
        )
        if creds is None:
            return None, code, msg

        clean_params = {k: v for k, v in query_params.items() if v is not None}
        url = f"https://youtubeanalytics.googleapis.com/v2/reports?{urllib.parse.urlencode(clean_params)}"
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {creds.token}"},
            method="GET",
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data, "success", "OK"
        except urllib.error.HTTPError as http_err:
            slug, err_msg, should_inv = classify_youtube_http_error(
                http_err,
                api_source="analytics_v2",
                operation_name="youtubeAnalytics.reports.query",
            )
            if should_inv:
                self.invalidate_entry_token(entry_key)
            return None, slug, err_msg
        except Exception as exc:
            return None, "network_error", f"Erro de rede ao consultar YouTube Analytics API v2: {exc}"

    def upload_video_resumable(
        self,
        entry_key: str,
        file_path: Path,
        body_metadata: Dict[str, Any],
        timeout: int = 120,
    ) -> Tuple[Optional[Dict[str, Any]], str, str]:
        """Upload a video file via YouTube Data API v3 resumable upload protocol."""
        creds, code, msg = self._load_and_validate_entry_credentials(
            entry_key=entry_key,
            required_operation="upload_videos",
        )
        if creds is None:
            return None, code, msg

        if not file_path.exists() or not file_path.is_file():
            return None, "file_not_found", f"Arquivo de vídeo não encontrado em '{file_path}'."

        file_size = file_path.stat().st_size
        init_url = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
        meta_bytes = json.dumps(body_metadata, ensure_ascii=False).encode("utf-8")

        init_headers = {
            "Authorization": f"Bearer {creds.token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Length": str(file_size),
            "X-Upload-Content-Type": "video/*",
        }
        init_req = urllib.request.Request(init_url, data=meta_bytes, headers=init_headers, method="POST")

        try:
            with urllib.request.urlopen(init_req, timeout=30) as init_resp:
                upload_url = init_resp.headers.get("Location")
                if not upload_url:
                    raw_resp = init_resp.read().decode("utf-8", errors="ignore")
                    if raw_resp.strip():
                        return json.loads(raw_resp), "success", "OK"
                    return None, "upload_init_failed", "A API do YouTube não retornou a URL de sessão de upload (Location)."
        except urllib.error.HTTPError as http_err:
            slug, err_msg, should_inv = classify_youtube_http_error(
                http_err, api_source="data_v3", operation_name="videos.insert"
            )
            if should_inv:
                self.invalidate_entry_token(entry_key)
            return None, slug, err_msg
        except Exception as exc:
            return None, "network_error", f"Falha ao iniciar sessão de upload no YouTube: {exc}"

        # Perform binary upload to the resumable session URL
        try:
            video_bytes = file_path.read_bytes()
            put_headers = {
                "Authorization": f"Bearer {creds.token}",
                "Content-Length": str(len(video_bytes)),
                "Content-Type": "video/*",
            }
            put_req = urllib.request.Request(upload_url, data=video_bytes, headers=put_headers, method="PUT")
            with urllib.request.urlopen(put_req, timeout=timeout) as put_resp:
                resp_data = json.loads(put_resp.read().decode("utf-8"))
                return resp_data, "success", "OK"
        except urllib.error.HTTPError as http_err:
            slug, err_msg, should_inv = classify_youtube_http_error(
                http_err, api_source="data_v3", operation_name="videos.insert"
            )
            if should_inv:
                self.invalidate_entry_token(entry_key)
            return None, slug, err_msg
        except Exception as exc:
            return None, "network_error", f"Erro durante transferência do arquivo de vídeo para o YouTube: {exc}"

    # -------------------------------------------------------------------------
    # Passive Connection Check & Target Channel Discovery Verification
    # -------------------------------------------------------------------------

    def check_connection_and_channels(self, account: Optional[str] = None) -> Dict[str, Any]:
        """Passively verify all connected accounts and channels, refreshing stats and checking UCYCmXtIR-tbWCyrwbLdczyA.

        NEVER opens a browser. Isolates per-channel failures so healthy channels are always returned.
        """
        entries = self._load_channels_index()
        if not entries:
            return {
                "status": "not_authenticated",
                "connected_accounts": [],
                "channels": [],
                "target_channel_check": {
                    "channel_id": KNOWN_TARGET_CHANNEL_IDS[0],
                    "authorized": False,
                    "message": (
                        f"O canal {KNOWN_TARGET_CHANNEL_IDS[0]} ainda não está acessível porque nenhuma conta foi conectada."
                    ),
                },
                "message": (
                    "Nenhuma conta do YouTube está conectada ao Aton. "
                    "Execute 'run.bat youtube-auth cursopb@gmail.com' e 'run.bat youtube-auth servpb@gmail.com'."
                ),
            }

        aq = account.strip().lower() if account and account.strip() else None
        channels_report: List[Dict[str, Any]] = []
        unlinked_accounts: List[Dict[str, Any]] = []
        failed_entries: List[Dict[str, Any]] = []
        connected_emails_set = set()
        authorized_channel_ids = set()

        for entry_key, meta in sorted(entries.items()):
            if not isinstance(meta, dict):
                continue
            acc_email = str(meta.get("account_email", "")).strip().lower()
            if aq and acc_email != aq and acc_email.split("@")[0] != aq:
                continue

            chan_id = str(meta.get("channel_id", "unlinked")).strip()
            if chan_id == "unlinked":
                creds, code, msg = self._load_and_validate_entry_credentials(entry_key, required_operation="read_data")
                if creds is not None:
                    connected_emails_set.add(acc_email)
                    # Try to discover channels now in case YouTube Data API v3 was just enabled
                    disc_chans, disc_code, _ = self._discover_mine_channels_with_token(getattr(creds, "token", "") or "")
                    if disc_chans and disc_code == "success":
                        for ch in disc_chans:
                            actual_id = ch["channel_id"]
                            authorized_channel_ids.add(actual_id)
                            self._save_channel_entry_token(
                                creds=creds,
                                account_email=acc_email,
                                channel_info=ch,
                                access_mode=str(meta.get("access_mode", "manage")),
                                scopes=meta.get("scopes", YOUTUBE_MANAGE_SCOPES),
                            )
                            channels_report.append({
                                "channel_id": actual_id,
                                "title": ch["title"],
                                "custom_url": ch["custom_url"],
                                "account_email": acc_email,
                                "access_mode": meta.get("access_mode", "manage"),
                                "subscriber_count": ch["subscriber_count"],
                                "video_count": ch["video_count"],
                                "view_count": ch["view_count"],
                                "status": "connected",
                            })
                        entries = self._load_channels_index()
                        if entry_key in entries:
                            del entries[entry_key]
                            self._save_channels_index(entries)
                        continue
                    unlinked_accounts.append({
                        "account_email": acc_email,
                        "access_mode": meta.get("access_mode", "manage"),
                        "status": "authenticated_no_channels",
                        "message": "Conta autenticada, mas sem canal retornado por channels.list(mine=True).",
                    })
                else:
                    failed_entries.append({
                        "entry_key": entry_key,
                        "account_email": acc_email,
                        "channel_id": chan_id,
                        "status": code,
                        "message": msg,
                    })
                continue

            data, code, msg = self.request_data_api(
                "channels",
                entry_key=entry_key,
                query_params={"part": "snippet,statistics,contentDetails,status", "mine": "true"},
                required_operation="read_data",
                operation_name="channels.list",
            )
            if data is not None and code == "success":
                items = data.get("items", [])
                matched_item = None
                for it in items:
                    if str(it.get("id", "")).strip() == chan_id:
                        matched_item = it
                        break
                if matched_item is None and items:
                    matched_item = items[0]

                if matched_item is not None:
                    parsed_ch = self._parse_channel_item(matched_item)
                    actual_id = parsed_ch["channel_id"]
                    connected_emails_set.add(acc_email)
                    authorized_channel_ids.add(actual_id)

                    # Update cached stats in index
                    meta["channel_title"] = parsed_ch["title"]
                    meta["custom_url"] = parsed_ch["custom_url"]
                    meta["subscriber_count"] = parsed_ch["subscriber_count"]
                    meta["video_count"] = parsed_ch["video_count"]
                    meta["view_count"] = parsed_ch["view_count"]
                    meta["status"] = "connected"
                    meta["updated_at"] = datetime.now(timezone.utc).isoformat()

                    channels_report.append({
                        "channel_id": actual_id,
                        "title": parsed_ch["title"],
                        "custom_url": parsed_ch["custom_url"],
                        "account_email": acc_email,
                        "access_mode": meta.get("access_mode", "manage"),
                        "subscriber_count": parsed_ch["subscriber_count"],
                        "video_count": parsed_ch["video_count"],
                        "view_count": parsed_ch["view_count"],
                        "status": "connected",
                    })
                else:
                    failed_entries.append({
                        "entry_key": entry_key,
                        "account_email": acc_email,
                        "channel_id": chan_id,
                        "status": "channel_not_in_mine",
                        "message": f"O token de '{acc_email}' está válido, mas o canal '{chan_id}' não foi retornado em mine=True.",
                    })
            else:
                failed_entries.append({
                    "entry_key": entry_key,
                    "account_email": acc_email,
                    "channel_id": chan_id,
                    "channel_title": meta.get("channel_title", chan_id),
                    "status": code,
                    "message": msg,
                })

        self._save_channels_index(entries)

        # Explicitly check target channel UCYCmXtIR-tbWCyrwbLdczyA
        target_id = KNOWN_TARGET_CHANNEL_IDS[0]
        if target_id in authorized_channel_ids:
            matched_target = next((c for c in channels_report if c["channel_id"] == target_id), {})
            target_check = {
                "channel_id": target_id,
                "authorized": True,
                "title": matched_target.get("title", ""),
                "account_email": matched_target.get("account_email", ""),
                "message": (
                    f"Canal '{matched_target.get('title', target_id)}' ({target_id}) está autenticado e autorizado "
                    f"pela conta {matched_target.get('account_email', '')}."
                ),
            }
        else:
            pub_meta, pub_code, _ = self.fetch_public_channel_metadata(target_id)
            if pub_meta and pub_code == "success":
                target_check = {
                    "channel_id": target_id,
                    "authorized": False,
                    "public_title": pub_meta.get("title", ""),
                    "public_custom_url": pub_meta.get("custom_url", ""),
                    "public_subscriber_count": pub_meta.get("subscriber_count", 0),
                    "message": (
                        f"O canal público '{pub_meta.get('title', '')}' ({target_id}) existe no YouTube, "
                        "mas NÃO está autorizado por nenhum dos tokens atualmente conectados. "
                        "Para gerenciá-lo, execute 'run.bat youtube-auth <email>' e selecione a identidade/Conta de Marca desse canal."
                    ),
                }
            else:
                target_check = {
                    "channel_id": target_id,
                    "authorized": False,
                    "message": (
                        f"O canal {target_id} ainda não está autorizado nas credenciais conectadas "
                        "(execute 'run.bat youtube-auth <email>' e selecione a identidade correspondente se sua conta tiver acesso a ele)."
                    ),
                }

        overall_status = "connected" if (channels_report or unlinked_accounts) else "not_authenticated"
        parts_msg: List[str] = []
        if channels_report:
            ch_list_str = "; ".join(
                f"'{c['title']}' [{c['channel_id']}] (conta {c['account_email']}, modo {c['access_mode']}, "
                f"{c['subscriber_count']} inscritos, {c['video_count']} vídeos)"
                for c in channels_report
            )
            parts_msg.append(f"{len(channels_report)} canal(is) autenticado(s): {ch_list_str}.")
        if unlinked_accounts:
            unl_str = ", ".join(u["account_email"] for u in unlinked_accounts)
            parts_msg.append(f"Conta(s) sem canal retornado em mine=True: {unl_str}.")
        if failed_entries:
            fail_str = ", ".join(
                f"{f.get('channel_title', f.get('channel_id'))} ({f.get('account_email')}: {f.get('status')})"
                for f in failed_entries
            )
            parts_msg.append(f"Pendências de reconexão: {fail_str}.")
        parts_msg.append(target_check["message"])

        return {
            "status": overall_status,
            "connected_accounts": sorted(connected_emails_set),
            "channels": channels_report,
            "unlinked_accounts": unlinked_accounts,
            "failed_entries": failed_entries,
            "target_channel_check": target_check,
            "message": " ".join(parts_msg),
        }


# Shared singleton instance
_default_youtube_service: Optional[YouTubeConnectionService] = None


def get_youtube_service() -> YouTubeConnectionService:
    """Return the shared YouTubeConnectionService singleton instance."""
    global _default_youtube_service
    if _default_youtube_service is None:
        _default_youtube_service = YouTubeConnectionService()
    return _default_youtube_service
