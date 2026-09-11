"""tron — the Discord line to the operator.

Discord REST is used deliberately: outbound notes post to #tron and the
engine's normal wake poll reads recent human messages from that one channel.
The transport is optional; missing credentials or network failures never stop
the engine.
"""

import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV = ROOT / ".env"
# The operator-managed bot credential is shared by TRON worktrees.  Keep the
# engine-local file first for standalone installs and tests.
MODES_ENV = ROOT.parents[2] / "tron-modes" / ".env"
CHANNEL_ID = "1547918251651112971"
MESSAGE_URL = f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages"
_state = {"loaded": False, "token": None, "after": None}


def _load():
    if not _state["loaded"]:
        _state["loaded"] = True
        for env in (ENV, MODES_ENV):
            if not env.exists():
                continue
            for line in env.read_text().splitlines():
                key, _, value = line.partition("=")
                if key.strip() == "DISCORD_BOT_TOKEN":
                    _state["token"] = value.strip().strip('"')
                    break
            if _state["token"]:
                break
    return bool(_state["token"])


def _request(url, data=None, timeout=10):
    request = urllib.request.Request(
        url, data=data,
        headers={"Authorization": f"Bot {_state['token']}",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


def note(text):
    """Post one outbound note to #tron; return False on any delivery failure."""
    if not _load():
        return False
    try:
        _request(MESSAGE_URL, json.dumps({"content": text}).encode())
        return True
    except Exception:
        return False


def inbox():
    """Return unseen human messages in #tron, oldest first, once each."""
    if not _load():
        return []
    try:
        query = {"limit": 100}
        if _state["after"]:
            query["after"] = _state["after"]
        messages = _request(MESSAGE_URL + "?" + urllib.parse.urlencode(query))
    except Exception:
        return []
    if not isinstance(messages, list):
        return []
    if messages:
        _state["after"] = max(message["id"] for message in messages)
    return [message.get("content", "").strip() for message in reversed(messages)
            if not message.get("author", {}).get("bot")
            and message.get("content", "").strip()]
