"""
Electro Stock — Backend Sync Server
====================================
Run this script on your PC. It listens on http://localhost:5050
and automatically saves/loads inventory data to/from the file
path you set in the inventory system's Settings page.

Requirements: Python 3.7+  (no extra packages needed)
Start with  : double-click start_server.bat
              OR run:  python electro_stock_server.py

NOTE: This server is only needed for "Local Python Server" data-sync
mode. GitHub Repository mode doesn't need it at all. License key
verification does NOT go through this server — it happens entirely
in the browser using public/private key signing. See SECURITY_NOTES.md
and license_generator.py.
"""

import json
import os
import shutil
import socket
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

# When this script's output isn't a real console (e.g. redirected to a log
# file by the watchdog, or run on a non-English Windows locale), Python can
# pick a narrow legacy encoding that can't represent some characters and
# crashes on print(). Force UTF-8 with a safe fallback so that can never
# take the server down.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

# ── CONFIG ────────────────────────────────────────────────────────
PORT = 5050
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "electro_sync_config.json")

# ── STATE ─────────────────────────────────────────────────────────
config = {"data_file": ""}


def load_config():
    global config
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
            print(f"[CONFIG] Loaded. Data file: {config.get('data_file','(not set)')}")
        except Exception as e:
            print(f"[CONFIG] Could not load config: {e}")

def save_config():
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print(f"[CONFIG] Could not save config: {e}")

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def get_mtime():
    """Modification time of the data file, used by the browser to detect
    when another device has saved changes since this one last loaded."""
    fp = config.get("data_file", "")
    if fp and os.path.exists(fp):
        try:
            return os.path.getmtime(fp)
        except Exception:
            return None
    return None

# ── HTTP HANDLER ─────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass  # suppress default HTTP logs — we use our own

    # ── Catch ALL connection errors silently ──────────────────────
    def handle(self):
        try:
            super().handle()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            # Browser closed the connection early — completely normal, ignore it
            pass
        except Exception as e:
            log(f"HANDLER ERROR: {e}")

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass
        except Exception as e:
            log(f"REQUEST ERROR: {e}")

    # ── Safe JSON response writer ─────────────────────────────────
    def send_json(self, data, status=200):
        try:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass  # client disconnected — nothing we can do, ignore cleanly
        except Exception as e:
            log(f"SEND ERROR: {e}")

    def read_body(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            return self.rfile.read(length)
        except Exception:
            return b""

    # ── OPTIONS (CORS preflight) ──────────────────────────────────
    def do_OPTIONS(self):
        try:
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass

    # ── GET ───────────────────────────────────────────────────────
    def do_GET(self):
        # /status — health check
        if self.path == "/status":
            self.send_json({
                "ok": True,
                "data_file": config.get("data_file", ""),
                "mtime": get_mtime(),
                "server": "Electro Stock Server v1.2"
            })

        # /load — read data file and return to browser
        elif self.path == "/load":
            fp = config.get("data_file", "")
            if not fp:
                self.send_json({"ok": False, "error": "No data file path configured. Set it in Settings."})
                return
            if not os.path.exists(fp):
                self.send_json({"ok": False, "error": f"File not found: {fp}"})
                return
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    data = json.load(f)
                log(f"LOAD  <- {fp}")
                self.send_json({"ok": True, "data": data, "loaded_from": fp, "mtime": get_mtime()})
            except Exception as e:
                log(f"LOAD ERROR: {e}")
                self.send_json({"ok": False, "error": str(e)})

        else:
            self.send_json({"ok": False, "error": "Unknown endpoint"}, 404)

    # ── POST ──────────────────────────────────────────────────────
    def do_POST(self):

        # /config — set the data file path
        if self.path == "/config":
            try:
                body = json.loads(self.read_body())
                new_path = body.get("data_file", "").strip()
                if not new_path:
                    self.send_json({"ok": False, "error": "data_file path is required"})
                    return
                parent = os.path.dirname(new_path)
                if parent and not os.path.exists(parent):
                    os.makedirs(parent, exist_ok=True)
                    log(f"CONFIG  Created directory: {parent}")
                config["data_file"] = new_path
                save_config()
                log(f"CONFIG  Data file set to: {new_path}")
                self.send_json({"ok": True, "data_file": new_path})
            except Exception as e:
                log(f"CONFIG ERROR: {e}")
                self.send_json({"ok": False, "error": str(e)})

        # /save — write data to file
        elif self.path == "/save":
            fp = config.get("data_file", "")
            if not fp:
                self.send_json({"ok": False, "error": "No data file path set. Go to Settings > Backend Sync."})
                return
            try:
                body = json.loads(self.read_body())
                data = body.get("data", body)

                # Write to temp file first then rename — prevents file corruption
                tmp = fp + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                shutil.move(tmp, fp)

                # Rolling backup
                bak = fp + ".bak"
                shutil.copy2(fp, bak)

                synced_at = data.get("syncedAt", datetime.now().isoformat())
                log(f"SAVE  -> {os.path.basename(fp)}  (at {synced_at[:19]})")
                self.send_json({"ok": True, "saved_to": fp, "mtime": get_mtime()})
            except Exception as e:
                log(f"SAVE ERROR: {e}")
                self.send_json({"ok": False, "error": str(e)})

        else:
            self.send_json({"ok": False, "error": "Unknown endpoint"}, 404)


# ── CUSTOM SERVER — suppress socket-level tracebacks ─────────────
class QuietServer(HTTPServer):
    def handle_error(self, request, client_address):
        # Get the current exception
        import sys
        exc_type = sys.exc_info()[0]
        # Silently ignore connection-level errors from browsers
        if exc_type in (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            return
        # For anything else, log a clean one-liner instead of a full traceback
        log(f"SERVER ERROR from {client_address}: {sys.exc_info()[1]}")


# ── MAIN ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    load_config()

    server = QuietServer(("localhost", PORT), Handler)

    print("=" * 60)
    print("  Electro Stock — Backend Sync Server  v1.4")
    print("=" * 60)
    print(f"  Listening on  : http://localhost:{PORT}")
    print(f"  Data file     : {config.get('data_file') or '(not set — configure in Settings)'}")
    print(f"  Config stored : {CONFIG_FILE}")
    print("-" * 60)
    print("  Keep this window open while using the inventory system.")
    print("  Press Ctrl+C to stop the server.")
    print("=" * 60)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[SERVER] Stopped by user.")
        server.server_close()
