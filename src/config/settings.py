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

CLOUDSCRAPER_DOMAINS = {
    "smiles.com.br",
    "voeazul.com.br",
    "latam.com",
    "livelo.com.br",
    "esfera.com.vc",
}

PROGRAM_URLS: dict[str, str] = {
    "smiles": "https://www.smiles.com.br/acumule/transferencia-de-pontos",
    "azul": "https://www.voeazul.com.br/pt/br/azul-fidelidade/como-acumular/transferencia-de-pontos",
    "latam": "https://www.latam.com/pt_br/latam-pass/acumule-pontos/transferencia-de-pontos/",
    "livelo": "https://www.livelo.com.br/ganhe-pontos/transferencia-de-pontos",
    "esfera": "https://www.esfera.com.vc/transferencia-de-pontos",
}

NEWS_RSS_FEEDS: dict[str, str] = {
    "melhores_destinos": "https://www.melhoresdestinos.com.br/feed",
    "passageiro_de_primeira": "https://www.passageirodeprimeira.com.br/feed",
    "pontos_pra_voar": "https://www.pontospravolar.com/feed",
    "mestre_das_milhas": "https://www.mestredasmilhas.com/feed",
    "melhores_cartoes": "https://www.melhorescartoes.com.br/feed",
}

GOOGLE_NEWS_KEYWORDS = [
    "transferência bônus milhas",
    "promoção pontos smiles",
    "promoção livelo transferência",
    "bônus transferência latam pass",
    "promoção esfera milhas",
    "bônus transferência esfera smiles",
    "bônus transferência livelo smiles",
    "bônus transferência esfera azul",
    "bônus transferência livelo azul",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database (supabase_url/key opcionais — acesso via DATABASE_URL direto)
    database_url: str = Field(alias="DATABASE_URL")
    supabase_url: str = Field(default="", alias="SUPABASE_URL")
    supabase_key: str = Field(default="", alias="SUPABASE_KEY")

    # Email — Resend (primary)
    resend_api_key: str = Field(default="", alias="RESEND_API_KEY")
    email_from: str = Field(default="Radar de Milhas <noreply@milesradar.com>", alias="EMAIL_FROM")

    # Email — Gmail SMTP (fallback)
    gmail_user: str = Field(default="", alias="GMAIL_USER")
    gmail_app_password: str = Field(default="", alias="GMAIL_APP_PASSWORD")

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
