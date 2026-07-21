#!/usr/bin/env python3
"""tron-reborn — the workflow as a BPMN diagram, generated.

workflow.toml is the single source of the process; this module derives
the interactive BPMN diagram from the SAME parsed table workflow.py
lints and tron.py executes — the diagram cannot drift from the flow.

`python3 bpmn.py --write` regenerates workflow/workflow.bpmn (BPMN 2.0
XML, spec-complete: every node carries <incoming>/<outgoing>) and
workflow/workflow.html (self-contained viewer on the vendored bpmn-js);
selftests fail when either is stale. Layout follows the authoring
guidelines (tron-app/docs/bpmn.md): token-driven track grid, integer
(col,row), one lane per actor + an ENGINE lane for gates and landings,
gateways always marked, no edge labels (node names carry semantics).

The generated files are NOT published anywhere yet — the tron-www sync
hook is deliberately absent until 0.4.2 (operator ruling 260716).
"""

import base64
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

import workflow

ROOT = Path(__file__).resolve().parent
DIR = ROOT / "workflow"
BPMN = DIR / "workflow.bpmn"
HTML = DIR / "workflow.html"
VENDOR = "vendor/bpmn-viewer.production.min.js"

TOK = {                      # every size/gap comes from here, nothing twice
    # uniform cell: a column is the width of the widest element (a task); a
    # gateway/event sits centred in its full-size cell (bpmn.md §1)
    "cellW": 138,            # uniform column content width
    "taskW": 128, "taskH": 58, "gw": 42, "ev": 30,
    "colGap": 48,            # one gap between columns, laid edge-to-edge
    "pitchX": 186,           # column pitch = cellW + colGap
    "laneH": 92,             # uniform lane row height = one actor lane
    "laneBand": 30,          # matches bpmn-js's fixed pool label-band width,
                             # so the pool-title divider and the lane left
                             # edges fall on ONE line (no 4px step)
    "bandGap": 0,            # lanes tile as one cohesive block (no band gap)
    "pad": 28,               # one symmetric pool padding, all sides
    "dock": 0.28,            # ¼-ish dock offset that separates parallel edges
    "poolX": 40, "poolY": 40,
}
NS = {
    "bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",
    "bpmndi": "http://www.omg.org/spec/BPMN/20100524/DI",
    "dc": "http://www.omg.org/spec/DD/20100524/DC",
    "di": "http://www.omg.org/spec/DD/20100524/DI",
}

# The published tron-app diagram's brand skin, baked in so every --write
# reproduces it (the look cannot drift from a hand-tuned copy). Same
# vendored bpmn-js viewer as the live page; the 42labs design tokens, the
# fonts, the TRON logomark, and the compact warm canvas come from here.
# Node fills carry meaning: the two escalation tiers read as the LLM
# architect (emerald) and the terminal operator (sky), matching the live
# map's AIDE/OPERATOR palette.
LOGO_SVG = (
    '<svg class="logo__svg" viewBox="0 0 150 27" fill="none" '
    'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="TRON">'
    '<path class="logo__mark" d="M23.5389 25.5945C23.5389 26.2534 23.004 26.7876 22.3442 26.7876H20.7762C20.716 26.7876 20.6567 26.7831 20.5989 26.7745C20.541 26.7831 20.4818 26.7876 20.4215 26.7876H1.19468C0.534876 26.7876 0 26.2534 0 25.5945V24.0659C0 23.407 0.534876 22.8728 1.19468 22.8728H8.82942V16.2481C8.82942 15.4791 9.45284 14.8557 10.2219 14.8557H11.3944C12.1634 14.8557 12.7868 15.4791 12.7868 16.2482V22.8728H19.5815V16.2481C19.5815 15.4791 20.2049 14.8557 20.974 14.8557H22.1465C22.9155 14.8557 23.5389 15.4791 23.5389 16.2482V25.5945Z"/>'
    '<path class="logo__mark" d="M11.5921 0.279053C11.6524 0.279053 11.7116 0.283274 11.7695 0.291869C11.8273 0.283274 11.8865 0.279053 11.9468 0.279053H31.1736C31.8334 0.279053 32.3683 0.813209 32.3683 1.47212V3.00075C32.3683 3.65966 31.8334 4.19382 31.1736 4.19382H23.5389V10.5575C23.5389 11.3265 22.9155 11.95 22.1465 11.95H20.974C20.2049 11.95 19.5815 11.3265 19.5815 10.5575V4.19382H12.7868V10.5575C12.7868 11.3265 12.1634 11.95 11.3944 11.95H10.2219C9.45284 11.95 8.82942 11.3265 8.82942 10.5575V1.47212C8.82942 0.813209 9.3643 0.279053 10.0241 0.279053H11.5921Z"/>'
    '<path class="logo__type" d="M89.728 8.75482C89.728 9.78958 89.6001 10.7139 89.3443 11.5278C89.0886 12.3416 88.7398 13.0625 88.298 13.6903C87.8678 14.3065 87.3678 14.8355 86.7981 15.2773C86.2284 15.7191 85.6297 16.0854 85.0018 16.376C84.3856 16.6551 83.7578 16.8585 83.1183 16.9864C82.4905 17.1143 81.8975 17.1783 81.3395 17.1783L90.8093 25.3575H83.7985L74.3461 17.1783H72.201C71.5846 17.1783 71.0848 16.6785 71.0848 16.0621V13.7601C71.0848 13.1436 71.5846 12.6439 72.201 12.6439H81.3395C81.9092 12.5974 82.4265 12.4811 82.8916 12.2951C83.3683 12.0975 83.7752 11.8359 84.1124 11.5103C84.4612 11.1848 84.7286 10.7953 84.9146 10.3418C85.1007 9.87678 85.1937 9.34777 85.1937 8.75482V5.89469C85.1937 5.6389 85.1588 5.44706 85.089 5.31917C85.0309 5.17965 84.9495 5.08083 84.8449 5.02269C84.7519 4.95293 84.6472 4.91224 84.531 4.90061C84.4263 4.88899 84.3275 4.88317 84.2345 4.88317H69.2711V25.3575H64.7367V2.63344C64.7367 2.31952 64.7949 2.02304 64.9111 1.74401C65.0274 1.46497 65.1844 1.22081 65.382 1.01153C65.5913 0.802254 65.8354 0.639483 66.1145 0.523217C66.3935 0.406952 66.6958 0.348819 67.0214 0.348819H84.2345C85.246 0.348819 86.1005 0.534844 86.7981 0.906893C87.4957 1.26732 88.0596 1.72657 88.4898 2.28464C88.9316 2.83109 89.2455 3.42404 89.4315 4.0635C89.6292 4.70296 89.728 5.30173 89.728 5.85981V8.75482Z"/>'
    '<path class="logo__type" d="M51.3778 25.5668H46.8435V15.9052C46.8435 15.2887 47.3432 14.789 47.9596 14.789H50.2617C50.8781 14.789 51.3778 15.2887 51.3778 15.9052V25.5668Z"/>'
    '<path class="logo__type" d="M61.3709 3.9763C61.3709 4.59274 60.8711 5.09245 60.2547 5.09245H51.3778V10.8825C51.3778 11.4989 50.8781 11.9986 50.2617 11.9986H47.9596C47.3432 11.9986 46.8435 11.4989 46.8435 10.8825V5.09245H37.9492C37.3327 5.09245 36.833 4.59274 36.833 3.9763V1.67425C36.833 1.05781 37.3327 0.558097 37.9492 0.558097H60.2547C60.8711 0.558097 61.3709 1.05781 61.3709 1.67425V3.9763Z"/>'
    '<path class="logo__type" d="M98.5875 15.2424C98.5875 16.1377 98.727 16.9515 99.006 17.684C99.2967 18.4049 99.7036 19.0269 100.227 19.5501C100.75 20.0616 101.372 20.4628 102.093 20.7534C102.825 21.0325 103.633 21.172 104.517 21.172H110.621C111.505 21.172 112.307 21.0325 113.028 20.7534C113.76 20.4628 114.388 20.0616 114.911 19.5501C115.434 19.0269 115.835 18.4049 116.114 17.684C116.405 16.9515 116.55 16.1377 116.55 15.2424C116.55 14.992 116.753 14.789 117.004 14.789H120.631C120.882 14.789 121.085 14.992 121.085 15.2424C121.085 16.7655 120.823 18.1665 120.3 19.4454C119.777 20.7244 119.05 21.8289 118.12 22.759C117.19 23.6891 116.085 24.4158 114.807 24.939C113.539 25.4506 112.156 25.7063 110.656 25.7063H104.517C103.017 25.7063 101.628 25.4506 100.349 24.939C99.07 24.4158 97.9654 23.6891 97.0353 22.759C96.1052 21.8289 95.3727 20.7244 94.8379 19.4454C94.3147 18.1665 94.0531 16.7655 94.0531 15.2424C94.0531 14.992 94.2561 14.789 94.5065 14.789H98.134C98.3844 14.789 98.5875 14.992 98.5875 15.2424Z"/>'
    '<path class="logo__type" d="M110.656 2.20737e-05C112.156 2.20737e-05 113.539 0.26162 114.807 0.784815C116.085 1.30801 117.19 2.03467 118.12 2.96479C119.05 3.88329 119.777 4.98781 120.3 6.27836C120.823 7.55728 121.085 8.95247 121.085 10.4639V10.8825C121.085 11.4989 120.585 11.9986 119.969 11.9986H117.667C117.05 11.9986 116.55 11.4989 116.55 10.8825V10.4639C116.55 9.56868 116.405 8.76063 116.114 8.03978C115.835 7.30731 115.434 6.68529 114.911 6.17372C114.4 5.65053 113.778 5.24941 113.045 4.97037C112.324 4.67971 111.528 4.53438 110.656 4.53438H104.517C103.633 4.53438 102.825 4.67971 102.093 4.97037C101.372 5.24941 100.75 5.65053 100.227 6.17372C99.7036 6.68529 99.2967 7.30731 99.006 8.03978C98.727 8.76063 98.5875 9.56868 98.5875 10.4639V10.8825C98.5875 11.4989 98.0877 11.9986 97.4713 11.9986H95.1693C94.5528 11.9986 94.0531 11.4989 94.0531 10.8825V10.4639C94.0531 8.95247 94.3147 7.55728 94.8379 6.27836C95.3727 4.98781 96.1052 3.88329 97.0353 2.96479C97.9654 2.03467 99.07 1.30801 100.349 0.784815C101.628 0.26162 103.017 2.20737e-05 104.517 2.20737e-05H110.656Z"/>'
    '<path class="logo__type" d="M126.404 0.170605C126.834 -0.00378947 127.276 -0.044484 127.729 0.0485266C128.183 0.129911 128.572 0.339198 128.898 0.676361L142.157 14.5075L142.142 14.5225L143.822 16.245L145.466 17.9592V17.929L150 22.5756V23.4179C150 23.7434 149.936 24.0457 149.808 24.3248C149.692 24.6038 149.529 24.848 149.32 25.0572C149.122 25.2549 148.884 25.4119 148.605 25.5281C148.326 25.6444 148.029 25.7025 147.715 25.7025C147.436 25.7025 147.152 25.6502 146.861 25.5456C146.582 25.4409 146.332 25.2723 146.111 25.0398L129.543 7.73949V25.3537H125.009V2.28083C125.009 1.81577 125.137 1.3972 125.392 1.02516C125.66 0.641489 125.997 0.356628 126.404 0.170605Z"/>'
    '<path class="logo__type" d="M148.884 0.345004C149.5 0.345004 150 0.844721 150 1.46115V15.8381C150 16.8391 148.784 17.3338 148.085 16.6175L145.783 14.2584C145.58 14.05 145.466 13.7703 145.466 13.4791V1.46115C145.466 0.844721 145.965 0.345004 146.582 0.345004H148.884Z"/>'
    '</svg>')

# The browser-tab favicon is the TRON glyph — the same two logo__mark paths
# the topbar wordmark uses (single source, nothing drawn twice), as a
# self-contained data URI so the standalone file carries its own icon.
FAVICON = "data:image/svg+xml;base64," + base64.b64encode((
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 33 27">'
    + "".join(f'<path fill="#E2711D" d="{d}"/>'
              for d in re.findall(r'class="logo__mark" d="([^"]+)"', LOGO_SVG))
    + '</svg>').encode()).decode()


# ----------------------------------------------------------- the graph
def spine(flow):
    """Phases in pass-spine order (lint guarantees next reaches landed),
    then any remaining phases in file order — every node gets a column."""
    byid = {ph["id"]: ph for ph in flow["phase"]}
    out, cur = [], flow["phase"][0]["id"]
    while cur != workflow.END and byid[cur] not in out:
        out.append(byid[cur])
        cur = byid[cur]["next"]
    return out + [ph for ph in flow["phase"] if ph not in out]


def _balance(text, cap=12):
    """Wrap a label into ~2 balanced lines — split so the widest line is as
    narrow as possible; short or one-word labels stay on one line. Generic
    and automated (no per-node hand-tuning): centred multi-line node text."""
    words = text.split()
    if len(words) < 2 or len(text) <= cap:
        return text
    best = None
    for k in range(1, len(words)):
        a, b = " ".join(words[:k]), " ".join(words[k:])
        widest = max(len(a), len(b))
        if best is None or widest < best[0]:
            best = (widest, a + "\n" + b)
    return best[1]


def graph(flow):
    """The diagram as data: nodes {id,kind,name,lane,col} + flows
    (source,target), then laid out (each node gets cx,cy). Swimlanes,
    row = actor (bpmn.md §2): ENGINE on top (gates, landings, register),
    then one lane per actor, then the two escalation tiers. A work phase's
    task and its gate STACK in one column (§2, answer→gateway in a column);
    the exception spine is a compact band below, its own columns."""
    lanes = (["engine"] + list(dict.fromkeys(
        ph["actor"] for ph in flow["phase"])) + list(workflow.ESC_TIERS))
    nodes, flows = [], []

    def node(nid, kind, name, lane, col):
        nodes.append({"id": nid, "kind": kind, "name": name,
                      "lane": lanes.index(lane), "col": col})

    # --- the pass spine: start, then each phase as task(actor)+gate(engine)
    #     stacked in one column; a landing takes the next engine column ---
    node("start", "start", ">tron start", "engine", 0)
    prev, col = "start", 0
    for ph in spine(flow):
        pid = ph["id"]
        col += 1
        # a task is an ACTIVITY, named by its verb; the swimlane already names
        # the actor, so the verb alone follows BPMN (verb, object implicit)
        node(f"task_{pid}", "task", _balance(pid.capitalize()),
             ph["actor"], col)
        flows.append((prev, f"task_{pid}"))            # forward feed → task L
        # a gateway is the verification DECISION, phrased as a question; the
        # closing word + gate detail live in the notes panel (bpmn.md §4)
        if ph["kind"] == "work":
            node(f"gw_{pid}", "gateway", f"{ph['word'].capitalize()}?",
                 "engine", col)
            flows += [(f"task_{pid}", f"gw_{pid}"),     # up to the gate
                      (f"gw_{pid}", f"task_{pid}")]     # bounce back, capped
        else:
            node(f"gw_{pid}", "gateway", f"{ph['pass_word'].capitalize()}?",
                 "engine", col)
            flows += [(f"task_{pid}", f"gw_{pid}"),
                      (f"gw_{pid}", f"task_{ph['on_reject']}")]  # reject back
        prev = f"gw_{pid}"
        if ph.get("land"):
            col += 1
            node(f"land_{pid}", "task", _balance("Land on the trunk"),
                 "engine", col)
            flows.append((prev, f"land_{pid}"))
            prev = f"land_{pid}"
    col += 1
    node("end", "end", "Done", "engine", col)
    flows.append((prev, "end"))

    # --- the EXCEPTION band (workflow.ESCALATION), a compact block in its
    #     own architect/operator rows below the pass spine. A stuck seat
    #     climbs the architect-first ladder: the architect rules (back to
    #     the seat) or the signal reaches the operator, whose answer syncs
    #     back. Same table the engine routes from — the drawing can't drift.
    arch, oper = workflow.ESC_TIERS[0], workflow.ESC_TIERS[-1]
    node("esc_start", "start", "Seat stuck", arch, 1)
    node("esc_arch", "task", "Judge", arch, 2)
    node("esc_gw", "gateway", "Rule or escalate?", arch, 3)
    node("esc_ruling", "end", "Resolved", arch, 4)
    node("esc_op", "task", "Answer", oper, 3)
    flows += [("esc_start", "esc_arch"),         # stuck -> architect
              ("esc_arch", "esc_gw"),
              ("esc_gw", "esc_ruling"),          # ruling -> seat
              ("esc_gw", "esc_op"),              # escalate/recurrence -> op
              ("esc_op", "esc_arch")]            # operator answer syncs back
    layout(lanes, nodes)
    return lanes, nodes, flows


# -------------------------------------------------------------- layout
def _pass_lanes(lanes):
    return len(lanes) - len(workflow.ESC_TIERS)


def layout(lanes, nodes):
    """Derive each node's centre (cx,cy) from its integer (col,row): same
    column → shared centre-X, same lane → shared centre-Y (bpmn.md §1). One
    symmetric pad; the exception band drops by an extra bandGap of breathing
    space below the pass band."""
    ox = TOK["poolX"] + TOK["laneBand"] + TOK["pad"]
    passn = _pass_lanes(lanes)
    for n in nodes:
        n["cx"] = ox + n["col"] * TOK["pitchX"] + TOK["cellW"] // 2
        band = TOK["bandGap"] if n["lane"] >= passn else 0
        n["cy"] = (TOK["poolY"] + n["lane"] * TOK["laneH"] + band
                   + TOK["laneH"] // 2)
    return nodes


def _size(n):
    return {"task": (TOK["taskW"], TOK["taskH"]),
            "gateway": (TOK["gw"], TOK["gw"]),
            "start": (TOK["ev"], TOK["ev"]),
            "end": (TOK["ev"], TOK["ev"])}[n["kind"]]


def _center(n):
    return n["cx"], n["cy"]


def _bounds(n):
    w, h = _size(n)
    cx, cy = _center(n)
    return cx - w // 2, cy - h // 2, w, h


def _colgap_x(col):
    """The centre of the vertical channel in the gap just right of `col` —
    where a cross-row segment runs so it crosses no node (bpmn.md §3)."""
    ox = TOK["poolX"] + TOK["laneBand"] + TOK["pad"]
    return ox + (col + 1) * TOK["pitchX"] - TOK["colGap"] // 2


def _candidates(src, tgt, solo=False):
    """Every sensible orthogonal path from src to tgt, fewest-turns kinds
    first, so route() can PICK the shortest clean one rather than assume a
    shape (bpmn.md §3): a 0-turn straight when the two line up, two 1-bend
    L's (vert-then-horiz, horiz-then-vert), and the two 2-bend gap-channel
    doglegs that are always clear. A stacked pair that carries edges BOTH
    ways (task↔gate) offsets each to an opposite side so both arrows stay
    visible; a lone edge (`solo`) docks dead-centre, off the node's point."""
    sx, sy, sw, sh = _bounds(src)
    tx, ty, tw, th = _bounds(tgt)
    scx, scy = _center(src)
    tcx, tcy = _center(tgt)
    if src["col"] == tgt["col"]:
        off = 0 if solo else max(6, min(sw, tw) // 2 - 6)
        if tgt["lane"] > src["lane"]:
            return [[(scx + off, sy + sh), (scx + off, ty)]]
        return [[(scx - off, sy), (scx - off, ty + th)]]
    down, right = tcy > scy, tcx > scx
    sv = sy + sh if down else sy                       # src top/bottom exit
    shx = sx + sw if right else sx                     # src left/right exit
    tv = ty if down else ty + th                       # tgt top/bottom entry
    thx = tx if right else tx + tw                     # tgt left/right entry
    cands = []
    if scx == tcx:
        cands.append([(scx, sv), (tcx, tv)])           # 0-turn straight
    if scy == tcy:
        cands.append([(shx, scy), (thx, tcy)])
    cands.append([(scx, sv), (scx, tcy), (thx, tcy)])  # 1 bend: vert → horiz
    cands.append([(shx, scy), (tcx, scy), (tcx, tv)])  # 1 bend: horiz → vert
    xc = _colgap_x(min(src["col"], tgt["col"]))        # 2 bend: colGap channel
    cands.append([(shx, scy), (xc, scy), (xc, tcy), (thx, tcy)])
    ych = max(sy + sh, ty + th) + (TOK["laneH"] - max(sh, th)) // 2 - 4
    cands.append([(scx, sy + sh), (scx, ych),          # 2 bend: rowGap channel
                  (tcx, ych), (tcx, ty + th)])
    return cands


def _len(pts):
    return sum(abs(a[0] - b[0]) + abs(a[1] - b[1])
               for a, b in zip(pts, pts[1:]))


def _clean(pts, nodes, s, t):
    """The polyline crosses no node except its own two endpoints."""
    for n in nodes:
        if n["id"] in (s, t):
            continue
        bx, by, w, h = _bounds(n)
        if any(_hits_node(pts[i], pts[i + 1], (bx, by, bx + w, by + h))
               for i in range(len(pts) - 1)):
            return False
    return True


def route(src, tgt, nodes, solo=False):
    """The fewest-turns (tie → shortest) orthogonal path that crosses no
    other node — bpmn.md §3, chosen from the candidates, never assumed."""
    cands = _candidates(src, tgt, solo)
    clean = [p for p in cands if _clean(p, nodes, src["id"], tgt["id"])]
    return min(clean or cands, key=lambda p: (_turns(p), _len(p)))


# --------------------------------------------- the shortest-path invariant
# bpmn.md §3 as an enforced rule (not a guideline): every edge is orthogonal,
# crosses no node it does not connect, and takes the fewest turns ACHIEVABLE
# for its endpoints — measured against the same candidate set route() chooses
# from, so "minimal" means minimal in fact, not a hand-guessed floor. The
# selftest fails the build if any route beats none of its clean alternatives.
def _turns(pts):
    d = [(0 if b[0] == a[0] else (b[0] > a[0]) - (a[0] > b[0]),
          0 if b[1] == a[1] else (b[1] > a[1]) - (a[1] > b[1]))
         for a, b in zip(pts, pts[1:])]
    return sum(1 for a, b in zip(d, d[1:]) if a != b)


def _hits_node(p, q, box, m=4):
    """Does the axis-aligned segment p→q pass through box's interior
    (shrunk by m, so docking on an edge does not count)?"""
    x0, y0, x1, y1 = box[0] + m, box[1] + m, box[2] - m, box[3] - m
    if x1 <= x0 or y1 <= y0:
        return False
    (ax, ay), (bx, by) = p, q
    if ax == bx:                                # vertical
        lo, hi = sorted((ay, by))
        return x0 < ax < x1 and lo < y1 and hi > y0
    lo, hi = sorted((ax, bx))                   # horizontal
    return y0 < ay < y1 and lo < x1 and hi > x0


def routing_faults(lanes, nodes, flows):
    """Every edge that breaks the invariant — empty = all clean. An edge is
    faulty if it is non-orthogonal, crosses a node, or turns more than the
    best clean candidate for the same endpoints (i.e. not turn-minimal)."""
    byid = {n["id"]: n for n in nodes}
    pairs = set(flows)
    bad = []
    for s, t in flows:
        src, tgt = byid[s], byid[t]
        solo = (t, s) not in pairs
        pts = route(src, tgt, nodes, solo)
        why = []
        if any(px != qx and py != qy for (px, py), (qx, qy)
               in zip(pts, pts[1:])):
            why.append("not orthogonal")
        if not _clean(pts, nodes, s, t):
            why.append("crosses a node")
        clean = [p for p in _candidates(src, tgt, solo)
                 if _clean(p, nodes, s, t)]
        best = min((_turns(p) for p in clean), default=_turns(pts))
        if _turns(pts) > best:
            why.append(f"turns {_turns(pts)} > {best}")
        if why:
            bad.append((s, t, "; ".join(why)))
    return bad


# ----------------------------------------------------------------- XML
def render_bpmn(flow=None):
    flow = flow or workflow.parse_file()
    lanes, nodes, flows = graph(flow)
    byid = {n["id"]: n for n in nodes}
    inc = {n["id"]: [] for n in nodes}
    out = {n["id"]: [] for n in nodes}
    fids = []
    for i, (s, t) in enumerate(flows):
        fid = f"flow_{i}"
        fids.append(fid)
        out[s].append(fid)
        inc[t].append(fid)

    ncols = max(n["col"] for n in nodes) + 1
    pool_w = TOK["laneBand"] + 2 * TOK["pad"] + (ncols - 1) * TOK["pitchX"] \
        + TOK["cellW"]
    pool_h = len(lanes) * TOK["laneH"] + TOK["bandGap"]
    tag = {"task": "task", "gateway": "exclusiveGateway",
           "start": "startEvent", "end": "endEvent"}

    x = ['<?xml version="1.0" encoding="UTF-8"?>',
         "<!-- GENERATED from workflow.toml by bpmn.py - do not edit;"
         " regenerate: python3 bpmn.py -(-)write -->",
         '<bpmn:definitions ' + " ".join(
             f'xmlns:{k}="{v}"' for k, v in NS.items())
         + ' id="defs" targetNamespace="https://tron.42labs.io/workflow">',
         '  <bpmn:collaboration id="collab">',
         '    <bpmn:participant id="pool" name="workflow.toml"'
         ' processRef="proc"/>',
         '  </bpmn:collaboration>',
         '  <bpmn:process id="proc" isExecutable="false">',
         '    <bpmn:laneSet id="lanes">']
    for i, lane in enumerate(lanes):
        x.append(f'      <bpmn:lane id="lane_{lane}" '
                 f'name={quoteattr(lane.upper())}>')
        x += [f'        <bpmn:flowNodeRef>{n["id"]}</bpmn:flowNodeRef>'
              for n in nodes if n["lane"] == i]
        x.append('      </bpmn:lane>')
    x.append('    </bpmn:laneSet>')
    for n in nodes:
        name = escape(n["name"]).replace("\n", "&#10;")
        x.append(f'    <bpmn:{tag[n["kind"]]} id="{n["id"]}" name="{name}">')
        x += [f'      <bpmn:incoming>{f}</bpmn:incoming>'
              for f in inc[n["id"]]]
        x += [f'      <bpmn:outgoing>{f}</bpmn:outgoing>'
              for f in out[n["id"]]]
        x.append(f'    </bpmn:{tag[n["kind"]]}>')
    for fid, (s, t) in zip(fids, flows):
        x.append(f'    <bpmn:sequenceFlow id="{fid}" sourceRef="{s}" '
                 f'targetRef="{t}"/>')
    x += ['  </bpmn:process>',
          '  <bpmndi:BPMNDiagram id="dia">',
          '    <bpmndi:BPMNPlane id="plane" bpmnElement="collab">',
          '      <bpmndi:BPMNShape id="pool_di" bpmnElement="pool" '
          'isHorizontal="true">',
          f'        <dc:Bounds x="{TOK["poolX"]}" y="{TOK["poolY"]}" '
          f'width="{pool_w}" height="{pool_h}"/>',
          '      </bpmndi:BPMNShape>']
    passn = _pass_lanes(lanes)
    for i, lane in enumerate(lanes):
        band = TOK["bandGap"] if i >= passn else 0
        x += [f'      <bpmndi:BPMNShape id="lane_{lane}_di" '
              f'bpmnElement="lane_{lane}" isHorizontal="true">',
              f'        <dc:Bounds x="{TOK["poolX"] + TOK["laneBand"]}" '
              f'y="{TOK["poolY"] + i * TOK["laneH"] + band}" '
              f'width="{pool_w - TOK["laneBand"]}" '
              f'height="{TOK["laneH"]}"/>',
              '      </bpmndi:BPMNShape>']
    for n in nodes:
        bx, by, w, h = _bounds(n)
        marker = ' isMarkerVisible="true"' if n["kind"] == "gateway" else ""
        shape = [f'      <bpmndi:BPMNShape id="{n["id"]}_di" '
                 f'bpmnElement="{n["id"]}"{marker}>',
                 f'        <dc:Bounds x="{bx}" y="{by}" width="{w}" '
                 f'height="{h}"/>']
        # external labels (events, gateways) get explicit bounds so they sit
        # on a clear side — gateways above the diamond, events below — never
        # over an edge or the task beneath (bpmn.md §4). Tasks label inside.
        if n["kind"] in ("gateway", "start", "end"):
            lines = n["name"].split("\n")
            lw = max((len(s) for s in lines), default=1) * 7 + 10
            lh = len(lines) * 14 + 4
            lx = _center(n)[0] - lw // 2
            ly = by - lh - 3 if n["kind"] == "gateway" else by + h + 3
            shape.append(f'        <bpmndi:BPMNLabel><dc:Bounds x="{lx}" '
                         f'y="{ly}" width="{lw}" height="{lh}"/>'
                         f'</bpmndi:BPMNLabel>')
        shape.append('      </bpmndi:BPMNShape>')
        x += shape
    pairs = set(flows)
    for fid, (s, t) in zip(fids, flows):
        x.append(f'      <bpmndi:BPMNEdge id="{fid}_di" '
                 f'bpmnElement="{fid}">')
        x += [f'        <di:waypoint x="{px}" y="{py}"/>'
              for px, py in route(byid[s], byid[t], nodes,
                                  (t, s) not in pairs)]
        x.append('      </bpmndi:BPMNEdge>')
    x += ['    </bpmndi:BPMNPlane>',
          '  </bpmndi:BPMNDiagram>',
          '</bpmn:definitions>', '']
    return "\n".join(x)


# --------------------------------------------------------- node styling
def node_classes(lanes, nodes):
    """Each node's semantic style class (added as a bpmn-js marker after
    import, so CSS can paint it). The two escalation tiers read as the LLM
    architect and the terminal operator — the live map's AIDE/OPERATOR
    palette — the engine's own landings stay neutral, the actor seats copper."""
    out = {}
    for n in nodes:
        lane = lanes[n["lane"]]
        if n["kind"] in ("start", "end"):
            c = "event"
        elif n["kind"] == "gateway":
            c = "gate"
        elif lane == "engine":
            c = "engine"
        elif lane in workflow.ESC_TIERS:
            c = lane                      # architect / operator
        else:
            c = "seat"                    # a workflow actor's task
        out[n["id"]] = c
    return out


def notes(flow, nodes):
    """The click-through annotations, one per node that carries prose. Phase
    notes are the `note=` field authored in workflow.toml; the escalation
    notes derive from the same ESCALATION table the engine routes from, so
    the panel cannot drift from the flow either."""
    byid = {ph["id"]: ph for ph in flow["phase"]}
    lim = workflow.limits(flow)
    judges = "; ".join(dict.fromkeys(t["judge"] for t in workflow.ESC_TRIGGERS))
    esc = {
        "esc_start": ("STUCK", "A stuck seat raises the exception spine — a "
                      "QUESTION, an engine wall, or an unparsable close."),
        "esc_arch": ("ARCHITECT", "Architect-first — the architect (an LLM) "
                     "reads every stuck signal before anyone is paged: "
                     + judges + "."),
        "esc_gw": ("ROUTE", "A ruling returns to the seat; an ESCALATE, a "
                   "recurrence of an already-ruled wall, or the ablated "
                   "architect_first arm sends the signal up to the operator."),
        "esc_op": ("OPERATOR", "The operator is the last resort and answers "
                   "from anywhere via Telegram; the answer syncs back down "
                   "through the " + workflow.ESC_SYNC + "."),
        "esc_ruling": ("RULING", "The ruling is relayed back to the stuck "
                       "seat, which resumes."),
    }
    out = []
    for n in nodes:
        nid, badge, text = n["id"], None, None
        if nid.startswith("task_"):
            ph = byid.get(nid[len("task_"):])
            if ph and ph.get("note"):
                badge, text = ph["id"].upper(), ph["note"]
        elif nid.startswith("gw_"):
            ph = byid.get(nid[len("gw_"):])
            if ph and ph["kind"] == "work":
                gate = ph["gate"] + (" + AC challenge" if ph.get("challenge")
                                     else "")
                badge, text = "GATE", (
                    f"The seat closes on >>{ph['word']}; the engine gate "
                    f"verifies {gate} — a bounce (capped at {lim['gate_fails']}, "
                    f"then the operator) sends it back, never forward.")
            elif ph:
                badge, text = "GATE", (
                    f">>{ph['pass_word']} advances; >>{ph['reject_word']} "
                    f"routes the findings back via the fix prompt (capped at "
                    f"{lim['review_cycles']}). Every verdict is recorded in "
                    f"reviews.md.")
        elif nid.startswith("land_"):
            badge, text = "LAND", ("Engine mechanical land: fast-forward the "
                                   "ref, then re-run the full suite ON the "
                                   "trunk — the claim is never trusted, the "
                                   "engine re-derives green itself.")
        elif nid == "end":
            badge, text = "DONE", (
                f"The register is stamped done — landed, trunk-green, and "
                f"wrapped. Caps per phase: {lim['gate_fails']} gate bounces, "
                f"{lim['review_cycles']} review rejects, {lim['phase_turns']} "
                f"turns — each ends at the operator.")
        elif nid in esc:
            badge, text = esc[nid]
        if text:
            out.append({"id": nid, "badge": badge,
                        "name": n["name"].replace("\n", " · "), "text": text})
    return out


# ---------------------------------------------------------------- HTML
def render_html(flow=None):
    flow = flow or workflow.parse_file()
    xml = render_bpmn(flow)
    lanes, nodes, _ = graph(flow)
    ncls = node_classes(lanes, nodes)
    cards = notes(flow, nodes)
    cards_html = "\n".join(
        f'    <article class="note-card" id="note--{c["id"]}">\n'
        f'      <header><span class="ncname">{escape(c["name"])}</span>'
        f'</header>\n'
        f'      <p>{escape(c["text"])}</p>\n'
        f'    </article>' for c in cards)
    tpl = """<!DOCTYPE html>
<!-- GENERATED from workflow.toml by bpmn.py - do not edit;
     regenerate: python3 bpmn.py -(-)write. NOT published until 0.4.2.
     Skin: the live 42labs tron-app workflow diagram (same vendored bpmn-js
     viewer + design tokens + logomark), baked in so --write is stable. -->
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TRON | Workflow</title>
<link rel="icon" href="__FAVICON__">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=IBM+Plex+Sans:wght@400;500;600&family=Geist+Mono:wght@400;500&display=swap" rel="stylesheet">
<script src="__VENDOR__"></script>
<style>
  :root{
    --canvas-warm:#FDFAF5; --cream:#FEF3E2; --border-cool:#E7E5E4;
    --mid-stone:#B8AFA8; --stone:#756D68; --graphite:#433E3A; --charcoal:#1C1917;
    --copper:#E2711D; --copper-dark:#CC5D0A; --copper-soft:#FDECD8;
    --copper-border:#F5C9A1; --copper-deep:#AA4D08;
    --blue-dark:#2563EB; --sky:#EFF6FF;
    --emerald:#16A34A; --emerald-dark:#166534;
    --accent:var(--copper); --logo:var(--copper-dark);
    --font-heading:'Space Grotesk',system-ui,sans-serif;
    --font-body:'IBM Plex Sans',system-ui,sans-serif;
    --font-mono:'Geist Mono',ui-monospace,monospace;
    --r-4:10px; --r-full:999px; --head-h:62px;
  }
  *{box-sizing:border-box}
  html,body{height:100%;}
  body{margin:0; background:var(--cream); color:var(--charcoal);
    font-family:var(--font-body); display:flex; flex-direction:column; overflow:hidden;}
  .topbar{flex:0 0 var(--head-h); height:var(--head-h); background:var(--canvas-warm);
    border-bottom:1px solid var(--border-cool); display:flex; align-items:center; z-index:20;}
  .topbar__inner{width:100%; margin-inline:auto; padding-inline:clamp(16px,4vw,40px);
    display:flex; align-items:center; justify-content:space-between; gap:24px;}
  .flowhead{display:flex; align-items:center; gap:10px;}
  .flowhead .nname{font-family:var(--font-heading); font-weight:600; font-size:15px;
    color:var(--charcoal); text-transform:uppercase; letter-spacing:.02em;}
  .logolink{display:inline-flex; align-items:center;}
  .logo__svg{height:26px; width:auto; display:block;}
  .logo__mark{fill:var(--accent);} .logo__type{fill:var(--logo);}
  .hsep{width:1px; height:18px; background:var(--border-cool);}
  .topctl{display:flex; align-items:center; gap:8px;}
  .zoomctl{display:flex; gap:6px;}
  .zoomctl button{width:32px; height:32px; border:1px solid var(--border-cool);
    background:#fff; border-radius:8px; font-size:18px; line-height:1; color:var(--graphite);
    cursor:pointer; font-family:var(--font-body); box-shadow:0 1px 3px rgba(28,25,23,.08);}
  .zoomctl button:hover{background:var(--cream); border-color:var(--copper-border);}
  .annotbtn{height:32px; padding:0 14px; border:1px solid var(--copper-border);
    background:var(--copper-soft); color:var(--copper-deep); border-radius:8px;
    font-family:var(--font-body); font-size:12px; font-weight:600; cursor:pointer;
    text-transform:uppercase; letter-spacing:.03em; box-shadow:0 1px 3px rgba(28,25,23,.08);}
  .annotbtn:hover{background:var(--copper-deep); color:#fff; border-color:var(--copper-deep);}
  #canvas{flex:1; min-height:0; background:var(--cream); cursor:grab;}
  #canvas:active{cursor:grabbing;}
  /* node/gateway/event text renders as authored (sentence case); a terminal
     command like ">tron start" must stay lowercase. Lane owner names are
     uppercased in the data, not here. */
  /* Do NOT style .bjs-powered-by — the bpmn-js licence requires the
     watermark stay fully visible and unaltered. Left exactly as rendered. */
  /* chart area (pool + every lane) = warm canvas against the cream page */
  .djs-element[data-element-id="pool"] .djs-visual > rect,
  .djs-element[data-element-id^="lane_"] .djs-visual > rect{ fill:var(--canvas-warm) !important; }
  /* semantic node fills (marker classes added after import) */
  .djs-element.n-seat .djs-visual > rect{ fill:var(--copper-soft) !important; stroke:var(--copper) !important; }
  .djs-element.n-engine .djs-visual > rect{ fill:#fff !important; stroke:var(--graphite) !important; }
  .djs-element.n-architect .djs-visual > rect{ fill:var(--emerald) !important; stroke:var(--emerald-dark) !important; }
  .djs-element.n-architect .djs-visual > text{ fill:#fff !important; }
  .djs-element.n-operator .djs-visual > rect{ fill:var(--sky) !important; stroke:var(--blue-dark) !important; }
  .djs-element.n-operator .djs-visual > text{ fill:var(--blue-dark) !important; }
  .djs-element.has-note{ cursor:pointer; }
  /* annotations — sliding right panel, self-contained (notes baked in) */
  .notes-panel{position:fixed; top:0; right:0; width:440px; max-width:92vw; height:100vh; z-index:60;
    background:#fff; border-left:1px solid var(--border-cool); box-shadow:-8px 0 24px rgba(28,25,23,.10);
    transform:translateX(100%); transition:transform .28s ease; display:flex; flex-direction:column;}
  .notes-panel.open{transform:translateX(0);}
  .notes-hd{flex:0 0 auto; display:flex; align-items:center; justify-content:space-between;
    padding:16px 18px; border-bottom:1px solid var(--border-cool);
    font-family:var(--font-heading); font-weight:600; text-transform:uppercase; letter-spacing:.04em;}
  .notes-close{width:30px; height:30px; border:1px solid var(--border-cool); background:#fff;
    border-radius:8px; font-size:17px; line-height:1; color:var(--stone); cursor:pointer;}
  .notes-close:hover{background:var(--cream); border-color:var(--copper-border);}
  .notes-body{flex:1; min-height:0; overflow-y:auto; padding:14px 18px;}
  .note-card{padding:12px 0; border-bottom:1px solid var(--border-cool);}
  .note-card__hd, .note-card header{display:flex; align-items:center; gap:8px; margin-bottom:6px;}
  .nnum{font-family:var(--font-mono); font-size:12px; font-weight:500; color:var(--copper-dark);
    background:var(--copper-soft); border:1px solid var(--copper-border); border-radius:var(--r-full);
    padding:2px 9px; white-space:nowrap;}
  .ncname{font-family:var(--font-heading); font-weight:600; font-size:13px; color:var(--charcoal);
    text-transform:uppercase; letter-spacing:.01em;}
  .note-card p{margin:0; font-size:13.5px; line-height:1.5; color:var(--graphite);}
  .note-card.hl{background:var(--copper-soft); margin-inline:-18px; padding-inline:18px; border-radius:var(--r-4);}
</style>
</head>
<body>
<header class="topbar"><div class="topbar__inner">
  <div class="flowhead">
    <a class="logolink" href="https://tron.42labs.io" target="_self" aria-label="TRON — 42labs home">__LOGO__</a>
  </div>
  <div class="topctl">
    <div class="zoomctl">
      <button id="zin" aria-label="zoom in">+</button>
      <button id="zout" aria-label="zoom out">&minus;</button>
      <button id="zfit" aria-label="fit">&#x2922;</button>
    </div>
    <button class="annotbtn" onclick="toggleNotes()">annotations</button>
  </div>
</div></header>
<div id="canvas"></div>
<aside class="notes-panel" id="notes" aria-label="annotations">
  <header class="notes-hd"><span>Annotations</span>
    <button class="notes-close" onclick="toggleNotes(false)" aria-label="close annotations">&times;</button></header>
  <div class="notes-body">
__CARDS__
  </div>
</aside>
<script type="text/xml" id="bpmn-xml">
__XML__</script>
<script>
  const NODE_CLASS = __NODECLASS__;
  const NOTE_IDS = new Set(Object.keys(NODE_CLASS).filter(
    id => document.getElementById("note--" + id)));
  const MIN_Z = 0.2, MAX_Z = 4;
  const viewer = new BpmnJS({ container: "#canvas" });
  const canvas = () => viewer.get("canvas");
  const clamp = z => Math.max(MIN_Z, Math.min(MAX_Z, z));
  // fit the whole flow, centred, with breathing room so the pool never
  // touches the header or the page edges (mirrors the live page's fitNow)
  function fit() {
    const c = canvas();
    c.zoom("fit-viewport", "auto");
    c.zoom(clamp(c.zoom() * 0.9));
  }
  function zoomBy(f) { const c = canvas(); c.zoom(clamp(c.zoom() * f)); }
  // the vendored viewer omits zoomScroll/moveCanvas — wire pan + wheel-zoom
  // by hand so the controls and the canvas actually move
  function wirePanZoom() {
    const el = document.getElementById("canvas");
    el.addEventListener("wheel", e => {
      e.preventDefault();
      const c = canvas(), vb = c.viewbox(), r = el.getBoundingClientRect();
      const p = { x: vb.x + (e.clientX - r.left) / vb.scale,
                  y: vb.y + (e.clientY - r.top) / vb.scale };
      c.zoom(clamp(vb.scale * (e.deltaY < 0 ? 1.1 : 1 / 1.1)), p);
    }, { passive: false });
    let pan = null;
    el.addEventListener("mousedown", e => {
      pan = { x: e.clientX, y: e.clientY, m: 0 }; });
    window.addEventListener("mousemove", e => {
      if (!pan) return;
      pan.m += Math.abs(e.clientX - pan.x) + Math.abs(e.clientY - pan.y);
      canvas().scroll({ dx: e.clientX - pan.x, dy: e.clientY - pan.y });
      pan.x = e.clientX; pan.y = e.clientY;
      el.style.cursor = "grabbing";
    });
    window.addEventListener("mouseup", () => { pan = null; el.style.cursor = ""; });
  }
  viewer.importXML(document.getElementById("bpmn-xml").textContent).then(() => {
    const c = canvas();
    for (const [id, k] of Object.entries(NODE_CLASS)) c.addMarker(id, "n-" + k);
    NOTE_IDS.forEach(id => c.addMarker(id, "has-note"));
    viewer.get("eventBus").on("element.click", e => {
      if (NOTE_IDS.has(e.element.id)) focusNote(e.element.id);
    });
    wirePanZoom();
    fit();
  });
  document.getElementById("zin").onclick = () => zoomBy(1.2);
  document.getElementById("zout").onclick = () => zoomBy(1 / 1.2);
  document.getElementById("zfit").onclick = fit;
  window.addEventListener("resize", fit);
  function toggleNotes(force){
    const p = document.getElementById("notes");
    const open = force === undefined ? !p.classList.contains("open") : force;
    p.classList.toggle("open", open);
  }
  function focusNote(id){
    toggleNotes(true);
    document.querySelectorAll(".note-card.hl").forEach(c => c.classList.remove("hl"));
    const c = document.getElementById("note--" + id);
    if (c){ c.classList.add("hl"); c.scrollIntoView({block:"center", behavior:"smooth"}); }
  }
  document.addEventListener("keydown", e => { if (e.key === "Escape") toggleNotes(false); });
</script>
</body>
</html>
"""
    return (tpl.replace("__VENDOR__", VENDOR)
            .replace("__FAVICON__", FAVICON)
            .replace("__LOGO__", LOGO_SVG)
            .replace("__CARDS__", cards_html)
            .replace("__NODECLASS__", json.dumps(ncls))
            .replace("__XML__", xml))


def docs_in_sync():
    return (BPMN.exists() and BPMN.read_text() == render_bpmn()
            and HTML.exists() and HTML.read_text() == render_html())


# -------------------------------------------------------------- selftest
def selftest():
    import copy
    flow = workflow.parse_file()
    xml = render_bpmn(flow)
    html = render_html(flow)
    root = ET.fromstring(xml)
    proc = root.find("bpmn:process", NS)
    plane = root.find(".//bpmndi:BPMNPlane", NS)
    tags = {"task", "exclusiveGateway", "startEvent", "endEvent"}
    fnodes = [e for e in proc if e.tag.split("}")[1] in tags]
    sflows = proc.findall("bpmn:sequenceFlow", NS)
    ids = {e.get("id") for e in fnodes}
    shapes = {s.get("bpmnElement")
              for s in plane.findall("bpmndi:BPMNShape", NS)}
    edges = plane.findall("bpmndi:BPMNEdge", NS)

    def wired(e):        # spec-complete: bpmnlint needs incoming/outgoing
        i = e.findall("bpmn:incoming", NS)
        o = e.findall("bpmn:outgoing", NS)
        k = e.tag.split("}")[1]
        return ((bool(i) or k == "startEvent")
                and (bool(o) or k == "endEvent"))

    # a LEGAL re-model must diagram too: the audit variant from workflow.py
    variant = copy.deepcopy(flow)
    variant["phase"].insert(2, {
        "id": "audit", "kind": "verdict", "actor": "reviewer",
        "persona": "auditor", "assign": "review_assign",
        "pass_word": "APPROVED", "reject_word": "REJECTED",
        "fix": "fix", "on_reject": "build", "next": "merge"})
    variant["phase"][1]["next"] = "audit"
    vxml = render_bpmn(variant)

    ok = [
        docs_in_sync(),
        len(ids) == len(fnodes),                       # ids unique
        all(wired(e) for e in fnodes),
        # every phase renders one task + one marked gateway
        all(f"task_{ph['id']}" in ids and f"gw_{ph['id']}" in ids
            for ph in flow["phase"]),
        all(s.get("isMarkerVisible") == "true"
            for s in plane.findall("bpmndi:BPMNShape", NS)
            if s.get("bpmnElement", "").startswith("gw_")),
        # every flow resolves, is drawn, and has >= 2 waypoints
        all(f.get("sourceRef") in ids and f.get("targetRef") in ids
            for f in sflows),
        ids | {f.get("id") for f in sflows} | {"pool"}
        | {lane.get("id") for lane in root.findall(".//bpmn:lane", NS)}
        >= shapes | {e.get("bpmnElement") for e in edges},
        len(edges) == len(sflows),
        all(len(e.findall("di:waypoint", NS)) >= 2 for e in edges),
        # semantics: bounce self-loops, the reject route, both landings
        any(f.get("sourceRef") == "gw_build"
            and f.get("targetRef") == "task_build" for f in sflows),
        any(f.get("sourceRef") == "gw_review"
            and f.get("targetRef") == "task_build" for f in sflows),
        {"land_merge", "land_wrap", "start", "end"} <= ids,
        # the escalation overlay: the exception spine from workflow.ESCALATION
        {"esc_start", "esc_arch", "esc_gw", "esc_op", "esc_ruling"} <= ids,
        any(f.get("sourceRef") == "esc_gw"          # architect escalates up
            and f.get("targetRef") == "esc_op" for f in sflows),
        any(f.get("sourceRef") == "esc_op"          # operator answer syncs
            and f.get("targetRef") == "esc_arch" for f in sflows),
        any(f.get("sourceRef") == "esc_gw"          # ruling back to the seat
            and f.get("targetRef") == "esc_ruling" for f in sflows),
        # lanes: engine + each actor + the two escalation tiers, every node
        # inside exactly one lane
        len(root.findall(".//bpmn:lane", NS)) == 3 + len(workflow.ESC_TIERS),
        {lane.get("name") for lane in root.findall(".//bpmn:lane", NS)}
        >= {t.upper() for t in workflow.ESC_TIERS},
        sorted(r.text for lane in root.findall(".//bpmn:lane", NS)
               for r in lane.findall("bpmn:flowNodeRef", NS))
        == sorted(ids),
        # the variant diagrams by data alone
        "task_audit" in vxml and 'id="gw_audit"' in vxml
        and ET.fromstring(vxml) is not None,
        # html embeds the exact same XML + the vendored viewer
        xml in html,
        VENDOR in html,
        "GENERATED" in xml and "GENERATED" in html,
        (DIR / VENDOR).exists(),
        # the baked-in 42labs skin: design tokens, brand font, the logomark
        "--copper" in html and "--canvas-warm" in html,
        "Space Grotesk" in html,
        "logo__mark" in html,
        # semantic node fills, painted by marker classes after import
        "NODE_CLASS" in html and "n-architect" in html and "n-operator" in html
        and "n-seat" in html and "n-engine" in html,
        # every node's style class resolves to a known category
        set(node_classes(*graph(flow)[:2]).values())
        <= {"event", "gate", "engine", "seat"} | set(workflow.ESC_TIERS),
        # the annotations panel: every authored phase note surfaces verbatim
        all(escape(ph["note"]) in html
            for ph in flow["phase"] if ph.get("note")),
        # and the escalation notes, derived from the same ESCALATION table
        'id="note--esc_arch"' in html and 'id="note--esc_op"' in html,
        "has-note" in html and escape(workflow.ESC_SYNC) in html,
        # a noted node exists for every card, and cards are click-wired
        all(f'id="note--{c["id"]}"' in html
            for c in notes(flow, graph(flow)[1])),
        # bpmn.md §3 as an enforced invariant — every edge orthogonal, at the
        # minimal turns its class allows, and crossing no node it doesn't
        # connect; holds on the base flow AND a re-modelled variant, so it is
        # a general rule, not a fit to one topology
        routing_faults(*graph(flow)) == [],
        routing_faults(*graph(variant)) == [],
    ]
    print(f"selftest: {sum(ok)}/{len(ok)} pass")
    sys.exit(0 if all(ok) else 1)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    elif "--write" in sys.argv:
        DIR.mkdir(exist_ok=True)
        BPMN.write_text(render_bpmn())
        HTML.write_text(render_html())
        print(f"wrote {BPMN}\nwrote {HTML}")
    else:
        print("docs in sync" if docs_in_sync()
              else "STALE — run: python3 bpmn.py --write")
        sys.exit(0 if docs_in_sync() else 1)
