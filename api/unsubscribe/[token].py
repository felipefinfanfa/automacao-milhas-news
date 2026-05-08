"""GET /api/unsubscribe/[token] — unsubscribe and delete user data."""

import html as html_module
import uuid
from http.server import BaseHTTPRequestHandler
from textwrap import dedent
from typing import Any

from src.db.models import UserPreferences, create_engine_from_url, get_session_factory
from src.config.settings import settings

_engine = create_engine_from_url(settings.database_url)
_SessionFactory = get_session_factory(_engine)


def _unsubscribe_html(message: str) -> bytes:
    content = dedent(f"""\
        <!DOCTYPE html>
        <html lang="pt-BR">
        <head>
          <meta charset="UTF-8">
          <meta name="viewport" content="width=device-width,initial-scale=1">
          <title>Radar de Milhas — Cancelar inscrição</title>
          <style>
            body {{
              font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
              background: #f1f5f9; display: flex; align-items: center;
              justify-content: center; min-height: 100vh; margin: 0;
            }}
            .card {{
              background: white; border-radius: 12px; padding: 2rem 2.5rem;
              box-shadow: 0 4px 24px rgba(15,23,42,.1); max-width: 420px;
              text-align: center;
            }}
            h1 {{ font-size: 1.25rem; color: #0f172a; margin-bottom: .75rem; }}
            p  {{ color: #64748b; font-size: .9375rem; line-height: 1.6; }}
            a  {{ color: #6366f1; font-weight: 600; }}
          </style>
        </head>
        <body>
          <div class="card">
            <h1>Radar de Milhas</h1>
            <p>{html_module.escape(message)}</p>
            <p style="margin-top:1.25rem"><a href="/">Voltar ao site</a></p>
          </div>
        </body>
        </html>
    """)
    return content.encode()


def _html_response(handler: Any, status: int, body: bytes) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        token_str = self.path.split("?")[0].rstrip("/").split("/")[-1]
        try:
            token_uuid = uuid.UUID(token_str)
        except ValueError:
            _html_response(self, 404, _unsubscribe_html("Token inválido."))
            return

        try:
            with _SessionFactory() as session:
                row = session.query(UserPreferences).filter_by(
                    unsubscribe_token=token_uuid
                ).first()
                if not row:
                    _html_response(
                        self, 404,
                        _unsubscribe_html("Usuário não encontrado ou já removido.")
                    )
                    return
                session.delete(row)
                session.commit()
            _html_response(
                self, 200,
                _unsubscribe_html(
                    "Inscrição cancelada com sucesso. "
                    "Seus dados foram permanentemente removidos."
                ),
            )
        except Exception as exc:
            _html_response(self, 500, _unsubscribe_html(f"Erro interno: {exc}"))
