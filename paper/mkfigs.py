#!/usr/bin/env python3
"""First-version publication figures for PAPER.md, in the 42labs diagram style.
Fig 1 — the deterministic core (block through the flow).
Fig 2 — the gate as a linear challenge.
Self-contained SVGs: tokens/fonts/palette matching the workflow diagram."""
from pathlib import Path

OUT = Path(__file__).parent

# ---- 42labs palette ----
CANVAS = "#FDFAF5"; CREAM = "#FEF3E2"; BORDER = "#E7E5E4"
COPPER = "#E2711D"; COPPER_D = "#CC5D0A"; COPPER_L = "#FDECD8"
EMER = "#16A34A"; EMER_D = "#166534"
SKY = "#EFF6FF"; BLUE = "#2563EB"
GRAPH = "#433E3A"; MUTE = "#8A817B"
FONT = "'Space Grotesk','IBM Plex Sans',system-ui,sans-serif"
MONO = "'Geist Mono',ui-monospace,'SFMono-Regular',monospace"

STYLE_TYPES = {  # fill, stroke, text
    "engine":    ("#ffffff", GRAPH,   GRAPH),
    "seat":      (COPPER_L,  COPPER,  COPPER_D),
    "gate":      (CREAM,     GRAPH,   GRAPH),
    "architect": (EMER,      EMER_D,  "#ffffff"),
    "operator":  (SKY,       BLUE,    BLUE),
    "trunk":     ("#ffffff", GRAPH,   GRAPH),
}


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def label(cx, cy, lines, color, size=13.5, weight=600, mono=False):
    fam = MONO if mono else FONT
    n = len(lines)
    y0 = cy - (n - 1) * (size * 0.62)
    out = []
    for i, ln in enumerate(lines):
        out.append(
            f'<text x="{cx:.1f}" y="{y0 + i*size*1.24:.1f}" text-anchor="middle" '
            f'dominant-baseline="middle" font-family="{fam}" font-size="{size}" '
            f'font-weight="{weight}" fill="{color}">{esc(ln)}</text>')
    return "\n".join(out)


def rect(cx, cy, w, h, kind, lines, rx=13, size=13.5, mono=False):
    fill, stroke, tx = STYLE_TYPES[kind]
    x, y = cx - w / 2, cy - h / 2
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w}" height="{h}" rx="{rx}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="1.6"/>\n'
            + label(cx, cy, lines, tx, size=size, mono=mono))


def diamond(cx, cy, w, h, lines):
    fill, stroke, tx = STYLE_TYPES["gate"]
    pts = f"{cx},{cy-h/2} {cx+w/2},{cy} {cx},{cy+h/2} {cx-w/2},{cy}"
    return (f'<polygon points="{pts}" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="1.6"/>\n' + label(cx, cy, lines, tx, size=12.5))


def terminal(cx, cy, r, lines, kind="engine"):
    fill, stroke, tx = STYLE_TYPES[kind]
    return (f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="2.4"/>\n'
            f'<circle cx="{cx}" cy="{cy}" r="{r-4.5}" fill="none" stroke="{stroke}" '
            f'stroke-width="1"/>\n' + label(cx, cy, lines, tx, size=12.5, weight=700))


def cylinder(cx, cy, w, h, lines):
    fill, stroke, tx = STYLE_TYPES["trunk"]
    x, y = cx - w / 2, cy - h / 2
    ry = 7
    d = (f"M{x},{y+ry} A{w/2},{ry} 0 0 1 {x+w},{y+ry} L{x+w},{y+h-ry} "
         f"A{w/2},{ry} 0 0 1 {x},{y+h-ry} Z")
    top = f"M{x},{y+ry} A{w/2},{ry} 0 0 0 {x+w},{y+ry}"
    return (f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="1.6"/>\n'
            f'<path d="{top}" fill="none" stroke="{stroke}" stroke-width="1.6"/>\n'
            + label(cx, cy + 3, lines, tx, size=12.5))


def defs():
    def marker(mid, color):
        return (f'<marker id="{mid}" viewBox="0 0 10 10" refX="8.5" refY="5" '
                f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
                f'<path d="M0,1 L9,5 L0,9 z" fill="{color}"/></marker>')
    return ("<defs>"
            + marker("ar", GRAPH) + marker("ar-c", COPPER_D)
            + marker("ar-m", MUTE) + marker("ar-b", BLUE)
            + "</defs>")


def elabel(x, y, text, color=MUTE, size=11, mono=False, anchor="middle"):
    fam = MONO if mono else FONT
    # rounded backing so the label reads over the canvas, not the line
    w = len(text) * (size * 0.56) + 12
    return (f'<rect x="{x-w/2:.1f}" y="{y-size*0.8:.1f}" width="{w:.1f}" '
            f'height="{size*1.55:.1f}" rx="{size*0.75:.1f}" fill="{CANVAS}" '
            f'opacity="0.95"/>'
            f'<text x="{x}" y="{y}" text-anchor="{anchor}" dominant-baseline="middle" '
            f'font-family="{fam}" font-size="{size}" font-weight="500" '
            f'fill="{color}">{esc(text)}</text>')


def path(d, color=GRAPH, marker="ar", dash=None, w=1.7):
    da = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{w}"'
            f'{da} marker-end="url(#{marker})" stroke-linejoin="round" '
            f'stroke-linecap="round"/>')


def wrap(w, h, body, title, sub):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" font-family="{FONT}">
{defs()}
<rect x="0" y="0" width="{w}" height="{h}" fill="{CANVAS}"/>
<rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="16" fill="none" stroke="{BORDER}"/>
<text x="34" y="42" font-family="{FONT}" font-size="16" font-weight="700" fill="{GRAPH}">{esc(title)}</text>
<text x="34" y="62" font-family="{MONO}" font-size="11.5" font-weight="500" fill="{MUTE}">{esc(sub)}</text>
{body}
</svg>'''


# ============================================================ FIG 1
def fig1():
    W, H = 1470, 500
    yS = 250                      # spine row
    yB = 400                      # off-path row (architect/operator)
    h = 60
    # per-node half-width (edges dock at the true edge, whatever the shape)
    hw = {"disp": 69, "build": 69, "intp": 70, "rev": 69, "merge": 69,
          "wrap": 59, "land": 34}
    cx = {"disp": 116, "build": 372, "intp": 577, "rev": 824, "merge": 1042,
          "wrap": 1228, "land": 1373}
    ax, ox = 577, 824             # architect under interpret, operator under review
    b = []
    # ---- edges ----
    def hx(a, c):
        return f"M{cx[a]+hw[a]},{yS} H{cx[c]-hw[c]}"
    for a, c in [("disp", "build"), ("build", "intp"), ("intp", "rev"),
                 ("rev", "merge"), ("merge", "wrap"), ("wrap", "land")]:
        b.append(path(hx(a, c)))
    # interpret -> architect (down)
    b.append(path(f"M{ax},{yS+48} V{yB-h/2}"))
    # architect -> build (ruling relayed, dashed, up-left)
    b.append(path(f"M{ax-90},{yB} H{cx['build']} V{yS+h/2}",
                  color=COPPER_D, marker="ar-c", dash="6 5"))
    # architect <-> operator (two offset dashed edges)
    b.append(path(f"M{ax+90},{yB-10} H{ox-75}",
                  color=MUTE, marker="ar-m", dash="6 5"))          # last resort ->
    b.append(path(f"M{ox-75},{yB+10} H{ax+90}",
                  color=BLUE, marker="ar-b", dash="6 5"))          # answer back <-
    # ---- nodes ----
    b.append(rect(cx["disp"], yS, 138, h, "engine", ["dispatch loop", "reads git pipeline"], size=12.5))
    b.append(rect(cx["build"], yS, 138, h, "seat", ["build", "worker"]))
    b.append(diamond(cx["intp"], yS, 140, 96, ["closed-vocab", "interpret"]))
    b.append(rect(cx["rev"], yS, 138, h, "seat", ["review", "judge · isolated"], size=12.5))
    b.append(rect(cx["merge"], yS, 138, h, "seat", ["merge", "worker owns it"], size=12.5))
    b.append(rect(cx["wrap"], yS, 118, h, "seat", ["wrap"]))
    b.append(terminal(cx["land"], yS, 34, ["landed"], kind="engine"))
    b.append(rect(ax, yB, 180, h, "architect", ["architect", "rule · answer · escalate"], size=11))
    b.append(rect(ox, yB, 150, h, "operator", ["operator", "last resort"], size=12.5))
    # ---- edge labels (on top of everything) ----
    b.append(elabel((cx["disp"]+cx["build"])/2, yS-15, "block, deps met", mono=True))
    b.append(elabel((cx["intp"]+cx["rev"])/2, yS-15, "DONE + gate", mono=True))
    b.append(elabel((cx["rev"]+cx["merge"])/2, yS-15, "verdict", mono=True))
    b.append(elabel(ax+16, (yS+yB)/2, "unparseable / QUESTION", mono=True, anchor="start"))
    b.append(elabel((ax+90+ox-75)/2, yB-24, "last resort", color=MUTE))
    b.append(elabel((ax+90+ox-75)/2, yB+34, "answer travels back", color=BLUE))
    b.append(elabel(cx["build"]+2, yS+66, "ruling relayed", color=COPPER_D))
    body = "\n".join(b)
    return wrap(W, H, body,
                "Figure 1 — The deterministic core: a block through the flow",
                "the closed-vocabulary interpret is the only decision point; the architect sits off the steering path")


# ============================================================ FIG 2
def fig2():
    W, H = 1060, 610
    xM = 320                     # main spine column
    w, h = 252, 58
    yTop = 118
    step = 70
    ci = {k: yTop + i*step for i, k in
          enumerate(["C", "S1", "S2", "S3", "S4", "S5", "D"])}
    xT = 760                     # trunk column (right)
    xFail = 66                   # fail return rail (left)
    xP = 740                     # production (right, bottom)
    yTrunk = ci["S3"]
    order = ["C", "S1", "S2", "S3", "S4", "S5", "D"]
    b, labs = [], []
    # ---- spine edges ----
    for a, c in zip(order, order[1:]):
        end = ci[c] - (34 if c == "D" else h/2)
        b.append(path(f"M{xM},{ci[a]+h/2} V{end}"))
    # ---- fail return rail: S1,S2,S3,S5 -> C (left) ----
    for s in ["S1", "S2", "S3", "S5"]:
        b.append(path(f"M{xM-w/2},{ci[s]} H{xFail} V{ci['C']} H{xM-w/2}",
                      color=COPPER_D, marker="ar-c", dash="6 5", w=1.4))
    labs.append(elabel(xFail, (ci['C']+ci['S2'])/2, "fail → back to work",
                       color=COPPER_D))
    # ---- trunk evidence: trunk -> S1,S4,S5 (right, dashed) ----
    rail = xM + w/2 + 46
    for s in ["S1", "S4", "S5"]:
        b.append(path(f"M{xT-72},{yTrunk} H{rail} V{ci[s]} H{xM+w/2}",
                      color=MUTE, marker="ar-m", dash="4 5", w=1.3))
    labs.append(elabel((rail+xT-72)/2, yTrunk-60, "evidence", color=MUTE))
    # ---- DONE -> production ----
    b.append(path(f"M{xM+50},{ci['D']} H{xP-75}", color=GRAPH, w=2.2))
    labs.append(elabel((xM+50+xP-75)/2, ci['D']-15, "operator-gated, outside TRON",
                       color=GRAPH, size=10.5))
    # ---- nodes ----
    b.append(rect(xM, ci["C"], w, h, "seat", ["worker: DONE", "opens a candidate"], size=13))
    b.append(rect(xM, ci["S1"], w, h, "engine", ["1 · structural check", "branch + commits"], size=13))
    b.append(rect(xM, ci["S2"], w, h, "engine", ["2 · engine runs the tests", "in the worker's arena"], size=13))
    b.append(rect(xM, ci["S3"], w, h, "engine", ["3 · AC challenge", "CONFIRMED + evidence"], size=13))
    b.append(rect(xM, ci["S4"], w, h, "engine", ["4 · landing", "contains-trunk · ref-advance"], size=12.5))
    b.append(rect(xM, ci["S5"], w, h, "engine", ["5 · re-validate on trunk", "trunk-only test · clean teardown"], size=12))
    b.append(terminal(xM, ci["D"], 34, ["closed", "= done"], kind="architect"))
    b.append(cylinder(xT, yTrunk, 128, 74, ["trunk", "read-only"]))
    b.append(rect(xP, ci["D"], 150, 52, "operator", ["production"], size=13))
    body = "\n".join(b + labs)   # labels last, on top
    return wrap(W, H, body,
                "Figure 2 — The gate: a linear challenge",
                "trunk is evidence read into each stage, never the terminal")


(OUT / "fig1-core.svg").write_text(fig1())
(OUT / "fig2-gate.svg").write_text(fig2())
print("wrote fig1-core.svg, fig2-gate.svg")
