# TRON-SCAFFOLD install

```zsh
modes/install.sh              # /tron-scaffold in every project + the terminal shortcut
modes/install.sh ~/path/proj  # /tron-scaffold in one project only
modes/install.sh --no-path    # skip the shell-rc PATH line
```

That is the whole install, fresh machine included. `install.sh` writes the slash command with
SCAFFOLD's absolute path baked in, and adds one PATH line to your shell rc for the `tron-scaffold`
shortcut. **No pointer files, no environment variables, no other machine state.**

`tron-scaffold` opens the REPL already booted as SCAFFOLD; `tron-scaffold "new project: acme"`
passes the task straight through.

Run it from anywhere — SCAFFOLD asks where the new project's workspace goes. It needs no hooks and
no project-side install: the project it scaffolds doesn't exist yet.
