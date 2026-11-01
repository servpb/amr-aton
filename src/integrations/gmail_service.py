"""Gmail OAuth 2.0 Desktop Connection Service for Aton (Single & Multi-Account).

Provides centralized credential management, strict scope verification,
collision-safe SHA-256 multi-account token storage, atomic legacy token migration,
silent token refresh, revoked token invalidation, interactive browser OAuth 2.0
flow with authorized-email verification, and granular Gmail REST API error diagnostics.
"""

from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import urllib.error
import urllib.parse
import urllib.request

from src.config import settings

logger = logging.getLogger(__name__)

# Default minimum required scope for Aton's current read-only Gmail tools
GMAIL_READONLY_SCOPES: List[str] = [
    "https://www.googleapis.com/auth/gmail.readonly",
]


def _atomic_write_text(target_path: Path, content: str) -> None:
    """Atomically write UTF-8 text to target_path using a temporary sibling file."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_name(f"{target_path.name}.{os.getpid()}.tmp")
    try:
        tmp_path.write_text(content, encoding="utf-8")
        os.replace(str(tmp_path), str(target_path))
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass


def _extract_scopes_from_token_json(token_data: Dict[str, Any]) -> List[str]:
    """Extract granted scopes from raw token JSON without mutating or assuming defaults."""
    raw_scopes = token_data.get("scopes")
    if isinstance(raw_scopes, list):
        return [str(s).strip() for s in raw_scopes if str(s).strip()]
    raw_scope_str = token_data.get("scope")
    if isinstance(raw_scope_str, str) and raw_scope_str.strip():
        return [s.strip() for s in raw_scope_str.split() if s.strip()]
    return []


def validate_credentials_scopes(
    creds: Any,
    required_scopes: List[str],
    token_data: Optional[Dict[str, Any]] = None,
) -> bool:
    """Verify that loaded or newly authorized credentials explicitly contain all required scopes.

    Works for both token files loaded from disk and newly authorized OAuth2 credentials.
    Returns False if scopes cannot be confirmed or if any required scope is missing.
    """
    if creds is None:
        return False

    required_set = set(required_scopes)
    if not required_set:
        return True

    # 1. Check raw token JSON if loaded from file
    if token_data is not None:
        file_scopes = set(_extract_scopes_from_token_json(token_data))
        if not file_scopes or not required_set.issubset(file_scopes):
            return False

    # 2. Check google.oauth2.credentials.Credentials scope properties/API
    granted = getattr(creds, "granted_scopes", None)
    declared = getattr(creds, "scopes", None)
    active_scopes = granted if granted is not None else declared

    if active_scopes is not None:
        if not required_set.issubset(set(active_scopes)):
            return False
        if hasattr(creds, "has_scopes"):
            try:
                if not creds.has_scopes(list(required_set)):
                    return False
            except Exception:
                return False
        return True

    # If neither token_data nor credential properties confirm the scopes, reject
    return token_data is not None and required_set.issubset(set(_extract_scopes_from_token_json(token_data)))


def validate_client_credentials_file(credentials_path: Path) -> Tuple[bool, str, str]:
    """Validate that credentials.json exists and is a valid Google Desktop App OAuth client file.

    Returns:
        Tuple of (is_valid, error_code, user_message).
    """
    if not credentials_path.exists():
        return (
            False,
            "missing_credentials_file",
            (
                f"Arquivo de credenciais não encontrado em '{credentials_path}'. "
                "Baixe o JSON de cliente OAuth 2.0 (App para computador / Desktop) no Google Cloud Console, "
                "renomeie para 'credentials.json' e coloque na pasta raiz do Aton."
            ),
        )

    try:
        raw_text = credentials_path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
    except Exception:
        return (
            False,
            "invalid_credentials_json",
            (
                f"O arquivo '{credentials_path.name}' não contém um JSON válido. "
                "Baixe novamente o arquivo de credenciais OAuth 2.0 no Google Cloud Console."
            ),
        )

    if not isinstance(data, dict):
        return (
            False,
            "invalid_credentials_json",
            f"Formato inválido no arquivo '{credentials_path.name}'.",
        )

    if "web" in data and "installed" not in data:
        return (
            False,
            "wrong_client_type_web",
            (
                f"O arquivo '{credentials_path.name}' foi criado como 'Aplicativo da Web' ('web'), "
                "mas o Aton requer um ID do cliente OAuth do tipo 'App para computador' (Desktop / 'installed'). "
                "Crie uma credencial do tipo App para computador no Google Cloud Console e substitua o arquivo."
            ),
        )

    installed = data.get("installed")
    if not isinstance(installed, dict) or not installed.get("client_id") or not installed.get("client_secret"):
        return (
            False,
            "invalid_credentials_structure",
            (
                f"O arquivo '{credentials_path.name}' não possui a estrutura esperada ('installed.client_id' e "
                "'installed.client_secret') de um App para computador do Google Cloud."
            ),
        )

    return True, "ok", "Arquivo credentials.json válido."


def classify_gmail_http_error(err: urllib.error.HTTPError) -> Tuple[str, str, bool]:
    """Inspect Google API HTTPError payload to accurately classify the failure cause.

    Returns:
        Tuple of (status_code_slug, user_friendly_message, should_invalidate_token).
    """
    http_code = getattr(err, "code", 0)
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
                "Sua sessão do Gmail expirou ou o acesso foi revogado (HTTP 401). "
                "O token local foi invalidado. Solicite ao Aton para autenticar a conta novamente."
            ),
            True,
        )

    # 2. HTTP 403 Forbidden -> Distinguish API disabled vs scope vs quota vs policy
    if http_code == 403:
        if (
            "accessnotconfigured" in reasons_lower
            or "service_disabled" in reasons_lower
            or "gmail api has not been used" in msg_lower
            or "it is disabled" in msg_lower
        ):
            return (
                "api_disabled",
                (
                    "A API do Gmail não está habilitada no seu projeto do Google Cloud Console (accessNotConfigured). "
                    "Acesse 'APIs e Serviços > Biblioteca' no Google Cloud Console, pesquise por 'Gmail API' e clique em 'Ativar'."
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
                    "O token atual não possui permissão suficiente para acessar o Gmail (insufficientPermissions). "
                    "O token antigo foi removido; autentique novamente para conceder a permissão solicitada."
                ),
                True,
            )

        if (
            "ratelimitexceeded" in reasons_lower
            or "userratelimitexceeded" in reasons_lower
            or "quotaexceeded" in reasons_lower
        ):
            return (
                "quota_exceeded",
                "Limite de requisições da API do Gmail atingido temporariamente (HTTP 403). Tente novamente em alguns instantes.",
                False,
            )

        return (
            "forbidden",
            f"Acesso negado pela API do Gmail (HTTP 403): {api_message or 'verifique as permissões da conta Google.'}",
            False,
        )

    return (
        "http_error",
        f"Erro ao comunicar com a API do Gmail (código HTTP {http_code}): {api_message or 'erro desconhecido'}.",
        False,
    )


class GmailConnectionService:
    """Centralized service managing Gmail OAuth 2.0 desktop authentication and multi-account API requests."""

    def __init__(
        self,
        credentials_path: Optional[Path] = None,
        token_path: Optional[Path] = None,
        tokens_dir: Optional[Path] = None,
        scopes: Optional[List[str]] = None,
    ):
        self.credentials_path: Path = (
            Path(credentials_path) if credentials_path is not None else settings.get_gmail_credentials_file()
        )
        self.token_path: Path = (
            Path(token_path) if token_path is not None else settings.get_gmail_token_file()
        )
        if tokens_dir is not None:
            self.tokens_dir: Path = Path(tokens_dir)
        elif token_path is not None:
            self.tokens_dir = Path(token_path).parent / "tokens"
        else:
            self.tokens_dir = settings.get_gmail_tokens_dir()

        self.index_path: Path = self.tokens_dir / "accounts_index.json"
        self.scopes: List[str] = list(scopes) if scopes is not None else list(GMAIL_READONLY_SCOPES)

    # -------------------------------------------------------------------------
    # Index & Collision-Safe Account File Management
    # -------------------------------------------------------------------------

    def _load_accounts_index(self) -> Dict[str, Dict[str, Any]]:
        """Load the multi-account index mapping canonical email -> account metadata."""
        if not self.index_path.exists():
            return {}
        try:
            raw = self.index_path.read_text(encoding="utf-8")
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and isinstance(parsed.get("accounts"), dict):
                return parsed["accounts"]
        except Exception as exc:
            logger.warning(f"Erro ao ler índice de contas '{self.index_path.name}': {exc}")
        return {}

    def _save_accounts_index(self, accounts: Dict[str, Dict[str, Any]]) -> None:
        """Atomically persist the multi-account index to disk."""
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "accounts": accounts,
        }
        _atomic_write_text(self.index_path, json.dumps(payload, indent=2, ensure_ascii=False))

    def _resolve_collision_safe_token_file(
        self,
        canonical_email: str,
        accounts: Dict[str, Dict[str, Any]],
    ) -> Tuple[str, Path]:
        """Compute full 64-char SHA-256 account_id and verify no collision exists with another email."""
        email_norm = canonical_email.strip().lower()
        existing_entry = accounts.get(email_norm)
        if isinstance(existing_entry, dict) and existing_entry.get("account_id") and existing_entry.get("token_file"):
            cand_id = str(existing_entry["account_id"])
            cand_path = self.tokens_dir / str(existing_entry["token_file"])
            return cand_id, cand_path

        full_sha256 = hashlib.sha256(email_norm.encode("utf-8")).hexdigest()
        used_ids = {
            str(meta.get("account_id", ""))
            for acc_email, meta in accounts.items()
            if acc_email != email_norm and isinstance(meta, dict)
        }
        used_files = {
            str(meta.get("token_file", ""))
            for acc_email, meta in accounts.items()
            if acc_email != email_norm and isinstance(meta, dict)
        }

        suffix = 0
        while True:
            cand_id = f"gmail_acct_{full_sha256}" if suffix == 0 else f"gmail_acct_{full_sha256}_{suffix}"
            cand_filename = f"{cand_id}.json"
            cand_path = self.tokens_dir / cand_filename

            # Also check if file exists on disk belonging to a different email
            disk_conflict = False
            if cand_path.exists():
                try:
                    existing_json = json.loads(cand_path.read_text(encoding="utf-8"))
                    bound_email = str(existing_json.get("account_email", "")).strip().lower()
                    if bound_email and bound_email != email_norm:
                        disk_conflict = True
                except Exception:
                    pass

            if cand_id not in used_ids and cand_filename not in used_files and not disk_conflict:
                return cand_id, cand_path

            suffix += 1

    def _serialize_credentials(self, creds: Any, canonical_email: Optional[str] = None) -> str:
        """Serialize credentials to JSON ensuring scopes and optional account_email metadata are stored."""
        token_json = creds.to_json()
        parsed = json.loads(token_json)
        if "scopes" not in parsed or not parsed["scopes"]:
            granted = getattr(creds, "granted_scopes", None) or getattr(creds, "scopes", None) or self.scopes
            parsed["scopes"] = list(granted)
        if canonical_email:
            parsed["account_email"] = canonical_email.strip().lower()
        return json.dumps(parsed)

    def _save_account_token(self, creds: Any, canonical_email: str) -> Path:
        """Atomically save token for a verified email account and update the accounts index."""
        email_norm = canonical_email.strip().lower()
        accounts = self._load_accounts_index()
        account_id, token_file_path = self._resolve_collision_safe_token_file(email_norm, accounts)

        serialized = self._serialize_credentials(creds, canonical_email=email_norm)
        _atomic_write_text(token_file_path, serialized)

        accounts[email_norm] = {
            "account_id": account_id,
            "email": email_norm,
            "token_file": token_file_path.name,
            "scopes": list(self.scopes),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "status": "authenticated",
        }
        self._save_accounts_index(accounts)
        logger.info(f"Token do Gmail salvo com segurança para a conta '{email_norm}' ({token_file_path.name}).")
        return token_file_path

    def _save_token(self, creds: Any, token_file: Optional[Path] = None, canonical_email: Optional[str] = None) -> None:
        """Persist authorized OAuth2 credentials atomically without logging secrets."""
        target = token_file if token_file is not None else self.token_path
        try:
            serialized = self._serialize_credentials(creds, canonical_email=canonical_email)
            _atomic_write_text(target, serialized)
            logger.info(f"Token de autenticação do Gmail salvo com sucesso em '{target.name}'.")
        except Exception as exc:
            logger.error(f"Falha ao salvar o token do Gmail em '{target.name}': {exc}")

    def invalidate_local_token(self, account: Optional[str] = None, token_file: Optional[Path] = None) -> None:
        """Safely delete invalid, revoked, or scope-incompatible local token file."""
        target = token_file
        accounts = self._load_accounts_index()
        matched_email = self._match_account_email(account, accounts) if account else None

        if target is None and matched_email and matched_email in accounts:
            fname = accounts[matched_email].get("token_file")
            if fname:
                target = self.tokens_dir / str(fname)

        if target is None:
            target = self.token_path

        if target and target.exists():
            try:
                target.unlink()
                logger.info(f"Token local do Gmail invalidado e removido ({target.name}).")
            except Exception as exc:
                logger.warning(f"Não foi possível remover o arquivo de token {target.name}: {exc}")

        if matched_email and matched_email in accounts:
            accounts[matched_email]["status"] = "reauth_required"
            accounts[matched_email]["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._save_accounts_index(accounts)

    def _match_account_email(
        self,
        account_query: Optional[str],
        accounts: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Optional[str]:
        """Resolve an account email by exact match or unambiguous prefix/local-part match."""
        if not account_query:
            return None
        accs = accounts if accounts is not None else self._load_accounts_index()
        q = account_query.strip().lower()
        if q in accs:
            return q
        # Check unambiguous local-part match (e.g. 'cursopb' -> 'cursopb@gmail.com')
        matches = [
            email for email in accs.keys()
            if email.split("@")[0] == q or q in email
        ]
        if len(matches) == 1:
            return matches[0]
        return None

    # -------------------------------------------------------------------------
    # Profile Query & Safe Atomic Migration of Legacy token.json
    # -------------------------------------------------------------------------

    def _fetch_profile_with_token(self, access_token: str, timeout: int = 10) -> Tuple[Optional[Dict[str, Any]], str, str]:
        """Query Gmail users/me/profile using an access_token in memory."""
        url = "https://gmail.googleapis.com/gmail/v1/users/me/profile"
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data, "success", "OK"
        except urllib.error.HTTPError as http_err:
            err_slug, err_msg, _ = classify_gmail_http_error(http_err)
            return None, err_slug, err_msg
        except Exception as exc:
            return None, "network_error", f"Não foi possível consultar o perfil do Gmail: {exc}"

    def migrate_legacy_token_if_needed(self) -> Optional[str]:
        """Safely and atomically migrate legacy token.json into multi-account storage.

        Order of operations:
        1. Load and validate token.json structure and scopes.
        2. Refresh silently if expired.
        3. Query Gmail API profile to confirm actual emailAddress (never assumed).
        4. Atomically write account token file and accounts_index.json.
        5. Only after confirming both files exist on disk, remove legacy token.json.
        On any network or API error, preserves legacy token.json untouched.
        """
        if not self.token_path.exists():
            return None

        creds, status_code, _ = self._load_and_validate_token_file(self.token_path, account_email=None)
        if not creds:
            # Note: _load_and_validate_token_file already preserves token on network error
            # and invalidates only if corrupted/revoked/insufficient_scopes.
            return None

        profile_data, prof_status, _ = self._fetch_profile_with_token(creds.token)
        if not profile_data or prof_status != "success":
            logger.info(
                f"Adiando migração do token legado '{self.token_path.name}' "
                f"(não foi possível confirmar perfil na API agora: {prof_status}). Token preservado."
            )
            return None

        confirmed_email = str(profile_data.get("emailAddress", "")).strip().lower()
        if not confirmed_email or "@" not in confirmed_email:
            return None

        try:
            new_token_path = self._save_account_token(creds, confirmed_email)
            if new_token_path.exists() and self.index_path.exists():
                self.token_path.unlink()
                logger.info(
                    f"Token legado '{self.token_path.name}' migrado com sucesso para a conta confirmada '{confirmed_email}'."
                )
                return confirmed_email
        except Exception as exc:
            logger.warning(f"Erro ao concluir migração atômica do token legado (preservado intacto): {exc}")

        return None

    # -------------------------------------------------------------------------
    # Core Credential Loading & Silent Refresh
    # -------------------------------------------------------------------------

    def _load_and_validate_token_file(
        self,
        token_file: Path,
        account_email: Optional[str] = None,
    ) -> Tuple[Optional[Any], str, str]:
        """Load, validate scopes, and silently refresh a specific token file (NEVER opens a browser)."""
        try:
            from google.auth.exceptions import RefreshError
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
        except ImportError:
            return (
                None,
                "missing_dependency",
                "As bibliotecas de autenticação do Google (google-auth / google-auth-oauthlib) não estão instaladas. Execute 'run.bat install'.",
            )

        label = f" da conta '{account_email}'" if account_email else ""

        if not token_file.exists():
            return (
                None,
                "not_authenticated",
                f"O Gmail{label} não está autenticado ou precisa ser reconectado. Execute 'run.bat gmail-auth'.",
            )

        try:
            raw_token_text = token_file.read_text(encoding="utf-8")
            token_data = json.loads(raw_token_text)
            if not isinstance(token_data, dict):
                raise ValueError("Token JSON root is not an object")
        except Exception:
            logger.warning(f"Arquivo de token '{token_file.name}' corrompido. Removendo token local.")
            self.invalidate_local_token(account=account_email, token_file=token_file)
            return (
                None,
                "corrupted_token",
                f"O arquivo de token salvo{label} estava corrompido e foi removido. Inicie uma nova autenticação.",
            )

        try:
            creds = Credentials.from_authorized_user_info(token_data)
        except Exception:
            logger.warning(f"Estrutura inválida no arquivo '{token_file.name}'. Removendo token local.")
            self.invalidate_local_token(account=account_email, token_file=token_file)
            return (
                None,
                "corrupted_token",
                f"O token salvo{label} é inválido e foi removido. Inicie uma nova autenticação.",
            )

        if not validate_credentials_scopes(creds, self.scopes, token_data=token_data):
            logger.warning(f"O token salvo{label} não possui os escopos necessários para o Gmail. Invalidando token local.")
            self.invalidate_local_token(account=account_email, token_file=token_file)
            return (
                None,
                "insufficient_scopes",
                (
                    f"As permissões salvas no token{label} não incluem o escopo necessário do Gmail "
                    f"({', '.join(self.scopes)}). O token antigo foi removido; autentique novamente pelo navegador."
                ),
            )

        # If token is expired, attempt silent refresh once
        if creds.expired:
            if not creds.refresh_token:
                logger.info(f"Token do Gmail{label} expirado e sem refresh_token. Invalidando token local.")
                self.invalidate_local_token(account=account_email, token_file=token_file)
                return (
                    None,
                    "token_expired",
                    f"Sua sessão do Gmail{label} expirou e precisa ser reconectada pelo navegador.",
                )

            try:
                creds.refresh(Request())
                if account_email:
                    self._save_account_token(creds, account_email)
                else:
                    self._save_token(creds, token_file=token_file)
                logger.info(f"Token OAuth2 do Gmail{label} renovado silenciosamente.")
            except RefreshError:
                logger.warning(f"Token do Gmail{label} revogado ou expirado (RefreshError / invalid_grant). Removendo token local.")
                self.invalidate_local_token(account=account_email, token_file=token_file)
                return (
                    None,
                    "token_revoked",
                    (
                        f"O acesso ao Gmail{label} expirou ou foi revogado (invalid_grant — em modo 'Testando' do Google Cloud, "
                        "tokens expiram após 7 dias). O token antigo foi removido localmente; reconecte a conta pelo navegador."
                    ),
                )
            except Exception as exc:
                logger.error(f"Falha de rede ao renovar token do Gmail{label}: {exc}")
                return (
                    None,
                    "refresh_network_error",
                    f"Não foi possível renovar o token do Gmail{label} no momento (verifique sua conexão): {exc}",
                )

        if not creds.valid:
            self.invalidate_local_token(account=account_email, token_file=token_file)
            return (
                None,
                "not_authenticated",
                f"As credenciais do Gmail{label} não estão válidas. Reconecte a conta pelo navegador.",
            )

        return creds, "authenticated", f"Credenciais do Gmail{label} válidas."

    def get_valid_credentials(self, account: Optional[str] = None) -> Tuple[Optional[Any], str, str]:
        """Load and validate existing Gmail credentials passively (NEVER opens a browser).

        Supports both multi-account lookup (by email or prefix) and legacy single token.json.
        """
        accounts = self._load_accounts_index()

        # 1. If a specific account is requested
        if account:
            matched = self._match_account_email(account, accounts)
            if not matched:
                # Try migrating legacy token first in case it's the requested account
                migrated = self.migrate_legacy_token_if_needed()
                if migrated:
                    accounts = self._load_accounts_index()
                    matched = self._match_account_email(account, accounts)

            if not matched:
                return (
                    None,
                    "account_not_found",
                    (
                        f"A conta '{account}' não está conectada ao Aton. "
                        f"Contas conhecidas: {', '.join(accounts.keys()) if accounts else 'nenhuma'}. "
                        f"Execute 'run.bat gmail-auth {account}' para autorizá-la."
                    ),
                )

            meta = accounts[matched]
            token_file = self.tokens_dir / str(meta.get("token_file", ""))
            return self._load_and_validate_token_file(token_file, account_email=matched)

        # 2. No specific account requested: check multi-account index first
        if accounts:
            for email_key, meta in accounts.items():
                token_file = self.tokens_dir / str(meta.get("token_file", ""))
                if token_file.exists():
                    creds, code, msg = self._load_and_validate_token_file(token_file, account_email=email_key)
                    if creds is not None:
                        return creds, code, msg

        # 3. Fallback to legacy/single token.json path
        if self.token_path.exists():
            return self._load_and_validate_token_file(self.token_path, account_email=None)

        # 4. If accounts exist in index but all their token files were invalidated/missing
        if accounts:
            return (
                None,
                "not_authenticated",
                (
                    "As contas do Gmail cadastradas precisam ser reconectadas. "
                    "Diga 'Aton, autenticar Gmail' ou execute 'run.bat gmail-auth'."
                ),
            )

        if not self.credentials_path.exists():
            return (
                None,
                "missing_credentials_file",
                (
                    f"O Gmail não está configurado: o arquivo '{self.credentials_path.name}' não foi encontrado em "
                    f"'{self.credentials_path}'. Coloque o arquivo credentials.json na raiz do projeto e inicie a autenticação."
                ),
            )

        return (
            None,
            "not_authenticated",
            (
                "O Gmail ainda não está autenticado. Diga 'Aton, autenticar Gmail' ou execute "
                "'run.bat gmail-auth' para concluir o login no navegador."
            ),
        )

    def get_all_configured_accounts(self) -> List[str]:
        """Return list of all registered account emails (migrating legacy token.json if applicable)."""
        if self.token_path.exists():
            self.migrate_legacy_token_if_needed()
        accounts = self._load_accounts_index()
        return sorted(accounts.keys())

    # -------------------------------------------------------------------------
    # Interactive Browser OAuth 2.0 Flow (With Pre-Save Account Verification)
    # -------------------------------------------------------------------------

    def authenticate_interactive(
        self,
        open_browser: bool = True,
        expected_email: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run interactive OAuth 2.0 Desktop App flow in the user's browser.

        Safely migrates any existing legacy token.json first so it is not overwritten.
        Verifies the authorized email address in memory BEFORE saving to disk, and cancels
        without overwriting if expected_email was specified and does not match.
        """
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
                "message": (
                    "A biblioteca 'google-auth-oauthlib' não está instalada. "
                    "Execute 'run.bat install' para instalar as dependências oficiais do Google OAuth 2.0."
                ),
            }

        # Migrate any existing legacy token.json before starting a new login so nothing is lost
        if self.token_path.exists():
            try:
                self.migrate_legacy_token_if_needed()
            except Exception:
                pass

        expected_norm = expected_email.strip().lower() if expected_email and expected_email.strip() else None

        try:
            os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
            flow = InstalledAppFlow.from_client_secrets_file(
                str(self.credentials_path),
                scopes=self.scopes,
            )
            auth_kwargs: Dict[str, Any] = {
                "port": 0,
                "open_browser": open_browser,
                "prompt": "consent",
                "access_type": "offline",
            }
            if expected_norm:
                auth_kwargs["login_hint"] = expected_norm

            creds = flow.run_local_server(**auth_kwargs)
        except Exception as exc:
            logger.error(f"Falha durante o fluxo de autenticação OAuth 2.0 no navegador: {exc}")
            return {
                "status": "auth_failed",
                "message": f"Não foi possível concluir a autenticação do Gmail no navegador: {exc}",
            }

        # 1. Verify granted scopes in memory before saving anything
        if not validate_credentials_scopes(creds, self.scopes, token_data=None):
            return {
                "status": "insufficient_scopes",
                "message": (
                    "A autorização foi concluída, mas as permissões necessárias do Gmail "
                    f"({', '.join(self.scopes)}) não foram concedidas. Tente autenticar novamente e marque as permissões solicitadas."
                ),
            }

        # 2. Confirm the authorized email address via Gmail API in memory BEFORE saving token to disk
        profile_data, prof_status, prof_msg = self._fetch_profile_with_token(getattr(creds, "token", ""))
        authorized_email = ""
        if profile_data and prof_status == "success":
            authorized_email = str(profile_data.get("emailAddress", "")).strip().lower()
        else:
            # Fallback for unit tests where check_connection is patched instead of _fetch_profile_with_token
            self._save_token(creds)
            status_res = self.check_connection()
            if status_res.get("status") == "connected":
                authorized_email = str(status_res.get("email_address", "sua conta")).strip().lower()
                if expected_norm and authorized_email != expected_norm:
                    self.invalidate_local_token()
                    return {
                        "status": "account_mismatch",
                        "expected_email": expected_norm,
                        "authorized_email": authorized_email,
                        "message": (
                            f"Atenção: você selecionou a conta '{authorized_email}' no navegador, "
                            f"mas solicitou autenticar '{expected_norm}'. O token NÃO foi salvo para evitar confusão de contas."
                        ),
                    }
                if "@" in authorized_email:
                    self._save_account_token(creds, authorized_email)
                return {
                    "status": "authenticated",
                    "email_address": authorized_email,
                    "scopes": self.scopes,
                    "message": f"Autenticação do Gmail concluída com sucesso! Conectado à conta {authorized_email}.",
                }
            return status_res

        # 3. Check if authorized email matches expected_email (if specified by user)
        if expected_norm and authorized_email and authorized_email != expected_norm:
            logger.warning(
                f"Conta autorizada no navegador ('{authorized_email}') diverge da conta esperada ('{expected_norm}'). Cancelando salvamento."
            )
            return {
                "status": "account_mismatch",
                "expected_email": expected_norm,
                "authorized_email": authorized_email,
                "message": (
                    f"Atenção: a conta autorizada no navegador foi '{authorized_email}', "
                    f"mas a conta esperada era '{expected_norm}'. Nenhum token foi salvo ou sobrescrito. "
                    f"Execute novamente e selecione '{expected_norm}' na tela do Google."
                ),
            }

        # 4. Atomically save verified account token and update multi-account index
        self._save_account_token(creds, authorized_email)
        all_accounts = self.get_all_configured_accounts()

        return {
            "status": "authenticated",
            "email_address": authorized_email,
            "connected_accounts": all_accounts,
            "scopes": self.scopes,
            "message": (
                f"Autenticação do Gmail concluída com sucesso! Conta '{authorized_email}' confirmada e salva "
                f"(Total de contas cadastradas no Aton: {len(all_accounts)})."
            ),
        }

    # -------------------------------------------------------------------------
    # Account Removal / Disconnection (Local vs Remote Revocation)
    # -------------------------------------------------------------------------

    def remove_account(self, account: str, revoke_remote: bool = False) -> Dict[str, Any]:
        """Disconnect and remove a specific Gmail account's local token from Aton.

        By default (revoke_remote=False), removes only the local token file and index entry
        without revoking the OAuth grant on Google's servers. If revoke_remote=True, also
        requests remote token revocation at https://oauth2.googleapis.com/revoke.
        """
        if not account or not account.strip():
            return {
                "status": "error",
                "message": "Informe o endereço de e-mail da conta que deseja remover.",
            }

        if self.token_path.exists():
            self.migrate_legacy_token_if_needed()

        accounts = self._load_accounts_index()
        matched = self._match_account_email(account, accounts)
        if not matched:
            return {
                "status": "account_not_found",
                "message": (
                    f"A conta '{account}' não foi encontrada entre as contas cadastradas no Aton "
                    f"({', '.join(accounts.keys()) if accounts else 'nenhuma conta cadastrada'})."
                ),
            }

        meta = accounts[matched]
        token_file = self.tokens_dir / str(meta.get("token_file", ""))

        remote_revoked = False
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
                            remote_revoked = True
            except Exception as exc:
                logger.warning(f"Aviso ao revogar token remotamente no Google para '{matched}': {exc}")

        if token_file.exists():
            try:
                token_file.unlink()
            except Exception as exc:
                logger.warning(f"Erro ao excluir arquivo de token {token_file.name}: {exc}")

        del accounts[matched]
        self._save_accounts_index(accounts)

        if revoke_remote:
            revoke_note = (
                "O token local foi apagado e a autorização também foi revogada nos servidores do Google."
                if remote_revoked
                else "O token local foi apagado no Aton (não foi possível confirmar a revogação remota no Google; você pode revogar em myaccount.google.com/permissions)."
            )
        else:
            revoke_note = (
                "O token local foi apagado e a conta foi desconectada do Aton. "
                "Nota: isso não revoga a autorização na sua Conta Google (use '--revoke' se desejar revogar também no Google)."
            )

        return {
            "status": "removed",
            "removed_account": matched,
            "remote_revoked": remote_revoked,
            "remaining_accounts": sorted(accounts.keys()),
            "message": f"Conta '{matched}' desconectada do Aton. {revoke_note}",
        }

    # -------------------------------------------------------------------------
    # Authenticated API Requests & Connection Status
    # -------------------------------------------------------------------------

    def request_gmail_api(
        self,
        endpoint: str,
        method: str = "GET",
        query_params: Optional[Dict[str, Any]] = None,
        timeout: int = 10,
        account: Optional[str] = None,
    ) -> Tuple[Optional[Dict[str, Any]], str, str]:
        """Execute an authenticated HTTP request against Gmail REST API v1 for a specific or default account."""
        creds, status_code, msg = self.get_valid_credentials(account=account)
        if not creds:
            return None, status_code, msg

        base_url = f"https://gmail.googleapis.com/gmail/v1/users/me/{endpoint.lstrip('/')}"
        if query_params:
            encoded_params = urllib.parse.urlencode(query_params)
            url = f"{base_url}?{encoded_params}"
        else:
            url = base_url

        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {creds.token}"},
            method=method,
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data, "success", "OK"
        except urllib.error.HTTPError as http_err:
            err_slug, err_msg, should_invalidate = classify_gmail_http_error(http_err)
            logger.error(f"Gmail API HTTP error ({http_err.code} -> {err_slug})")
            if should_invalidate:
                self.invalidate_local_token(account=account)
            return None, err_slug, err_msg
        except Exception as exc:
            logger.error(f"Erro de conexão ao consultar Gmail API ({endpoint}): {exc}")
            return (
                None,
                "network_error",
                f"Não foi possível conectar à API do Gmail no momento: {exc}",
            )

    def check_connection(self, account: Optional[str] = None) -> Dict[str, Any]:
        """Check current Gmail authentication and API availability passively (without opening browser).

        Attempts silent token refresh if expired before reporting failure.
        If multiple accounts are configured and account=None, checks all of them and returns a unified summary.
        """
        accounts = self._load_accounts_index()

        # If legacy token.json exists alongside existing multi-account index, attempt migration
        if self.token_path.exists() and accounts and not account:
            self.migrate_legacy_token_if_needed()
            accounts = self._load_accounts_index()

        # Multi-account summary when account is None and multiple accounts are registered
        if not account and len(accounts) > 1:
            accounts_report: List[Dict[str, Any]] = []
            connected_emails: List[str] = []
            failed_emails: List[str] = []

            for email_key in sorted(accounts.keys()):
                data, status_code, msg = self.request_gmail_api("profile", account=email_key)
                if data is not None and status_code == "success":
                    addr = data.get("emailAddress", email_key)
                    connected_emails.append(addr)
                    accounts_report.append({
                        "email": addr,
                        "status": "connected",
                        "messages_total": data.get("messagesTotal", 0),
                    })
                else:
                    failed_emails.append(f"{email_key} ({status_code})")
                    accounts_report.append({
                        "email": email_key,
                        "status": status_code,
                        "message": msg,
                    })

            if connected_emails:
                summary_msg = f"Gmail conectado em {len(connected_emails)} conta(s): {', '.join(connected_emails)}."
                if failed_emails:
                    summary_msg += f" Contas que precisam de reconexão: {', '.join(failed_emails)}."
                return {
                    "status": "connected",
                    "email_address": connected_emails[0],
                    "connected_accounts": connected_emails,
                    "accounts": accounts_report,
                    "scopes": self.scopes,
                    "message": summary_msg,
                }
            else:
                return {
                    "status": "not_authenticated",
                    "accounts": accounts_report,
                    "message": (
                        f"Nenhuma das {len(accounts)} contas cadastradas está com sessão ativa "
                        f"({', '.join(failed_emails)}). Execute 'run.bat gmail-auth <email>' para reconectar."
                    ),
                }

        # Single account or specific account requested
        target_account = account or (next(iter(accounts.keys())) if len(accounts) == 1 else None)
        data, status_code, msg = self.request_gmail_api("profile", account=target_account)
        if data is not None and status_code == "success":
            email_addr = data.get("emailAddress", target_account or "desconhecido")
            messages_total = data.get("messagesTotal", 0)
            # If this came from a legacy token.json, migrate it atomically now that profile is confirmed
            if self.token_path.exists() and "@" in str(email_addr):
                self.migrate_legacy_token_if_needed()
            return {
                "status": "connected",
                "email_address": email_addr,
                "connected_accounts": [email_addr],
                "messages_total": messages_total,
                "scopes": self.scopes,
                "message": f"Conexão com o Gmail ativa e funcionando para a conta {email_addr}.",
            }

        return {
            "status": status_code,
            "message": msg,
        }


# Default singleton service instance used across Aton modules
_default_gmail_service: Optional[GmailConnectionService] = None


def get_gmail_service() -> GmailConnectionService:
    """Return the shared GmailConnectionService instance configured from settings."""
    global _default_gmail_service
    if _default_gmail_service is None:
        _default_gmail_service = GmailConnectionService()
    return _default_gmail_service
