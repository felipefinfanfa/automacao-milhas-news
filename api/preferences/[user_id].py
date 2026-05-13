"""GET + PUT /api/preferences/[user_id] — read and update user preferences."""

import json
import uuid
from http.server import BaseHTTPRequestHandler
from typing import Any

from src.api.schemas.preferences import UserPreferencesIn
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


def _row_to_dict(row: Any) -> dict:
    return {
        "user_id": str(row.user_id),
        "email": row.email,
        "name": row.name,
        "phone": row.phone,
        "monitored_programs": row.monitored_programs or [],
        "transfer_pairs": row.transfer_pairs or [],
        "accumulation_programs": row.accumulation_programs or [],
        "flight_routes": row.flight_routes or [],
        "flight_programs": row.flight_programs or [],
    }


def _parse_user_id(path: str) -> str:
    return path.split("?")[0].rstrip("/").split("/")[-1]


def _is_valid_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, PUT, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        user_id = _parse_user_id(self.path)
        if not _is_valid_uuid(user_id):
            _json_response(self, 404, {"detail": "Preferências não encontradas"})
            return
        try:
            with _SessionFactory() as session:
                row = session.query(UserPreferences).filter_by(user_id=user_id).first()
            if not row:
                _json_response(self, 404, {"detail": "Preferências não encontradas"})
                return
            _json_response(self, 200, _row_to_dict(row))
        except Exception as exc:
            _json_response(self, 500, {"detail": str(exc)})

    def do_PUT(self):
        user_id = _parse_user_id(self.path)
        if not _is_valid_uuid(user_id):
            _json_response(self, 400, {"detail": "user_id inválido"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            prefs_in = UserPreferencesIn(**body)
            valid_pairs = prefs_in.validated_transfer_pairs()
            pairs = [{"source": p.source, "dest": p.dest} for p in valid_pairs]
            valid_routes = prefs_in.validated_flight_routes()
            routes_data = [
                {"origin_iata": r.origin_iata, "destination_iata": r.destination_iata}
                for r in valid_routes
            ]
            valid_flight_programs = prefs_in.validated_flight_programs()

            with _SessionFactory() as session:
                row = session.query(UserPreferences).filter_by(user_id=user_id).first()
                if row:
                    row.monitored_programs = prefs_in.validated_programs()
                    row.transfer_pairs = pairs
                    row.accumulation_programs = prefs_in.validated_accumulation()
                    row.flight_routes = routes_data
                    row.flight_programs = valid_flight_programs
                else:
                    row = UserPreferences(
                        user_id=uuid.UUID(user_id),
                        monitored_programs=prefs_in.validated_programs(),
                        transfer_pairs=pairs,
                        accumulation_programs=prefs_in.validated_accumulation(),
                        flight_routes=routes_data,
                        flight_programs=valid_flight_programs,
                    )
                    session.add(row)
                session.commit()
                session.refresh(row)
                result = _row_to_dict(row)
                has_prefs = bool(
                    row.transfer_pairs
                    or row.accumulation_programs
                    or row.flight_routes
                    or row.flight_programs
                )
                send_confirmation = has_prefs and row.email
                token = str(row.unsubscribe_token) if row.unsubscribe_token else None
                uid = str(row.user_id)
                email = row.email
                acc_programs = row.accumulation_programs or []
                pair_objs = [
                    type("P", (), {"source": p["source"], "dest": p["dest"]})()
                    for p in (row.transfer_pairs or [])
                    if "source" in p and "dest" in p
                ]
                user_name = row.name
                flight_routes_data = row.flight_routes or []
                flight_programs_data = row.flight_programs or []

            if send_confirmation:
                from src.pipeline.dispatcher import dispatch_confirmation
                dispatch_confirmation(
                    user_id=uid,
                    user_email=email,
                    unsubscribe_token=token,
                    transfer_pairs=pair_objs,
                    accumulation_programs=acc_programs,
                    flight_routes=flight_routes_data,
                    flight_programs=flight_programs_data,
                    name=user_name,
                )

            _json_response(self, 200, result)
        except json.JSONDecodeError:
            _json_response(self, 400, {"detail": "JSON inválido"})
        except Exception as exc:
            _json_response(self, 500, {"detail": str(exc)})
