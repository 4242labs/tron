# TRON-FLYNN install

```zsh
modes/install.sh              # /tron-flynn in every project
modes/install.sh ~/path/proj  # /tron-flynn in one project only
```

That is the whole install. `install.sh` writes the slash command with FLYNN's absolute path baked
in — there are **no pointer files, no environment variables, and no machine-level state of ours**.
The command file itself is the only thing written, into Claude's own `commands/` directory.

Terminal shortcut (optional) — one line in your shell rc:

```zsh
export PATH="<tron-app>/modes/bin:$PATH"   # gives you: tron-flynn / tron-clu
```

`tron-flynn` opens the REPL already booted as FLYNN; `tron-flynn "audit tron"` passes the task
straight through.

FLYNN needs no hooks, no run flags, and no project-side install — it reads and advises, and writes
only when the operator directs it to.
