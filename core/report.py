"""core.report — the typed, identity-slot-free drained-report record (block
01-38 T2, ADR-0012 root invariant). `core/snapshot.py::_classify_reports` is
the ONE place a `Report` is constructed; every `core/*.py` module downstream
(`core/router.py`, `core/gate.py`, `core/casestate.py`, `core/architect.py`,
`core/liveness.py`, `core/reviewers.py`, `core/sentry.py`, ...) receives one.

## Why a type, not a value that happens to be empty

Before this task, a drained report was a plain `dict`. Any caller could read
`rep.get("sender")` / `rep["agent_id"]` / `rep.get("worker_id")` and get back
whatever the MESSAGE claimed (forgeable — the exact root-invariant failure
mode) or, if the field happened to be absent, a silent `None` — a value
indistinguishable from "no claim was made". Both are the same bug: a
forgeable read that quietly degrades instead of failing loud.

`Report` fixes this at the type level. Every OTHER key a resolved report may
carry — `tag`, `slots`, `block`, `branch`, `triage_id`, `verdict`, `text`,
`case_id`, `origin`, `at`, ... — behaves EXACTLY like a plain dict (every
non-identity consumer across `core/*.py` this task does not touch keeps
working unmodified). But the five message-borne identity keys the root
invariant names — `sender`, `worker`, `actor`, `agent_id`, `worker_id` — are
refused at EVERY read and write surface (`__getitem__`, `get`, `__contains__`,
`setdefault`, `__setitem__`, `pop`): reading one raises `IdentityNotOnMessage`
(a `TypeError`), never returns `None`. Reading a claimed identity off a
message is an attribute/type error BY CONSTRUCTION now, not a lookup that
happens to come back empty — this is the PRIMARY guarantee of the root
invariant; `core/identity_backstop_rig.py`'s structural grep is only its
tripwire, never the guarantee itself.

Writing one of the five keys is refused too (not merely reading) — a rig or
a future caller cannot smuggle identity back onto an already-built `Report`
through a second, dict-shaped path; the ONLY way a `Report` carries identity
at all is its own `origin` key (a `core.intake.Origin` namedtuple), stamped
exactly once by `core/snapshot.py::_classify_reports` from WHICH intake the
raw line drained from — never from anything the raw line's body claims.

`Report` is deliberately still dict-shaped for its legal keys (`.get`,
`[...]`, `in`, iteration all forward normally) — this is not a redesign of
every downstream `.get("block")`/`.get("tag")` call site (~20 of them, none
in this task's fixed reader set), only a structural refusal of the five
identity keys specifically.
"""
import collections.abc

FORBIDDEN_IDENTITY_KEYS = frozenset({"sender", "worker", "actor", "agent_id", "worker_id"})


class IdentityNotOnMessage(TypeError):
    """Raised by `Report` (read OR write) for one of the five message-borne
    identity keys the root invariant forbids: `sender`, `worker`, `actor`,
    `agent_id`, `worker_id`. Block 01-38 T2 — the drained report carries no
    such slot; this is a type error by construction, never a value that
    happens to be empty. The typed `core.intake.Origin` (a `Report`'s own
    `origin` key) is the SOLE legal way to learn who sent a report."""

    def __init__(self, key, action="read"):
        super().__init__(
            f"{key!r} may not be {action} on a drained report (block 01-38 "
            f"T2, the ADR-0012 root invariant) — a message carries no "
            f"identity slot; identity is read from the typed Origin "
            f"(rep['origin']), never claimed by the message body")
        self.key = key


def _deny(key, action):
    raise IdentityNotOnMessage(key, action)


class Report(collections.abc.MutableMapping):
    """A drained/admitted report — dict-shaped for every key except the five
    identity keys `FORBIDDEN_IDENTITY_KEYS` names (see module docstring).
    Backed by a plain `dict` internally; every read/write of a forbidden key
    raises `IdentityNotOnMessage` instead of returning/storing a value."""

    __slots__ = ("_data",)

    def __init__(self, data=None):
        self._data = {}
        for k, v in dict(data or {}).items():
            self[k] = v   # routes every key through __setitem__'s own guard

    def __getitem__(self, key):
        if key in FORBIDDEN_IDENTITY_KEYS:
            _deny(key, "read")
        return self._data[key]

    def __setitem__(self, key, value):
        if key in FORBIDDEN_IDENTITY_KEYS:
            _deny(key, "written onto")
        self._data[key] = value

    def __delitem__(self, key):
        if key in FORBIDDEN_IDENTITY_KEYS:
            _deny(key, "read")
        del self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)

    def __contains__(self, key):
        if key in FORBIDDEN_IDENTITY_KEYS:
            _deny(key, "read")
        return key in self._data

    def get(self, key, default=None):
        if key in FORBIDDEN_IDENTITY_KEYS:
            _deny(key, "read")
        return self._data.get(key, default)

    def setdefault(self, key, default=None):
        if key in FORBIDDEN_IDENTITY_KEYS:
            _deny(key, "written onto")
        return self._data.setdefault(key, default)

    def pop(self, key, *default):
        if key in FORBIDDEN_IDENTITY_KEYS:
            _deny(key, "read")
        return self._data.pop(key, *default)

    def __repr__(self):
        return f"Report({self._data!r})"
