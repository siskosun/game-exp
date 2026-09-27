# game-exp

`game-exp` is the canonical standalone source repository for the trusted game experiment control plane.

Repository: `https://github.com/siskosun/game-exp`

This repository is the only development source of truth. `toy2game`, `game-exp-sandbox`, target projects, and locally installed Harness copies are consumers/snapshots. They are not mirrors and are not updated on every game-exp change.

## Install or upgrade

Read `INSTALL.json`, identify the current Harness, and run only that Harness's install command. First install and upgrade use the same command.

```powershell
git clone https://github.com/siskosun/game-exp.git
cd game-exp
python tools/game-exp/install_harnesses.py --harness codex --json
```

Supported Harness values: `codex`, `qoder`, `cursor`. Use `--harness all` only when the user explicitly wants all three updated.

Each Harness now gets an independent runtime under `~/.game-exp/runtimes/<harness>`, an independent Skill copy, and only its own MCP configuration is changed. Upgrading one Harness does not rewrite the others.

## Source layout

- `tools/game-exp/`: runtime, CLI, MCP server, domain core, tests.
- `plugins/game-exp/`: portable Skill/plugin package.
- `.github/workflows/game-exp-*.yml`: trusted workflows copied into target projects by bootstrap.
- `.agents/plugins/marketplace.json`: local plugin marketplace descriptor.
- `INSTALL.json`: machine-readable install/upgrade contract.

## Development rule

Develop and release from this repository only. Do not automatically synchronize changes back to application repositories or installed Harness runtimes. A consumer upgrades only when explicitly requested.

Before merging a release change, run core tests, MCP tests, and the standing Conformance suite. Human gates, protected Ledger authority, and Trusted Writer boundaries remain unchanged.

Current version: `0.18.0`.
