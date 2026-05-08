"""GET /api/preferences/slots — available registration slots."""

import json
from http.server import BaseHTTPRequestHandler
from typing import Any

from src.config.settings import settings
from src.db.models import UserPreferences, create_engine_from_url, get_session_factory

_engine = create_engine_from_url(settings.database_url)
_SessionFactory = get_session_factory(_engine)


def _json_response(handler: Any, status: int, data: dict) -> None:
    body = json.dumps(data).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            with _SessionFactory() as session:
                used = session.query(UserPreferences).count()
            total = settings.max_users
            _json_response(self, 200, {
                "used": used,
                "total": total,
                "remaining": max(0, total - used),
            })
        except Exception as exc:
            _json_response(self, 500, {"detail": str(exc)})
