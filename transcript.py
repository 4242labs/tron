"""tron-reborn — transcript + terminal I/O.

Everything any LLM agent says (and everything the engine says to it) is
logged verbatim, one file per run, under runs/. The operator's terminal
exchanges go through here too, so the transcript is complete.
"""

import os
import threading
import time

import events
import tg

LOG_PATH = None
SAY_HOOK = None               # roster.event when a run binds its report
_OP_LOCK = threading.Lock()   # one operator, one terminal — pages serialize


def set_log(path):
    global LOG_PATH
    LOG_PATH = path
    print(f"[TRON] transcript: {path}", flush=True)


def log_entry(header, text):
    if LOG_PATH:
        with open(LOG_PATH, "a") as fh:
            fh.write(f"\n--- {time.strftime('%H:%M:%S')} {header} ---\n{text}\n")


def say(tag, text):
    print(f"[TRON] {tag}: {text}", flush=True)
    log_entry(f"TRON event: {tag}", text)
    if SAY_HOOK:
        SAY_HOOK(f"{tag}: {text}")


def halt(msg):
    """Engine-fatal stop that works from ANY thread (a thread's sys.exit
    only kills the thread — a silently dead block must be impossible)."""
    print(f"\n[TRON] {msg}", flush=True)
    log_entry("TRON halt", msg)
    os._exit(1)


def operator(context):
    """Page the operator and WAIT for the answer. Telegram first when
    configured (the operator is elsewhere; the reply is the dependency),
    the terminal as fallback — a page must never be droppable."""
    with _OP_LOCK:
        print("\n" + "=" * 60)
        print(f"[TRON -> OPERATOR] {context}")
        log_entry("TRON -> OPERATOR", context)
        events.emit("page", context=context[:200])
        ans = tg.ask("[TRON] Hey boss — the fleet needs you.\n\n"
                     + context + "\n\nReply here; your answer goes "
                     "straight back in.")
        if ans is None:
            try:
                ans = input("OPERATOR> ").strip()
            except EOFError:
                halt("halted: operator needed but no terminal input "
                     "available (and no Telegram answer)")
        else:
            print(f"OPERATOR (telegram)> {ans}")
        if ans.lower() in ("abort", "quit", "exit"):
            halt("aborted by operator")
        log_entry("OPERATOR -> TRON", ans)
        events.emit("answer", answer=ans[:200])
        return ans
