#!/usr/bin/env python3
"""Misread web app.

  python app/server.py            then open http://localhost:8080
  python app/server.py --port 9000

Uses NEBIUS_API_KEY from misread-test/.env for live runs. Without a key, the
sample letters still open with their saved results; live buttons are disabled.
Set MISREAD_MOCK=1 to try every button with a fake model (results mean nothing).
"""
import argparse
import http.server
import json
import mimetypes
import os
import pathlib
import re
import sys
import threading
import time

APP = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(APP))
STATIC = APP / "static"
core = None  # imported in main(), after --mock/--offline are applied
MAX_JOBS = 2
MAX_BODY = 400_000
PUBLIC = False  # --public: the saved examples are never overwritten
LIMITED = False  # --public without --no-limits: daily runs per visitor and in total

# Runs each visitor (by IP address) may start per day, and the site's total per day, in --public mode.
PER_VISITOR = {"extract": 5, "test": 5, "fix": 2, "read_in": 20, "help": 10}
PER_DAY = {"extract": 150, "test": 120, "fix": 25, "read_in": 400, "help": 300}


class DayCounter:
    """Counts runs per visitor and in total; everything resets at midnight (server time)."""

    def __init__(self):
        self.lock, self.day, self.seen = threading.Lock(), None, {}

    def take(self, ip, kind):
        """Count one run, or return why it isn't allowed."""
        with self.lock:
            today = time.strftime("%Y-%m-%d")
            if today != self.day:
                self.day, self.seen = today, {}
            mine, total = self.seen.get((ip, kind), 0), self.seen.get(("*", kind), 0)
            if total >= PER_DAY[kind]:
                return "Misread has reached today's limit of free runs. The examples still work; try again tomorrow."
            if mine >= PER_VISITOR[kind]:
                return "You've used today's free runs. The examples still work; try again tomorrow."
            self.seen[(ip, kind)], self.seen[("*", kind)] = mine + 1, total + 1
            return None


LIMITS = DayCounter()


# Sent with every response. Scripts may only come from this site and the one library CDN
# (pdf.js and mammoth for reading uploads), so text inside a letter can never run as code.
SECURITY_HEADERS = {
    "Content-Security-Policy": "; ".join([
        "default-src 'self'",
        "script-src 'self' https://cdnjs.cloudflare.com",
        "worker-src 'self' blob: https://cdnjs.cloudflare.com",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "font-src https://fonts.gstatic.com",
        "img-src 'self' data:",
        "connect-src 'self' https://cdnjs.cloudflare.com",
        "frame-ancestors 'self'",
        "base-uri 'none'",
        "form-action 'none'",
        "object-src 'none'",
    ]),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "SAMEORIGIN",
    "Referrer-Policy": "no-referrer",
}


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "Misread/1.0"
    sys_version = ""

    def end_headers(self):
        for k, v in SECURITY_HEADERS.items():
            self.send_header(k, v)
        super().end_headers()

    def log_message(self, fmt, *args):  # quieter console: only API calls
        if "/api/" in (args[0] if args else ""):
            sys.stderr.write("  " + (fmt % args) + "\n")

    # ------------------------------------------------------------ helpers
    def send_json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def fail(self, msg, code=400):
        self.send_json({"error": msg}, code)

    def body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ValueError("bad request") from None
        if n < 0:
            raise ValueError("bad request")
        if n > MAX_BODY:
            raise ValueError("that letter is too long")
        return json.loads(self.rfile.read(n) or b"{}")

    def send_file(self, path):
        if not path.is_file() or STATIC not in path.resolve().parents:
            return self.fail("not found", 404)
        data = path.read_bytes()
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def visitor(self):
        return self.headers.get("X-Real-IP") or self.client_address[0]

    def over_limit(self, kind):
        """In --public mode, refuse (429) once a visitor or the whole site has used today's runs."""
        if not LIMITED:
            return False
        why = LIMITS.take(self.visitor(), kind)
        if why:
            self.fail(why, 429)
            return True
        return False

    def need_live(self):
        if not core.LIVE:
            self.fail("Live runs need a NEBIUS_API_KEY in misread-test/.env.", 503)
            return False
        if core.running_jobs() >= MAX_JOBS:
            self.fail("Misread is busy with other runs. Try again in a minute.", 429)
            return False
        return True

    def letter_and_fact(self, data):
        text = str(data.get("text", "")).strip()
        if not text:
            raise ValueError("there is no letter text")
        if len(text.split()) > core.MAX_WORDS:
            raise ValueError(f"letters up to {core.MAX_WORDS:,} words, please")
        return text, core.check_fact(data.get("fact"))

    # ------------------------------------------------------------- routes
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            return self.send_file(STATIC / "index.html")
        if path.startswith("/static/"):
            return self.send_file(STATIC / path[len("/static/"):])
        if path == "/api/status":
            reason = None if core.LIVE else ("offline" if os.environ.get("NEBIUS_API_KEY") else "no_key")
            return self.send_json({"live": core.LIVE, "mock": core.MOCK, "offline_reason": reason, "models": core.MODELS,
                                   "web_help": core.LIVE and core.web_help.enabled()})
        if path == "/api/samples":
            return self.send_json(core.list_samples())
        m = re.fullmatch(r"/api/sample/([a-z0-9_]+)", path)
        if m:
            s = core.load_sample(m.group(1))
            return self.send_json(s) if s else self.fail("no such letter", 404)
        m = re.fullmatch(r"/api/job/([a-f0-9]+)", path)
        if m:
            job = core.JOBS.get(m.group(1))
            return self.send_json(job.view()) if job else self.fail("no such job", 404)
        return self.fail("not found", 404)

    def do_HEAD(self):  # link checkers and uptime monitors: same headers as GET, no body
        self.do_GET()

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        try:
            data = self.body()
            if path == "/api/extract":
                if not core.LIVE:
                    return self.fail("Reading a new letter needs a NEBIUS_API_KEY in misread-test/.env.", 503)
                text = str(data.get("text", "")).strip()
                if not text:
                    raise ValueError("paste a letter first")
                if len(text.split()) > core.MAX_WORDS:
                    raise ValueError(f"letters up to {core.MAX_WORDS:,} words, please")
                if self.over_limit("extract"):
                    return
                fact, ui = core.extract_with_ui(text)
                return self.send_json({**fact, "ui": ui})
            if path in ("/api/test", "/api/fix"):
                if not self.need_live():
                    return
                text, fact = self.letter_and_fact(data)
                kind = path.rsplit("/", 1)[1]
                if self.over_limit(kind):
                    return
                sid = data.get("sample_id")
                # a public visitor's run never replaces an example's saved result
                sid = sid if sid in core.sample_ids() and not PUBLIC else None
                fn = core.run_test_job if kind == "test" else core.run_fix_job
                job = core.start(kind, fn, text, fact, cache_as=sid)
                return self.send_json({"job": job.id})
            if path == "/api/read_in":
                if not self.need_live():
                    return
                language = str(data.get("language", ""))
                if language not in core.coach.READ_IN or core.coach.is_english(language):
                    raise ValueError("pick a language from the list")
                if self.over_limit("read_in"):
                    return
                sid = data.get("sample_id")
                if sid in core.sample_ids():  # an example: use the server's own copy, never the visitor's
                    return self.send_json(core.read_in_sample(sid, language))
                cards = data.get("cards") if isinstance(data.get("cards"), list) else []
                cards = [{"said": str(c.get("said", "")), "truth": str(c.get("truth", ""))} for c in cards if isinstance(c, dict)]
                return self.send_json(core.coach.read_in(core.API, core.check_fact(data.get("fact")), cards, language))
            if path == "/api/help":
                if not self.need_live():
                    return
                sid = data.get("sample_id")
                if sid in core.sample_ids():  # an example: saved after the first search, so usually free
                    return self.send_json({"help": core.help_sample(sid)})
                if self.over_limit("help"):
                    return
                return self.send_json({"help": core.web_help.official_help(core.API, core.check_fact(data.get("fact")))})
            if path == "/api/locate":
                if not core.LIVE or PUBLIC:
                    return self.fail("needs a key", 503)
                located = core.locate_sample(str(data.get("sample_id", "")))
                return self.send_json({"located": located}) if located is not None else self.fail("no saved result", 404)
            return self.fail("not found", 404)
        except ValueError as e:
            return self.fail(str(e))
        except Exception as e:  # keep the server up; show the reason
            return self.fail(f"{type(e).__name__}: {e}", 500)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--mock", action="store_true", help="fake model for trying the buttons; nothing is saved")
    p.add_argument("--offline", action="store_true", help="saved results only; never call the API")
    p.add_argument("--public", action="store_true",
                   help="for a public website: saved examples are never overwritten, and daily limits per visitor apply")
    p.add_argument("--no-limits", action="store_true", help="with --public: no daily limits")
    p.add_argument("--max-jobs", type=int, default=2, help="runs processed at the same time (default 2)")
    a = p.parse_args()
    global PUBLIC, LIMITED, MAX_JOBS
    PUBLIC, LIMITED, MAX_JOBS = a.public, a.public and not a.no_limits, a.max_jobs
    if a.mock:
        os.environ["MISREAD_MOCK"] = "1"
    global core
    import core as _core
    core = _core
    if a.offline:
        core.LIVE = False
    srv = http.server.ThreadingHTTPServer((a.host, a.port), Handler)
    mode = "MOCK model" if core.MOCK else "live (Nebius Token Factory)" if core.LIVE else "saved results only (no API key)"
    limits = ("  ·  public, daily limits on" if LIMITED else "  ·  public, no limits") if PUBLIC else ""
    print(f"Misread is running at http://localhost:{a.port}  ·  {mode}{limits}\nPress Ctrl+C to stop.", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
