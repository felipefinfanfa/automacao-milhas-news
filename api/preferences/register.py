"""POST /api/preferences/register — create or retrieve a user account."""

import json
import uuid
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
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            name = str(body.get("name", "")).strip()
            email = str(body.get("email", "")).strip().lower()
            phone = str(body.get("phone", "")).strip()

            if not name or not email or not phone:
                _json_response(self, 400, {"detail": "name, email e phone são obrigatórios"})
                return

            with _SessionFactory() as session:
                row = session.query(UserPreferences).filter_by(email=email).first()
                if row:
                    _json_response(
                        self,
                        200,
                        {
                            "user_id": str(row.user_id),
                            "email": email,
                            "name": row.name,
                            "phone": row.phone,
                            "is_new": False,
                        },
                    )
                    return

                count = session.query(UserPreferences).count()
                if count >= settings.max_users:
                    _json_response(
                        self,
                        400,
                        {
                            "detail": "Número máximo de cadastros atingido. Tente novamente mais tarde."
                        },
                    )
                    return

                new_id = uuid.uuid4()
                row = UserPreferences(
                    user_id=new_id,
                    email=email,
                    name=name,
                    phone=phone,
                    unsubscribe_token=uuid.uuid4(),
                    monitored_programs=[],
                    transfer_pairs=[],
                    accumulation_programs=[],
                )
                session.add(row)
                session.commit()
                _json_response(
                    self,
                    201,
                    {
                        "user_id": str(new_id),
                        "email": email,
                        "name": name,
                        "phone": phone,
                        "is_new": True,
                    },
                )
        except json.JSONDecodeError:
            _json_response(self, 400, {"detail": "JSON inválido"})
        except Exception as exc:
            _json_response(self, 500, {"detail": str(exc)})
