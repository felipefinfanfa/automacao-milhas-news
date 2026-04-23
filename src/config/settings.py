from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

LOYALTY_PROGRAMS = ["smiles", "azul", "latam", "livelo", "esfera", "iupp"]

CLOUDSCRAPER_DOMAINS = {
    "smiles.com.br",
    "voeazul.com.br",
    "latampass.latam.com",
    "livelo.com.br",
    "esfera.com.vc",
    "iupp.com.br",
}

PROGRAM_URLS: dict[str, str] = {
    "smiles": "https://www.smiles.com.br/voe-de-smiles/transferencia-de-pontos",
    "azul": "https://www.viajemais.voeazul.com.br/transferencia",
    "latam": "https://www.latampass.latam.com/pt_br/acumule-pontos/transferencia-de-pontos",
    "livelo": "https://www.livelo.com.br/transferencia",
    "esfera": "https://www.esfera.com.vc/transferencia-de-pontos",
    "iupp": "https://www.iupp.com.br/transferir",
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
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database (supabase_url/key opcionais — acesso via DATABASE_URL direto)
    database_url: str = Field(alias="DATABASE_URL")
    supabase_url: str = Field(default="", alias="SUPABASE_URL")
    supabase_key: str = Field(default="", alias="SUPABASE_KEY")

    # Email — Resend (primary)
    resend_api_key: str = Field(default="", alias="RESEND_API_KEY")
    email_from: str = Field(
        default="Miles Radar <noreply@milesradar.com>", alias="EMAIL_FROM"
    )

    # Email — Gmail SMTP (fallback)
    gmail_user: str = Field(default="", alias="GMAIL_USER")
    gmail_app_password: str = Field(default="", alias="GMAIL_APP_PASSWORD")

    # Recipients
    digest_recipient: str = Field(alias="DIGEST_RECIPIENT")

    # Capacity & URLs
    max_users: int = Field(default=200, alias="MAX_USERS")
    app_base_url: str = Field(
        default="https://milhas.felipefinfanfa.com.br", alias="APP_BASE_URL"
    )

    # Observability
    sentry_dsn: str = Field(default="", alias="SENTRY_DSN")

    # Runtime
    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


settings = Settings()  # type: ignore[call-arg]
