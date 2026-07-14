# TRON-ALFREDO install

```zsh
modes/install.sh              # /tron-alfredo in every project + the terminal shortcut
modes/install.sh ~/path/proj  # /tron-alfredo in one project only
modes/install.sh --no-path    # skip the shell-rc PATH line
```

That is the whole install, fresh machine included. `install.sh` writes the slash command with
ALFREDO's absolute path baked in, and adds one PATH line to your shell rc for the `tron-alfredo`
shortcut. **No pointer files, no environment variables, no other machine state.**

`tron-alfredo` opens the REPL already booted as ALFREDO; `tron-alfredo "the build is failing on
staging"` passes the task straight through.

ALFREDO needs no hooks, no run flags, and no project-side install. He keeps session logs under
`{meta}/logs/alfredo/` and nothing else — no project-local context file, no registry, no bootstrap.
