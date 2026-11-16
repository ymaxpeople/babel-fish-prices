"""HTTP layer on the Python standard library only (no web framework).

Endpoints (JSON):
  GET /health
  GET /v1/prices
  GET /v1/price/{tokenAddress}
  GET /v1/twap/{tokenAddress}?window=1h|24h
  GET /v1/pairs
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from . import config
from .service import PriceService
from .store import WINDOWS


def make_handler(service: PriceService):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # keep stdout clean
            pass

        def _send_json(self, obj, status=200):
            body = json.dumps(obj).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            # Public read-only API: allow browser pages on any origin
            # (e.g. the price dashboard) to fetch prices.
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, html, status=200):
            body = html.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        def _index_page(self):
            health = service.health()
            status = health.get("status", "unknown")
            mode = health.get("mode", "unknown")
            priced = health.get("tokens_priced", 0)
            return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Babel Fish Prices — InfiniteDrive Price API</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 44rem; padding: 0 1rem; line-height: 1.6; }}
  code {{ background: rgba(127,127,127,.15); padding: .1em .35em; border-radius: .3em; }}
  li {{ margin: .3em 0; }}
  .status {{ color: #2a7d2a; font-weight: bold; }}
</style>
</head>
<body>
<h1>Babel Fish Prices</h1>
<p>InfiniteDrive チェーン（chain ID 421018）のトークン価格を返す、公開・読み取り専用の価格 API です。価格は Don't Panic Finance のプール残高から算出しています。流動性が薄いチェーンのため、価格は参考値（reference only）として利用してください。</p>
<p>状態: <span class="status">{status}</span> / モード: {mode} / 価格提供中: {priced} トークン</p>
<h2>エンドポイント</h2>
<ul>
  <li><a href="/health"><code>GET /health</code></a> — 死活確認と状態</li>
  <li><a href="/v1/prices"><code>GET /v1/prices</code></a> — 全トークンの価格一覧</li>
  <li><a href="/v1/price/0x2c32120a12B754272d9E85C57F64b50cA2C43513"><code>GET /v1/price/{{tokenAddress}}</code></a> — 1トークンの価格（リンクは FISH の例）</li>
  <li><code>GET /v1/twap/{{tokenAddress}}?window=1h|24h</code> — TWAP（時間加重平均価格）</li>
  <li><a href="/v1/pairs"><code>GET /v1/pairs</code></a> — 対象ペア一覧</li>
</ul>
<p>ソースコード: <a href="https://github.com/ymaxpeople/babel-fish-prices">github.com/ymaxpeople/babel-fish-prices</a></p>
</body>
</html>"""

        def do_OPTIONS(self):
            # CORS preflight for browser fetch() calls.
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            try:
                if path == "/":
                    return self._send_html(self._index_page())
                if path == "/health":
                    return self._send_json(service.health())
                if path == "/v1/prices":
                    return self._send_json(service.prices())
                if path == "/v1/pairs":
                    return self._send_json({"pairs": service.pairs()})
                if path.startswith("/v1/price/"):
                    address = path[len("/v1/price/"):]
                    result = service.price_by_address(address)
                    if result is None:
                        return self._send_json(
                            {"error": "token not found", "address": address}, 404)
                    return self._send_json(result)
                if path.startswith("/v1/twap/"):
                    address = path[len("/v1/twap/"):]
                    window = parse_qs(parsed.query).get("window", ["1h"])[0]
                    if window not in WINDOWS:
                        return self._send_json(
                            {"error": "window must be 1h or 24h"}, 400)
                    result = service.twap(address, window)
                    if result is None:
                        return self._send_json(
                            {"error": "token not found", "address": address}, 404)
                    return self._send_json(result)
                return self._send_json({"error": "not found", "path": path}, 404)
            except Exception as exc:  # noqa: BLE001 - surface as 500 JSON
                return self._send_json({"error": str(exc)}, 500)

    return Handler


def _background_refresh(service: PriceService, stop_event: threading.Event):
    while not stop_event.is_set():
        service.refresh()
        stop_event.wait(service.refresh_interval)


def serve(host: str, port: int, service: PriceService | None = None,
          background: bool = True):
    service = service or PriceService()
    service.refresh(force=True)
    stop_event = threading.Event()
    thread = None
    if background:
        thread = threading.Thread(target=_background_refresh,
                                  args=(service, stop_event), daemon=True)
        thread.start()
    server = ThreadingHTTPServer((host, port), make_handler(service))
    print(f"babel-fish-prices listening on http://{host}:{port} "
          f"(mode={'fixture' if service.fixture_mode else 'live'})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        server.server_close()
