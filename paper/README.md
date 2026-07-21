# Paper build kit

Builds `PAPER.md` (repo root — the prose source of truth) into an arXiv-style
single-column PDF.

## Files
- `build.py` — Markdown → LaTeX (pandoc) → `main.pdf` (tectonic). Sets the
  title/author, substitutes the two Mermaid blocks in `PAPER.md` with the vector
  figures, converts unicode to XeTeX-safe LaTeX, and drops draft-only meta
  (provenance blurb, "Notes for typesetting").
- `mkfigs.py` — regenerates the two publication figures (`fig1-core.svg`,
  `fig2-gate.svg`) in the 42labs vector style.
- `arxiv.sty` — single-column preprint template (kourgeorge/arxiv-style).
- `fig1-core.svg`, `fig2-gate.svg` — committed figure sources.

## Toolchain
- Python 3 with `pip install cairosvg markdown pypdf`
- [`pandoc`](https://pandoc.org) ≥ 3 on `PATH`
- [`tectonic`](https://tectonic-typesetting.github.io) on `PATH` (self-fetches
  its LaTeX packages on first run)

## Build
```sh
python3 mkfigs.py     # only when the figures change
python3 build.py      # -> main.pdf
```

Prose is edited in `PAPER.md`; title/author/email live in `build.py`
(`TITLE`, `SHORTTITLE`, `\author{...}`). Build outputs (`main.*`, `body.md`,
`abstract.md`, `fig*.pdf`) are gitignored; `demoting-the-mcp.pdf` is the
last committed render.
