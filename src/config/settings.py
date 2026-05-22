from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

LOYALTY_PROGRAMS = ["smiles", "azul", "latam", "livelo", "esfera"]

# Origens permitidas em pares de transferência
TRANSFER_SOURCES = ["esfera", "livelo"]

# Destinos permitidos em pares de transferência
TRANSFER_DESTS = ["smiles", "azul", "latam"]

# Programas permitidos para acúmulo
ACCUMULATION_PROGRAMS = ["esfera", "livelo", "smiles", "azul", "latam"]

# Todos os pares ordenados válidos (não-comutativos)
VALID_TRANSFER_PAIRS: frozenset[tuple[str, str]] = frozenset(
    (src, dst) for src in TRANSFER_SOURCES for dst in TRANSFER_DESTS
)

NEWS_RSS_FEEDS: dict[str, str] = {
    "melhores_destinos": "https://www.melhoresdestinos.com.br/feed",
    "passageiro_de_primeira": "https://passageirodeprimeira.com/feed/",
    "pontos_pra_voar": "https://pontospravoar.com/feed/",
    "mestre_das_milhas": "https://mestredasmilhas.com/feed",
    "melhores_cartoes": "https://www.melhorescartoes.com.br/feed",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(alias="DATABASE_URL")

    # Email — Resend (único provedor)
    resend_api_key: str = Field(default="", alias="RESEND_API_KEY")
    email_from: str = Field(
        default="Radar de Milhas <noreply@felipefinfanfa.com.br>",
        alias="EMAIL_FROM",
    )

    # Recipients
    digest_recipient: str = Field(alias="DIGEST_RECIPIENT")

    # Capacity & URLs
    max_users: int = Field(default=200, alias="MAX_USERS")
    app_base_url: str = Field(default="https://milhas.felipefinfanfa.com.br", alias="APP_BASE_URL")

    # Observability
    sentry_dsn: str = Field(default="", alias="SENTRY_DSN")

    # Runtime
    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


settings = Settings()  # type: ignore[call-arg]
