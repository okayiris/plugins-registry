"""Loaded by Python on start for every plugin command the test environment runs (it is on PYTHONPATH).

It changes nothing in the plugin itself; it only replaces what the plugin reaches outside:

  SIM_HTTP=replay   urllib answers from the cassette; a request that is not in it fails like a
                    network error and is written to SIM_MISSES, so the test reports it.
  SIM_HTTP=record   urllib goes to the internet and every answer is added to the cassette.
  SIM_HTTP=live     urllib goes to the internet and nothing is kept.
  SIM_NOW=<ISO>     the clock stands still at that moment: datetime.now, date.today, time.time.
"""
import atexit
import base64
import datetime as _dt
import hashlib
import io
import json
import os
import threading
import time as _time
import urllib.error
import urllib.request

MODE = os.environ.get("SIM_HTTP", "replay")
CASSETTE = os.environ.get("SIM_CASSETTE", "")
MISSES = os.environ.get("SIM_MISSES", "")
NOW = os.environ.get("SIM_NOW", "")


# --- the clock ------------------------------------------------------------------------------------

if NOW:
    _frozen = _dt.datetime.fromisoformat(NOW)
    if _frozen.tzinfo is None:
        _frozen = _frozen.astimezone()          # the local zone of the run (TZ is set by the runner)
    _frozen_ts = _frozen.timestamp()
    _RealDate, _RealDateTime = _dt.date, _dt.datetime

    class _FrozenDate(_RealDate):
        @classmethod
        def today(cls):
            local = _RealDateTime.fromtimestamp(_frozen_ts)
            return cls(local.year, local.month, local.day)

    class _FrozenDateTime(_RealDateTime):
        @classmethod
        def now(cls, tz=None):
            real = _RealDateTime.fromtimestamp(_frozen_ts, tz)
            return cls(real.year, real.month, real.day, real.hour, real.minute, real.second,
                       real.microsecond, real.tzinfo)

        @classmethod
        def today(cls):
            return cls.now()

        @classmethod
        def utcnow(cls):
            return cls.now(_dt.timezone.utc).replace(tzinfo=None)

    _dt.date = _FrozenDate
    _dt.datetime = _FrozenDateTime
    _time.time = lambda: _frozen_ts


# --- chance ---------------------------------------------------------------------------------------
# Secret tokens are random, and a request that carries one (a payment's return address) would differ on
# every run and never be found in a cassette. With SIM_NOW set, secrets.token_* give a fixed series per
# home instead: the first command of a scenario gets the first value, the next command the next, and so on.

if NOW:
    import random as _random
    import secrets as _secrets

    def _next_seed():
        counter = os.path.join(os.environ.get("HOME", "."), ".sim-chance")
        try:
            with open(counter, encoding="utf-8") as f:
                n = int(f.read().strip() or 0)
        except (OSError, ValueError):
            n = 0
        try:
            with open(counter, "w", encoding="utf-8") as f:
                f.write(str(n + 1))
        except OSError:
            pass
        return n

    _chance = _random.Random(f"iris-sim-{_next_seed()}")

    def _token_bytes(nbytes=None):
        return bytes(_chance.getrandbits(8) for _ in range(nbytes or 32))

    _secrets.token_bytes = _token_bytes


# --- the internet ---------------------------------------------------------------------------------

_real_urlopen = urllib.request.urlopen
_lock = threading.Lock()
_tape = {}
_dirty = False


def _load():
    global _tape
    if CASSETTE and os.path.exists(CASSETTE):
        with open(CASSETTE, encoding="utf-8") as f:
            _tape = json.load(f).get("http", {})


def _save():
    if MODE != "record" or not _dirty or not CASSETTE:
        return
    with _lock:
        data = {}
        if os.path.exists(CASSETTE):
            with open(CASSETTE, encoding="utf-8") as f:
                data = json.load(f)
        data.setdefault("http", {}).update(_tape)
        data["http"] = dict(sorted(data["http"].items()))
        os.makedirs(os.path.dirname(CASSETTE), exist_ok=True)
        with open(CASSETTE + ".tmp", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
            f.write("\n")
        os.replace(CASSETTE + ".tmp", CASSETTE)


def key_of(method, url, body):
    """How a request is found back in the cassette: method, address, and a short hash of the body."""
    digest = hashlib.sha1(body).hexdigest()[:10] if body else "-"
    return f"{method} {url} {digest}"


def _encode(raw):
    try:
        return {"text": raw.decode("utf-8")}
    except UnicodeDecodeError:
        return {"base64": base64.b64encode(raw).decode()}


def _decode(entry):
    if "base64" in entry:
        return base64.b64decode(entry["base64"])
    return entry.get("text", "").encode("utf-8")


class _Headers:
    def __init__(self, content_type):
        self._type = content_type or "application/octet-stream"

    def get_content_type(self):
        return self._type.split(";")[0].strip()

    def get(self, name, default=None):
        return self._type if name.lower() == "content-type" else default

    def get_content_charset(self, default=None):
        return "utf-8"


class _Response(io.BytesIO):
    def __init__(self, raw, status, url, content_type):
        super().__init__(raw)
        self.status = self.code = status
        self.url = url
        self.headers = self.msg = _Headers(content_type)
        self.reason = "OK"

    def geturl(self):
        return self.url

    def getcode(self):
        return self.status

    def info(self):
        return self.headers

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _request_parts(req, data):
    if isinstance(req, str):
        return "POST" if data else "GET", req, data
    body = data if data is not None else req.data
    return req.get_method(), req.full_url, body


def _from_tape(entry, url):
    raw = _decode(entry)
    if entry["status"] >= 400:
        raise urllib.error.HTTPError(url, entry["status"], "recorded", None, io.BytesIO(raw))
    return _Response(raw, entry["status"], entry.get("url", url), entry.get("type", ""))


def _urlopen(req, data=None, timeout=None, **kw):
    global _dirty
    method, url, body = _request_parts(req, data)
    if isinstance(body, str):
        body = body.encode()
    key = key_of(method, url, body)
    if MODE == "replay":
        entry = _tape.get(key)
        if entry is None:
            if MISSES:
                with _lock, open(MISSES, "a", encoding="utf-8") as f:
                    f.write(key + "\n")
            raise urllib.error.URLError(f"not in the cassette: {key}")
        return _from_tape(entry, url)
    try:
        resp = _real_urlopen(req, data, timeout, **kw) if timeout is not None else _real_urlopen(req, data, **kw)
        raw = resp.read()
        entry = {"status": resp.status, "url": resp.geturl(), "type": resp.headers.get("Content-Type", "")}
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        entry = {"status": exc.code, "url": url, "type": exc.headers.get("Content-Type", "") if exc.headers else ""}
    entry.update(_encode(raw))
    # A rate limit or a server error says nothing about the plugin: never keep one, ask again next time.
    if MODE == "record" and entry["status"] != 429 and entry["status"] < 500:
        with _lock:
            _tape[key] = entry
            _dirty = True
    return _from_tape(entry, url)


if MODE in ("replay", "record", "live"):
    _load()
    urllib.request.urlopen = _urlopen
    atexit.register(_save)
