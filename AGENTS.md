# game-exp repository instructions

This repository is the canonical development and distribution source for game-exp.

When a user asks to install or upgrade game-exp from this repository:

1. Read `INSTALL.json` and `plugins/game-exp/skills/game-exp/SKILL.md`.
2. Detect which Harness you are currently operating in.
3. Install or upgrade only that Harness unless the user explicitly requests multiple Harnesses or `all`.
4. Do not modify `toy2game`, `game-exp-sandbox`, or any other consumer repository as part of a normal game-exp release.
5. Do not update other locally installed Harnesses as a side effect.
6. If a legacy shared `~/.agents` install is detected, preserve it during a single-Harness migration. Remove it only after an explicit `--harness all --cleanup-legacy-shared` request succeeds.
7. Use the same installer for first install and upgrade.
8. Keep repository binding dynamic; never hard-code a target project into the global MCP registration.
9. Preserve protected Ledger, Trusted Writer, human gates, and recovery semantics.

For development, branch from this repository's `main`, run the game-exp tests and Conformance suite, and merge changes here first. Consumer repositories pull a released version only when explicitly requested.
