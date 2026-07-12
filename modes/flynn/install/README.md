# TRON-FLYNN install kit

One-time, per machine. FLYNN ships as a mode inside `tron-app/modes/flynn` — clone `tron-app`
anywhere; nothing assumes a fixed location.

1. **Pointer** — the file every boot resolves the FLYNN root from:

   ```zsh
   echo "<tron-app>/modes/flynn" > ~/.claude/tron-flynn.path
   ```

2. **Slash command** — copy `tron-flynn-command.md` to `~/.claude/commands/tron-flynn.md`, and
   `/tron-flynn` becomes available in every project.

3. **Terminal shortcut** (optional) — in `~/.zshrc`:

   ```zsh
   tron-flynn() { claude "/tron-flynn $*"; }
   ```

   `tron-flynn` opens the REPL already booted as FLYNN; `tron-flynn "audit tron"` passes the task
   straight through. The sibling shortcut for the supervisor mode is `tron-clu() { claude "/tron-clu $*"; }`.

FLYNN needs no hooks, no run flags, and no project-side install — it reads and advises, and only
writes when the operator directs it to.
