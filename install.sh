#!/bin/sh
# ============================================================================
# TRON installer
#
#   curl -fsSL https://tron.42labs.io/seed.sh | sh
#
# What it does (and nothing more):
#   1. Checks that python3 and git are present.
#   2. Clones 4242labs/tron into ~/.tron  (or updates it in place if re-run).
#   3. Symlinks the `tron` launcher into ~/.local/bin so you can run `tron`
#      from anywhere.
#   4. Tells you how to start — and how to fix PATH if ~/.local/bin isn't on it.
#
# It is idempotent: run it again any time to update to the latest TRON.
# It never edits your shell rc files and never uses sudo.
#
# Override any of these with environment variables:
#   TRON_HOME   where to clone        (default: ~/.tron)
#   TRON_BIN    where to symlink       (default: ~/.local/bin)
#   TRON_REPO   git URL to clone       (default: https://github.com/4242labs/tron.git)
#   TRON_REF    branch/tag to check out(default: the repo default branch)
#
#   e.g.  curl -fsSL https://tron.42labs.io/seed.sh | TRON_REF=v0.4.2 sh
#
# Source of truth: this file lives at the root of 4242labs/tron. The pretty
# URL above is a redirect to it — there is no second copy to drift.
# ============================================================================

set -eu

# ---- configuration (env-overridable) --------------------------------------
TRON_HOME="${TRON_HOME:-$HOME/.tron}"
TRON_BIN="${TRON_BIN:-$HOME/.local/bin}"
TRON_REPO="${TRON_REPO:-https://github.com/4242labs/tron.git}"
TRON_REF="${TRON_REF:-}"

# ---- pretty output (degrades to plain text when not a terminal) -----------
if [ -t 1 ]; then
  B="$(printf '\033[1m')"; DIM="$(printf '\033[2m')"
  GRN="$(printf '\033[32m')"; YLW="$(printf '\033[33m')"
  RED="$(printf '\033[31m')"; RST="$(printf '\033[0m')"
else
  B=''; DIM=''; GRN=''; YLW=''; RED=''; RST=''
fi
say()  { printf '%s\n' "$*"; }
step() { printf '%s→%s %s\n' "$GRN" "$RST" "$*"; }
warn() { printf '%s!%s %s\n' "$YLW" "$RST" "$*"; }
die()  { printf '%s✗ %s%s\n' "$RED" "$*" "$RST" >&2; exit 1; }

# ---- 1. preflight: hard dependencies --------------------------------------
have() { command -v "$1" >/dev/null 2>&1; }

have git     || die "git is required but not found. Install git and re-run."
have python3 || die "python3 is required but not found. Install Python 3 and re-run."

say ""
say "${B}TRON${RST} — deterministic orchestrator"
say "${DIM}$TRON_REPO${RST}"
say ""

# ---- 2. clone or update ~/.tron -------------------------------------------
if [ -d "$TRON_HOME/.git" ]; then
  step "Updating existing install at $TRON_HOME"
  git -C "$TRON_HOME" fetch --quiet origin
  if [ -n "$TRON_REF" ]; then
    git -C "$TRON_HOME" checkout --quiet "$TRON_REF"
    git -C "$TRON_HOME" pull --quiet --ff-only origin "$TRON_REF" 2>/dev/null || true
  else
    # fast-forward the checked-out branch to its upstream
    git -C "$TRON_HOME" pull --quiet --ff-only 2>/dev/null \
      || warn "Local changes in $TRON_HOME — left as-is, not updated."
  fi
elif [ -e "$TRON_HOME" ]; then
  die "$TRON_HOME exists but is not a TRON checkout. Move it aside or set TRON_HOME."
else
  step "Cloning into $TRON_HOME"
  git clone --quiet "$TRON_REPO" "$TRON_HOME"
  [ -n "$TRON_REF" ] && git -C "$TRON_HOME" checkout --quiet "$TRON_REF"
fi

[ -f "$TRON_HOME/tron" ] || die "Clone succeeded but the launcher is missing — repo layout changed?"
chmod +x "$TRON_HOME/tron" 2>/dev/null || true

# ---- 3. symlink the launcher onto PATH ------------------------------------
mkdir -p "$TRON_BIN"
ln -sf "$TRON_HOME/tron" "$TRON_BIN/tron"
step "Linked $TRON_BIN/tron → $TRON_HOME/tron"

VERSION="$(cat "$TRON_HOME/VERSION" 2>/dev/null || echo '?')"

# ---- 4. report + PATH guidance --------------------------------------------
say ""
say "${GRN}${B}✓ TRON $VERSION installed.${RST}"
say ""

# Is TRON_BIN already reachable? If not, tell the user exactly how to fix it
# (we do NOT edit their shell rc for them).
case ":${PATH}:" in
  *":${TRON_BIN}:"*)
    say "Get started:"
    say "  ${B}tron start${RST}          ${DIM}# run TRON on the current repo${RST}"
    say "  ${B}tron start <path>${RST}   ${DIM}# ...or point it at a project${RST}"
    ;;
  *)
    warn "$TRON_BIN is not on your PATH yet. Add it:"
    say ""
    say "  ${B}export PATH=\"$TRON_BIN:\$PATH\"${RST}"
    say ""
    say "  ${DIM}(append that line to ~/.bashrc or ~/.zshrc to make it stick)${RST}"
    say ""
    say "Then: ${B}tron start${RST}   —   or right now: ${B}$TRON_HOME/tron start${RST}"
    ;;
esac
say ""
