#!/usr/bin/env python3
"""Build the arXiv-style single-column PDF from PAPER.md.
Pipeline: preprocess (figures, split) -> pandoc MD->LaTeX fragments ->
unicode fixups -> assemble main.tex (arxiv.sty) -> tectonic."""
import re
import subprocess
from pathlib import Path

import cairosvg
HERE = Path(__file__).parent
SRC = HERE.parent / "PAPER.md"
text = SRC.read_text()

# vector figures: SVG -> PDF for \includegraphics
for _name in ("fig1-core", "fig2-gate"):
    cairosvg.svg2pdf(url=str(HERE / f"{_name}.svg"),
                     write_to=str(HERE / f"{_name}.pdf"))

TITLE = (r"Demoting the Master Control Program:\\[2pt] Deterministic, "
         r"Zero-Trust Orchestration of a Fleet of LLM Agents")
SHORTTITLE = "Demoting the Master Control Program"

# ---- 1. replace the two ```mermaid``` blocks + their caption paragraph ----
FIGS = ["fig1-core.pdf", "fig2-gate.pdf"]
WIDTHS = ["1.0", "0.82"]
_n = [0]
def figrepl(m):
    k = _n[0]; _n[0] += 1
    cap = re.sub(r"\s+", " ", m.group("cap")).strip()
    return (f"\n\n\\begin{{figure}}[t]\n\\centering\n"
            f"\\includegraphics[width={WIDTHS[k]}\\linewidth]{{{FIGS[k]}}}\n"
            f"\\caption{{{cap}}}\n\\end{{figure}}\n\n")
# mermaid fence, then blank, then *Figure N — ... .* caption paragraph
text = re.sub(
    r"```mermaid.*?```\s*\*Figure \d+ [—-] (?P<cap>.*?)\*",
    figrepl, text, flags=re.DOTALL)

# ---- 2. split title / abstract / body(+refs), drop draft-meta ----
abs = re.search(r"## Abstract\s*(.*?)\s*\n---\n", text, re.DOTALL).group(1)
intro = text.index("## 1. Introduction")
notes = text.index("## Notes for typesetting")
refs = text.index("**References**")
body = text[intro:notes].rstrip()
ref_txt = text[refs:]
ref_txt = re.sub(r"^\*\*References\*\*[^.]*titles\)\.\s*", "", ref_txt, flags=re.DOTALL)
body += "\n\n## References {-}\n\n" + ref_txt
# strip manual "N." / "N.M" numbers from headings — LaTeX numbers them instead
body = re.sub(r"(?m)^(#{2,3})\s+\d+(\.\d+)?\.?\s+", r"\1 ", body)

(HERE / "abstract.md").write_text(abs)
(HERE / "body.md").write_text(body)

# ---- 3. pandoc MD -> LaTeX fragments ----
def pandoc(src, extra=()):
    out = subprocess.run(
        ["pandoc", src, "-f", "markdown+raw_tex", "-t", "latex", *extra],
        cwd=HERE, capture_output=True, text=True, check=True)
    return out.stdout

abstract_tex = pandoc("abstract.md")
body_tex = pandoc("body.md", ["--top-level-division=section",
                              "--shift-heading-level-by=-1"])

# ---- 4. unicode -> LaTeX fixups (XeTeX-safe, font-independent) ----
UMAP = {
    "→": r"$\rightarrow$", "←": r"$\leftarrow$", "↔": r"$\leftrightarrow$",
    "≤": r"$\le$", "≥": r"$\ge$", "≈": r"$\approx$", "−": r"$-$",
    "×": r"$\times$", "·": r"$\cdot$", "…": r"\ldots{}", "≠": r"$\neq$",
    "∥": r"$\parallel$", "⊢": r"$\vdash$", "§": r"\S{}", "†": r"\dag{}",
    "’": "'", "‘": "'", "“": "``", "”": "''",
}
def fixups(s):
    for u, l in UMAP.items():
        s = s.replace(u, l)
    s = s.replace("Pass\\^{}k", "Pass\\textsuperscript{k}").replace(
        "Pass^k", "Pass\\textsuperscript{k}")
    return s
abstract_tex, body_tex = fixups(abstract_tex), fixups(body_tex)

# ---- 5. assemble main.tex ----
PRE = r"""\documentclass{article}
\usepackage{arxiv}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{longtable}
\usepackage{array}
\usepackage{calc}
\usepackage{amsmath,amssymb}
\usepackage{xcolor}
\usepackage[colorlinks=true,allcolors=blue!55!black]{hyperref}
\usepackage{url}
\providecommand{\tightlist}{\setlength{\itemsep}{0pt}\setlength{\parskip}{0pt}}
\providecommand{\real}[1]{#1}
\providecommand{\passthrough}[1]{#1}
\title{""" + TITLE + r"""}
\renewcommand{\shorttitle}{""" + SHORTTITLE + r"""}
\author{\^Anderson Q. \\ 42labs \\ \texttt{anderson@42labs.io}}
\date{}
\begin{document}
\maketitle
\begin{abstract}
""" + abstract_tex + r"""
\end{abstract}
\vspace{-0.5em}
\begin{center}\itshape ``I fight for the Users.'' --- TRON (1982)\end{center}

""" + body_tex + r"""
\end{document}
"""
(HERE / "main.tex").write_text(PRE)
print("wrote main.tex", len(PRE), "bytes")

# ---- 6. compile ----
subprocess.run(["tectonic", "-X", "compile", "main.tex", "--outdir", "."],
               cwd=HERE, check=True)
print("wrote main.pdf")
