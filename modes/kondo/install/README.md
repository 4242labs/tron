# TRON-KONDO install

```zsh
modes/install.sh              # /tron-kondo in every project + the terminal shortcut
modes/install.sh <project>    # scope the command to one project
modes/install.sh --no-path    # skip the shell-rc PATH line
```

That is the whole install, fresh machine included. `install.sh` writes the slash command with KONDO's
absolute path baked in, and adds one PATH line to your shell rc for the `tron-kondo` shortcut.
**No pointer files, no environment variables, no other machine state.**

`tron-kondo` opens the REPL already booted as KONDO; `tron-kondo "tidy acme"` passes the task straight
through.

Run it from the project you want tidied, or from anywhere and tell KONDO where the project lives. It
needs no hooks and no project-side install.
