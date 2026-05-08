"""GET /api/preferences/programs/list — list of loyalty programs."""

import json
from http.server import BaseHTTPRequestHandler
from typing import Any

from src.config.settings import LOYALTY_PROGRAMS


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
        _json_response(self, 200, {"programs": LOYALTY_PROGRAMS})
