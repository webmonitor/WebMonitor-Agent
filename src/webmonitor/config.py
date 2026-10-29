"""Environment configuration. One process, one settings object, no credential files."""
import ipaddress
from functools import lru_cache
from urllib.parse import urlsplit, urlunsplit

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

TARGET_POLICIES = frozenset({"public", "allowlist", "any"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    pghost: str = "postgres"
    pgport: int = 5432
    pgdatabase: str = "webmonitor"
    pguser: str = "webmonitor"
    postgres_password: SecretStr = SecretStr("")
    pgpassword: SecretStr | None = None

    app_origin: str = "http://localhost:8080"
    development_mode: bool = False
    secret_key: SecretStr = SecretStr("")
    session_ttl_hours: int = 168
    trusted_proxy_ip: str | None = None

    admin_email: str = ""
    admin_password: SecretStr = SecretStr("")
    registration_allowed_emails: str = ""

    openai_api_key: SecretStr = SecretStr("")
    openai_base_url: str = "https://api.openai.com/v1"
    openai_container_base_url: str | None = None
    openai_model: str = ""
    container_runtime: bool = False

    s3_endpoint_url: str = "http://s3:9000"
    s3_bucket: str = "webmonitor-evidence"
    s3_access_key_id: SecretStr = SecretStr("")
    s3_secret_access_key: SecretStr = SecretStr("")
    egress_proxy_url: str = "http://egress:3128"

    smtp_host: str = ""
    smtp_port: int = 465
    smtp_username: SecretStr = SecretStr("")
    smtp_password: SecretStr = SecretStr("")
    smtp_use_ssl: bool = True
    smtp_starttls: bool = False
    mail_from: str = ""

    target_policy: str = "public"
    target_allowed_origins: str = ""

    agent_max_turns: int = 24
    agent_model_timeout_seconds: int = 120
    agent_max_tokens: int = 8192
    agent_timeout_seconds: int = 300
    agent_history_messages: int = 30
    agent_concurrency: int = 2
    http_concurrency: int = 8
    browser_concurrency: int = 4

    preview_ttl_minutes: int = 60
    message_max_chars: int = 32000
    max_active_monitors: int = 1000
    max_attempts: int = 3
    login_attempts: int = 10
    login_window_minutes: int = 15
    workers_enabled: bool = True

    @model_validator(mode="after")
    def validate_settings(self):
        if self.trusted_proxy_ip is not None:
            self.trusted_proxy_ip = str(ipaddress.ip_address(self.trusted_proxy_ip))
        origin = urlsplit(self.app_origin)
        if origin.scheme not in {"http", "https"} or not origin.hostname:
            raise ValueError("APP_ORIGIN must be an HTTP(S) origin")
        if origin.path or origin.query or origin.fragment or origin.username:
            raise ValueError("APP_ORIGIN must not contain path or credentials")
        if origin.scheme == "http" and not self.development_mode:
            raise ValueError("HTTP requires explicit DEVELOPMENT_MODE=true")
        if len(self.secret_key.get_secret_value()) < 32:
            raise ValueError("SECRET_KEY must contain at least 32 characters")
        if self.session_ttl_hours <= 0:
            raise ValueError("SESSION_TTL_HOURS must be positive")
        if self.target_policy not in TARGET_POLICIES:
            raise ValueError("TARGET_POLICY must be one of public, allowlist, any")
        if self.target_policy != "public" and not self.development_mode:
            raise ValueError("TARGET_POLICY other than public requires DEVELOPMENT_MODE=true")
        if self.target_policy == "allowlist" and not parse_target_origins(self.target_allowed_origins):
            raise ValueError("TARGET_POLICY=allowlist requires TARGET_ALLOWED_ORIGINS")
        for name in ("preview_ttl_minutes", "agent_concurrency", "http_concurrency",
                     "agent_model_timeout_seconds",
                     "browser_concurrency", "max_attempts", "max_active_monitors",
                     "login_attempts", "login_window_minutes", "agent_max_turns",
                     "agent_max_tokens", "agent_timeout_seconds", "agent_history_messages",
                     "message_max_chars"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name.upper()} must be at least 1")
        return self

    @property
    def database_url(self) -> URL:
        password = self.pgpassword or self.postgres_password
        return URL.create("postgresql+asyncpg", username=self.pguser,
                          password=password.get_secret_value(), host=self.pghost,
                          port=self.pgport, database=self.pgdatabase)

    @property
    def model_base_url(self) -> str:
        if not self.container_runtime:
            return self.openai_base_url
        if self.openai_container_base_url:
            return self.openai_container_base_url
        parts = urlsplit(self.openai_base_url)
        if parts.hostname in {"127.0.0.1", "localhost"}:
            authority = "host.docker.internal"
            if parts.port:
                authority += f":{parts.port}"
            return urlunsplit(parts._replace(netloc=authority))
        return self.openai_base_url

    @property
    def allowed_registration_emails(self) -> set[str]:
        return {item.strip().casefold() for item in self.registration_allowed_emails.split(",") if item.strip()}


def parse_target_origins(value: str) -> frozenset[str]:
    """Explicit scheme://host[:port] entries; anything malformed is a startup error."""
    origins = set()
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        parsed = urlsplit(item)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.path not in {"", "/"} or parsed.query or parsed.fragment
                or parsed.username is not None):
            raise ValueError("TARGET_ALLOWED_ORIGINS entries must be scheme://host[:port]")
        try:
            _ = parsed.port
        except ValueError as exc:
            raise ValueError("TARGET_ALLOWED_ORIGINS contains an invalid port") from exc
        origins.add(f"{parsed.scheme}://{parsed.netloc}")
    return frozenset(origins)


def allowed_target_origins() -> frozenset[str]:
    return parse_target_origins(get_settings().target_allowed_origins)


@lru_cache
def get_settings() -> Settings:
    return Settings()
