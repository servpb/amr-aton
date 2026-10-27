"""Device authorization and security manager for ATON multi-device network (Phase 11)."""

from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import secrets
import sqlite3
import time
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid

from src.config import settings

logger = logging.getLogger(__name__)

# Valid granular permissions
VALID_PERMISSIONS = {
    "commands",  # General voice/text commands, tools like weather, briefing, calendar
    "audio",     # Audio streaming in/out
    "screen",    # Screen capture, inspection, reading content
    "files",     # File reading, writing, document generation
    "control",   # OS interaction, shortcuts, mouse, typing, volume, app termination
}

# Mapping of tools to their required permission
TOOL_PERMISSION_MAP: Dict[str, str] = {
    # Screen perception tools
    "descrever_tela": "screen",
    "ler_conteudo_tela": "screen",
    "localizar_e_clicar_elemento": "screen",
    "preencher_campo_na_tela": "screen",
    "rolar_tela": "screen",
    # OS Control & Automation tools
    "close_application": "control",
    "type_text_in_active_window": "control",
    "send_keyboard_shortcut": "control",
    "focus_application_window": "control",
    "set_system_volume": "control",
    "control_system_media": "control",
    # File tools
    "create_and_open_document": "files",
}


class DeviceManager:
    """Manages secure device pairing, PIN validation, cryptographic tokens, and permissions."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.devices_db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Create and return a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Initialize tables for paired devices and temporary pairing requests."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Paired devices table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS aton_paired_devices (
                    device_id TEXT PRIMARY KEY,
                    device_name TEXT NOT NULL,
                    device_type TEXT NOT NULL,
                    last_ip TEXT NOT NULL,
                    permissions TEXT NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL DEFAULT 'active',
                    paired_at TEXT NOT NULL,
                    last_active_at TEXT NOT NULL
                )
                """
            )
            # Pending pairing requests table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS aton_pairing_requests (
                    request_id TEXT PRIMARY KEY,
                    client_ip TEXT NOT NULL,
                    device_name TEXT NOT NULL,
                    device_type TEXT NOT NULL,
                    pin_code TEXT NOT NULL,
                    requested_permissions TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def request_pairing(
        self,
        client_ip: str,
        device_name: str,
        device_type: str = "mobile",
        requested_permissions: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Create a new pairing request with a 6-digit one-time PIN and limited validity.

        Args:
            client_ip: IP address of the requesting client device.
            device_name: Friendly name (e.g., 'Galaxy S24', 'LG WebOS TV').
            device_type: One of 'mobile', 'desktop', 'tv', 'other'.
            requested_permissions: List of permissions requested (defaults to commands and audio).

        Returns:
            Dict containing request_id, pin_code, expires_at, and status.
        """
        request_id = str(uuid.uuid4())
        # Secure 6-digit numerical PIN code (100000 - 999999)
        pin_code = str(secrets.randbelow(900000) + 100000)
        expires_at = time.time() + settings.pairing_pin_expiry_seconds
        now_iso = datetime.now(timezone.utc).isoformat()

        # Sanitize requested permissions
        perms = requested_permissions or ["commands", "audio"]
        perms_json = json.dumps(list(set(perms) & VALID_PERMISSIONS) or ["commands"])

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO aton_pairing_requests (
                    request_id, client_ip, device_name, device_type,
                    pin_code, requested_permissions, expires_at, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (request_id, client_ip, device_name, device_type, pin_code, perms_json, expires_at, now_iso),
            )
            conn.commit()

        logger.info(
            f"🔐 [Pareamento ATON] Nova solicitação de '{device_name}' ({device_type}) no IP {client_ip}. "
            f"PIN gerado: {pin_code} (Válido por {settings.pairing_pin_expiry_seconds // 60} minutos)."
        )

        return {
            "request_id": request_id,
            "pin_code": pin_code,
            "expires_at": expires_at,
            "expires_in_seconds": settings.pairing_pin_expiry_seconds,
            "device_name": device_name,
            "device_type": device_type,
            "client_ip": client_ip,
            "status": "pending",
        }

    def confirm_pairing(
        self,
        request_id: str,
        pin_code: Optional[str] = None,
        granted_permissions: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Validate pairing request, verify PIN, and generate a long-lived auth token.

        Args:
            request_id: The ID of the pending pairing request.
            pin_code: The PIN entered by the client (optional if confirmed by host UI).
            granted_permissions: Specific permissions to grant (overrides requested if provided).

        Returns:
            Dict with token, device_id, device_name, and permissions if approved, else None.
        """
        now = time.time()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM aton_pairing_requests WHERE request_id = ? AND status = 'pending'",
                (request_id,),
            )
            row = cursor.fetchone()

            if not row:
                logger.warning(f"Solicitação de pareamento {request_id} não encontrada ou já finalizada.")
                return None

            if row["expires_at"] < now:
                cursor.execute(
                    "UPDATE aton_pairing_requests SET status = 'expired' WHERE request_id = ?",
                    (request_id,),
                )
                conn.commit()
                logger.warning(f"Solicitação de pareamento {request_id} expirou.")
                return None

            if pin_code is not None:
                cleaned_pin = str(pin_code).replace(" ", "").replace("-", "").strip()
                if cleaned_pin != row["pin_code"]:
                    logger.warning(f"PIN incorreto ({cleaned_pin}) para a solicitação {request_id}.")
                    return None

            # Generate unique device secret token (256-bit entropy)
            raw_token = f"aton_{secrets.token_urlsafe(32)}"
            token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
            device_id = str(uuid.uuid4())

            # Determine permissions
            if granted_permissions is not None:
                effective_perms = list(set(granted_permissions) & VALID_PERMISSIONS)
            else:
                try:
                    effective_perms = json.loads(row["requested_permissions"])
                except Exception:
                    effective_perms = ["commands", "audio"]

            if not effective_perms:
                effective_perms = ["commands"]

            now_iso = datetime.now(timezone.utc).isoformat()
            cursor.execute(
                """
                INSERT INTO aton_paired_devices (
                    device_id, device_name, device_type, last_ip,
                    permissions, token_hash, status, paired_at, last_active_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)
                """,
                (
                    device_id,
                    row["device_name"],
                    row["device_type"],
                    row["client_ip"],
                    json.dumps(effective_perms),
                    token_hash,
                    now_iso,
                    now_iso,
                ),
            )
            # Mark request as approved
            cursor.execute(
                "UPDATE aton_pairing_requests SET status = 'approved' WHERE request_id = ?",
                (request_id,),
            )
            conn.commit()

            logger.info(
                f"✅ Dispositivo pareado com sucesso: '{row['device_name']}' ({device_id}) "
                f"Permissões: {effective_perms}"
            )

            return {
                "token": raw_token,
                "device_id": device_id,
                "device_name": row["device_name"],
                "device_type": row["device_type"],
                "permissions": effective_perms,
                "paired_at": now_iso,
            }

    def validate_token(
        self,
        token: str,
        required_permission: Optional[str] = None,
        client_ip: Optional[str] = None,
    ) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """Validate bearer token and verify granular permissions.

        Returns:
            Tuple of (is_valid, device_dict, error_message)
        """
        if not token:
            return False, None, "Token de autenticação não fornecido."

        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM aton_paired_devices WHERE token_hash = ? AND status = 'active'",
                (token_hash,),
            )
            row = cursor.fetchone()

            if not row:
                return False, None, "Dispositivo não autorizado ou token revogado."

            try:
                device_perms = set(json.loads(row["permissions"]))
            except Exception:
                device_perms = set()

            # Check granular permission if required
            if required_permission:
                if required_permission not in device_perms and "all" not in device_perms:
                    return (
                        False,
                        dict(row),
                        f"Permissão negada. Este dispositivo não possui a permissão '{required_permission}'.",
                    )

            # Update last activity timestamp and IP
            now_iso = datetime.now(timezone.utc).isoformat()
            if client_ip:
                cursor.execute(
                    "UPDATE aton_paired_devices SET last_active_at = ?, last_ip = ? WHERE device_id = ?",
                    (now_iso, client_ip, row["device_id"]),
                )
            else:
                cursor.execute(
                    "UPDATE aton_paired_devices SET last_active_at = ? WHERE device_id = ?",
                    (now_iso, row["device_id"]),
                )
            conn.commit()

            device_data = dict(row)
            device_data.pop("token_hash", None)
            device_data["permissions"] = list(device_perms)
            return True, device_data, "OK"

    def list_devices(self) -> List[Dict[str, Any]]:
        """List all paired devices without exposing secrets."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM aton_paired_devices ORDER BY paired_at DESC")
            rows = cursor.fetchall()
            devices = []
            for r in rows:
                d = dict(r)
                d.pop("token_hash", None)
                try:
                    d["permissions"] = json.loads(d["permissions"])
                except Exception:
                    d["permissions"] = []
                devices.append(d)
            return devices

    def revoke_device(self, identifier: str) -> bool:
        """Revoke device authorization by device_id or device_name.

        Args:
            identifier: Either UUID device_id or friendly name.

        Returns:
            True if device was found and revoked.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE aton_paired_devices 
                SET status = 'revoked' 
                WHERE (device_id = ? OR LOWER(device_name) = LOWER(?)) AND status = 'active'
                """,
                (identifier, identifier),
            )
            affected = cursor.rowcount
            conn.commit()
            if affected > 0:
                logger.info(f"🚫 Dispositivo '{identifier}' revogado com sucesso ({affected} afetado).")
                return True
            return False

    def get_pending_requests(self) -> List[Dict[str, Any]]:
        """Return all active pending pairing requests that have not expired."""
        now = time.time()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT request_id, client_ip, device_name, device_type, pin_code, 
                       requested_permissions, expires_at, created_at 
                FROM aton_pairing_requests 
                WHERE status = 'pending' AND expires_at > ?
                ORDER BY created_at DESC
                """,
                (now,),
            )
            rows = cursor.fetchall()
            requests = []
            for r in rows:
                req = dict(r)
                req["expires_in_seconds"] = max(0, int(req["expires_at"] - now))
                try:
                    req["requested_permissions"] = json.loads(req["requested_permissions"])
                except Exception:
                    req["requested_permissions"] = []
                requests.append(req)
            return requests
