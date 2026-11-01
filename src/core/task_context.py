"""Structured task context and result verification manager for Aton."""

import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

VALID_TASK_STATES = {
    "aguardando_esclarecimento",
    "pronta",
    "executando",
    "verificando",
    "concluida",
    "inconclusiva",
    "falhou",
    "cancelada",
}

VALID_TRANSPORT_STATES = {
    "not_sent",
    "sent_confirmed",
    "sent_uncertain",
}

VALID_VERIFICATION_STATES = {
    "unverified",
    "confirmed",
    "inconclusive",
    "failed",
}

ORDINAL_MAP = {
    "primeiro": 0,
    "primeira": 0,
    "1": 0,
    "1º": 0,
    "1ª": 0,
    "um": 0,
    "uma": 0,
    "opção 1": 0,
    "opcao 1": 0,
    "número 1": 0,
    "numero 1": 0,
    "segundo": 1,
    "segunda": 1,
    "2": 1,
    "2º": 1,
    "2ª": 1,
    "dois": 1,
    "duas": 1,
    "opção 2": 1,
    "opcao 2": 1,
    "número 2": 1,
    "numero 2": 1,
    "terceiro": 2,
    "terceira": 2,
    "3": 2,
    "3º": 2,
    "3ª": 2,
    "três": 2,
    "tres": 2,
    "opção 3": 2,
    "opcao 3": 2,
    "número 3": 2,
    "numero 3": 2,
    "quarto": 3,
    "quarta": 3,
    "4": 3,
    "4º": 3,
    "4ª": 3,
    "quatro": 3,
    "quinto": 4,
    "quinta": 4,
    "5": 4,
    "5º": 4,
    "5ª": 4,
    "cinco": 4,
}


@dataclass
class TaskContext:
    """Represents a bounded, temporary user task during conversation."""

    task_id: str
    summary: str
    state: str = "pronta"
    target: Optional[str] = None
    current_step: str = "compreendido"
    current_request: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    references: Dict[str, Any] = field(default_factory=dict)
    pending_clarification: Optional[str] = None
    pending_action: Optional[Dict[str, Any]] = None
    last_action_id: Optional[str] = None
    last_action: Optional[str] = None
    last_result: Optional[Dict[str, Any]] = None
    transport_state: str = "not_sent"
    verification_state: str = "unverified"
    evidence: Optional[Dict[str, Any]] = None
    evidence_timestamp: Optional[float] = None
    is_cancelled: bool = False
    cancellation_reason: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def target_label(self) -> str:
        if self.target == "fire_tv":
            return "Fire Stick"
        if self.target == "pc":
            return "computador"
        if self.target in ("tv", "smart_tv"):
            return "televisão"
        return "dispositivo"

    def to_dict(self) -> Dict[str, Any]:
        """Convert task context to a safe, sanitised dictionary."""
        return {
            "task_id": self.task_id,
            "summary": self.summary,
            "state": self.state,
            "target": self.target,
            "target_label": self.target_label,
            "current_step": self.current_step,
            "current_request": self.current_request,
            "parameters": self.parameters,
            "references": self.references,
            "pending_clarification": self.pending_clarification,
            "transport_state": self.transport_state,
            "verification_state": self.verification_state,
            "evidence": self.evidence,
            "evidence_timestamp": self.evidence_timestamp,
            "is_cancelled": self.is_cancelled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class TaskContextManager:
    """Manages session-scoped destination and structured tasks with verification.

    Acts as the single source of truth for both target context (PC, Fire TV)
    and physical task execution state.
    """

    def __init__(self, timeout_seconds: float = 60.0):
        self.timeout_seconds = timeout_seconds
        self._current_target: Optional[str] = None
        self._last_updated: float = 0.0
        self._pending_clarification: Optional[str] = None
        self._pending_action: Optional[Dict[str, Any]] = None

        # Active single task
        self._active_task: Optional[TaskContext] = None
        self._last_completed_task: Optional[TaskContext] = None

    # --- Target Management (Backward Compatible) ---

    def set_target(self, target: str) -> None:
        """Set or update the active destination target (pc, fire_tv, smart_tv)."""
        valid_targets = {"pc", "fire_tv", "smart_tv"}
        normalized = target.strip().lower()
        if normalized in valid_targets:
            self._current_target = normalized
            self._last_updated = time.time()
            self._pending_clarification = None
            if self._active_task and not self._active_task.is_cancelled:
                self._active_task.target = normalized
                self._active_task.updated_at = time.time()

    def get_active_target(self) -> Optional[str]:
        """Return the active target if within timeout, or None if expired."""
        if self._current_target and (time.time() - self._last_updated <= self.timeout_seconds):
            return self._current_target
        self._current_target = None
        return None

    def set_pending_action(self, action_type: str, params: Dict[str, Any]) -> None:
        """Save a blocked ambiguous action waiting for destination clarification."""
        self._pending_action = {
            "action_type": action_type,
            "params": params,
            "timestamp": time.time(),
        }
        self._last_updated = time.time()

        if self._active_task and not self._active_task.is_cancelled:
            self._active_task.state = "aguardando_esclarecimento"
            self._active_task.pending_clarification = "destination"
            self._active_task.pending_action = self._pending_action
            self._active_task.updated_at = time.time()

    def get_pending_action(self) -> Optional[Dict[str, Any]]:
        """Return pending action if within timeout window."""
        if self._pending_action and (time.time() - self._pending_action.get("timestamp", 0) <= self.timeout_seconds):
            return self._pending_action
        self._pending_action = None
        return None

    def clear_pending_action(self) -> None:
        """Clear pending action once resolved or discarded."""
        self._pending_action = None
        if self._active_task:
            self._active_task.pending_action = None

    def set_pending_clarification(self, action_hint: str) -> None:
        """Record a pending clarification query to preserve context until answered."""
        self._pending_clarification = action_hint
        self._last_updated = time.time()

    def get_pending_clarification(self) -> Optional[str]:
        """Return pending clarification if within timeout window."""
        if self._pending_clarification and (time.time() - self._last_updated <= self.timeout_seconds):
            return self._pending_clarification
        self._pending_clarification = None
        return None

    # --- Structured Task Management ---

    def start_task(
        self,
        summary: str,
        target: Optional[str] = None,
        request: str = "",
        parameters: Optional[Dict[str, Any]] = None,
    ) -> TaskContext:
        """Initialize or start a new task context, superseding any prior task."""
        # Cleanly wrap prior active task
        if self._active_task and not self._active_task.is_cancelled:
            if self._active_task.state in ("executando", "verificando"):
                self._active_task.state = "concluida"
            self._last_completed_task = None

        effective_target = target or self.get_active_target()
        task_id = f"task_{int(time.time())}_{uuid.uuid4().hex[:6]}"

        task = TaskContext(
            task_id=task_id,
            summary=summary,
            state="pronta",
            target=effective_target,
            current_step="compreendido",
            current_request=request or summary,
            parameters=parameters or {},
            references={},
            transport_state="not_sent",
            verification_state="unverified",
            created_at=time.time(),
            updated_at=time.time(),
        )

        self._active_task = task
        self._last_updated = time.time()
        return task

    def get_active_task(self) -> Optional[TaskContext]:
        """Return currently active task if not timed out."""
        if self._active_task and (time.time() - self._active_task.updated_at <= self.timeout_seconds):
            return self._active_task
        return None

    def get_latest_task_or_completed(self) -> Optional[TaskContext]:
        """Return active task or most recently completed task for follow-up questions."""
        active = self.get_active_task()
        if active:
            return active
        if self._last_completed_task and (time.time() - self._last_completed_task.updated_at <= self.timeout_seconds * 2):
            return self._last_completed_task
        return None

    def record_action_planned(self, action_name: str, params: Optional[Dict[str, Any]] = None) -> Tuple[str, str]:
        """Record planned physical action and generate a unique action_id."""
        task = self.get_active_task()
        if not task:
            task = self.start_task(summary=f"Executar {action_name}", parameters=params)

        action_id = f"act_{int(time.time() * 1000) % 1000000}_{uuid.uuid4().hex[:4]}"
        task.last_action_id = action_id
        task.last_action = action_name
        task.state = "executando"
        task.current_step = "acao_planejada"
        task.transport_state = "not_sent"
        task.updated_at = time.time()
        self._last_updated = time.time()
        return task.task_id, action_id

    def record_transport_result(
        self,
        task_id: str,
        action_id: str,
        transport_state: str,
        message: Optional[str] = None,
    ) -> bool:
        """Update transport delivery state (not_sent, sent_confirmed, sent_uncertain)."""
        task = self.get_active_task()
        if not task or task.task_id != task_id or task.is_cancelled:
            logger.debug(f"Ignorando resultado de transporte para task_id {task_id} (inativo ou cancelado).")
            return False

        if transport_state in VALID_TRANSPORT_STATES:
            task.transport_state = transport_state

        task.current_step = "comando_enviado" if transport_state == "sent_confirmed" else "falha_transporte"
        task.updated_at = time.time()
        self._last_updated = time.time()
        return True

    def record_verification_result(
        self,
        task_id: str,
        action_id: str,
        verification_state: str,
        evidence: Optional[Dict[str, Any]] = None,
        result_payload: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Record observed verification state (confirmed, inconclusive, failed, unverified)."""
        task = self.get_active_task()
        if not task or task.task_id != task_id or task.is_cancelled:
            logger.debug(f"Ignorando verificação para task_id {task_id} (inativo ou cancelado).")
            return False

        if verification_state in VALID_VERIFICATION_STATES:
            task.verification_state = verification_state

        if evidence is not None:
            task.evidence = evidence
            task.evidence_timestamp = time.time()

        if result_payload is not None:
            task.last_result = result_payload

        # Map to overall task state
        if verification_state == "confirmed":
            task.state = "concluida"
            task.current_step = "resultado_confirmado"
        elif verification_state == "inconclusive":
            task.state = "inconclusiva"
            task.current_step = "resultado_inconclusivo"
        elif verification_state == "failed":
            task.state = "falhou"
            task.current_step = "resultado_falhou"
        else:
            task.state = "concluida" if task.transport_state == "sent_confirmed" else "inconclusiva"

        task.updated_at = time.time()
        self._last_updated = time.time()
        return True

    def set_pending_candidates(
        self,
        candidates: List[Dict[str, Any]],
        context_hint: str = "music_selection",
    ) -> None:
        """Store ordered list of presented candidates linked to active task."""
        task = self.get_active_task()
        if not task:
            task = self.start_task(summary="Seleção de opções")

        stored_candidates = []
        for idx, item in enumerate(candidates):
            c_dict = dict(item)
            c_dict["index"] = idx
            c_dict["task_id"] = task.task_id
            stored_candidates.append(c_dict)

        task.references["candidates"] = stored_candidates
        task.references["candidate_type"] = context_hint
        task.state = "aguardando_esclarecimento"
        task.pending_clarification = "choice"
        task.updated_at = time.time()
        self._last_updated = time.time()

    def resolve_ordinal_choice(
        self,
        choice_text: str,
    ) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """Resolve spoken ordinal selection against candidates actually presented in the current task."""
        task = self.get_active_task()
        if not task or not task.references.get("candidates"):
            return False, None, "Nenhuma lista de opções pendente de escolha para esta tarefa, senhor."

        if task.is_cancelled:
            return False, None, "A tarefa anterior foi cancelada. Por favor, faça um novo pedido."

        norm = choice_text.strip().lower()
        # Clean common prefixes like 'a ', 'o ', 'escolho a '
        norm_clean = re.sub(r"^(escolho|coloque|toca|toque|quero|seleciono|a|o)\s+", "", norm).strip()

        matched_index: Optional[int] = None
        for pattern, idx in ORDINAL_MAP.items():
            if norm == pattern or norm_clean == pattern or pattern in norm.split():
                matched_index = idx
                break

        # Check explicit digit in text
        if matched_index is None:
            m = re.search(r"\b([1-9])\b", norm)
            if m:
                matched_index = int(m.group(1)) - 1

        if matched_index is None:
            return False, None, f"Não compreendi a escolha '{choice_text}'. Diga 'a primeira', 'a segunda' ou o título desejado."

        candidates = task.references.get("candidates", [])
        if 0 <= matched_index < len(candidates):
            chosen = candidates[matched_index]
            task.references["last_choice"] = chosen
            task.pending_clarification = None
            task.state = "pronta"
            task.updated_at = time.time()
            self._last_updated = time.time()
            return True, chosen, f"Opção selecionada: '{chosen.get('title', 'Item selecionado')}'."
        else:
            total = len(candidates)
            return (
                False,
                None,
                f"Opção {matched_index + 1} inválida. Apresentei apenas {total} opções. Qual o senhor prefere?",
            )

    def is_action_allowed(self, task_id: Optional[str] = None) -> bool:
        """Check whether physical execution is allowed before initiating any step."""
        if task_id:
            if self._active_task and self._active_task.task_id == task_id:
                return not self._active_task.is_cancelled
            if self._last_completed_task and self._last_completed_task.task_id == task_id:
                return False
            return False

        if self._active_task is not None:
            return not self._active_task.is_cancelled

        return True

    def cancel_active_task(self, reason: str = "Cancelado pelo usuário") -> Dict[str, Any]:
        """Cancel active task, preventing subsequent physical steps."""
        task = self.get_active_task()
        if not task:
            return {
                "status": "cancelled",
                "action_already_sent": False,
                "message": "Nenhuma tarefa em andamento para cancelar.",
            }

        task.is_cancelled = True
        task.state = "cancelada"
        task.cancellation_reason = reason
        task.current_step = "cancelado"
        task.updated_at = time.time()

        was_sent = task.transport_state in ("sent_confirmed", "sent_uncertain")
        action_name = task.last_action or "ação"

        if was_sent:
            msg = (
                f"Tarefa cancelada. O comando para '{action_name}' já havia sido enviado ao {task.target_label}, "
                "mas interrompi as próximas etapas."
            )
        else:
            msg = f"Tarefa para '{action_name}' cancelada antes do envio de qualquer comando físico."

        return {
            "status": "cancelled",
            "task_id": task.task_id,
            "action_already_sent": was_sent,
            "message": msg,
        }

    def clear_on_sleep(self) -> None:
        """Cleanly clear active target and task state when assistant returns to sleep."""
        if self._active_task and not self._active_task.is_cancelled:
            # Mark cancelled so no late background worker executes actions
            self._active_task.is_cancelled = True
            self._last_completed_task = None

        self._active_task = None
        self._current_target = None
        self._last_updated = 0.0
        self._pending_clarification = None
        self._pending_action = None

    def clear(self) -> None:
        """Full reset (backward compatible)."""
        self.clear_on_sleep()


_global_task_context_manager: Optional[TaskContextManager] = None


def get_task_context() -> TaskContextManager:
    """Provide singleton instance of TaskContextManager."""
    global _global_task_context_manager
    if _global_task_context_manager is None:
        _global_task_context_manager = TaskContextManager()
    return _global_task_context_manager


# Alias for backward compatibility with existing get_target_context
get_target_context = get_task_context
