"""tron — the Telegram line to the operator.

The operator is elsewhere; that is the product. When `.env` (engine root)
carries TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID, milestone notes and pages
ride Telegram — a page WAITS for the operator's reply there, so a run
survives having no terminal. Unconfigured or unreachable, everything
degrades to the terminal exactly as before: the transport is an exit
ramp, never a dependency. Copy follows voice.md: terse, fact first,
routine vs contact-the-operator registers. Stdlib only.
"""

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV = ROOT / ".env"
ASK_TIMEOUT_S = 30 * 60       # a page waits this long before giving up
_state = {"loaded": False, "token": None, "chat": None, "offset": None}


def _load():
    if not _state["loaded"]:
        _state["loaded"] = True
        if ENV.exists():
            for line in ENV.read_text().splitlines():
                k, _, v = line.partition("=")
                if k.strip() == "TELEGRAM_BOT_TOKEN":
                    _state["token"] = v.strip().strip('"')
                if k.strip() == "TELEGRAM_CHAT_ID":
                    _state["chat"] = v.strip().strip('"')
    return _state["token"] and _state["chat"]


def _api(method, http_timeout, **params):
    # http_timeout is OURS (socket); params may carry Telegram's own
    # `timeout` (long-poll seconds) — the names must never collide: that
    # exact collision once TypeError'd every poll, silently, for 30 min.
    url = (f"https://api.telegram.org/bot{_state['token']}/{method}")
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(url, data=data, timeout=http_timeout) as r:
        return json.loads(r.read().decode())


def clip(text, limit=3900):
    """Telegram rejects >4096-char messages; a clipped page must still
    end with the ask, so the head is dropped, never the tail."""
    return text if len(text) <= limit else "…" + text[-limit:]


def note(text):
    """Fire-and-forget milestone line. False = not delivered (never raises
    — a milestone must not be able to take a run down)."""
    if not _load():
        return False
    try:
        return bool(_api("sendMessage", 10, chat_id=_state["chat"],
                         text=clip(text)).get("ok"))
    except Exception:
        return False


def _drain():
    """Advance past the backlog: anything sent BEFORE the page is stale
    context, never an answer to it."""
    try:
        for u in _api("getUpdates", 10, timeout=0).get("result", []):
            _state["offset"] = u["update_id"] + 1
    except Exception:
        pass


def ask(text, timeout_s=ASK_TIMEOUT_S):
    """Page the operator on Telegram and WAIT for the reply; None if the
    transport is unconfigured, undeliverable, or the wait expires — the
    caller falls back to the terminal."""
    if not _load():
        return None
    _drain()
    if not note(text):
        return None
    end, errors = time.time() + timeout_s, 0
    while time.time() < end:
        try:
            for u in _api("getUpdates", 60, timeout=50,
                          offset=_state["offset"] or 0).get("result", []):
                _state["offset"] = u["update_id"] + 1
                msg = u.get("message") or {}
                if (str(msg.get("chat", {}).get("id")) == _state["chat"]
                        and msg.get("text")):
                    return msg["text"].strip()
            errors = 0
        except Exception as e:
            errors += 1
            if errors == 3:   # a silently-broken poll must not look like
                return None   # a silent operator — surface the defect
            print(f"[TRON] telegram poll error ({errors}/3): {e!r}",
                  flush=True)
            time.sleep(5)
    return None


# -------------------------------------------------------------- selftest
def selftest():
    import sys
    saved = dict(_state)
    ok = []
    # unconfigured -> hard None/False, never an exception, never a wait
    _state.update(loaded=True, token=None, chat=None)
    ok += [note("x") is False, ask("x", timeout_s=1) is None]
    # clip keeps the tail (the ask), drops the head
    long = "H" * 5000 + " TAIL-ASK"
    ok += [clip("short") == "short", len(clip(long)) <= 3901,
           clip(long).endswith("TAIL-ASK"), clip(long).startswith("…")]
    # .env parsing tolerates quotes and unrelated lines
    import tempfile
    global ENV
    env = Path(tempfile.mkdtemp(prefix="tg-selftest-")) / ".env"
    env.write_text('OTHER=1\nTELEGRAM_BOT_TOKEN="t0k"\nTELEGRAM_CHAT_ID=42\n')
    saved_env, ENV = ENV, env
    _state.update(loaded=False, token=None, chat=None)
    ok += [_load() and _state["token"] == "t0k" and _state["chat"] == "42"]
    # end-to-end against a FAKE transport: the full ask() path — page out,
    # stale backlog drained, fresh answer in, offset confirmed. Every _api
    # call goes through the real signature (the timeout-name collision
    # that once broke every poll cannot come back unseen).
    calls = []
    stale = {"update_id": 7, "message":
             {"chat": {"id": 42}, "text": "stale, sent before the page"}}
    fresh = {"update_id": 8, "message":
             {"chat": {"id": 42}, "text": "  PROVISIONED: go  "}}

    class _FakeHTTP:
        def __init__(self, url, data, timeout):
            q = urllib.parse.parse_qs((data or b"").decode())
            calls.append((url.rsplit("/", 1)[1], q, timeout))
            if url.endswith("getUpdates"):
                have = int(q.get("offset", ["0"])[0] or 0)
                body = {"ok": True, "result":
                        [u for u in (stale, fresh) if u["update_id"] >= have
                         and not (u is fresh and len(calls) < 4)]}
            else:
                body = {"ok": True}
            self._body = json.dumps(body).encode()
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return self._body

    saved_open = urllib.request.urlopen
    urllib.request.urlopen = lambda url, data=None, timeout=None: \
        _FakeHTTP(url, data, timeout)
    ans = ask("the page", timeout_s=30)
    urllib.request.urlopen = saved_open
    polls = [c for c in calls if c[0] == "getUpdates" and "offset" in c[1]]
    ok += [ans == "PROVISIONED: go",              # fresh answer, stripped
           polls != [],                           # offset-bearing polls ran
           int(polls[0][1]["offset"][0]) == 8,    # stale backlog skipped
           _state["offset"] == 9,                 # answer confirmed
           any(c[0] == "sendMessage" for c in calls)]
    ENV = saved_env
    _state.update(saved)
    print(f"selftest: {sum(ok)}/{len(ok)} pass")
    sys.exit(0 if all(ok) else 1)


if __name__ == "__main__":
    selftest()
