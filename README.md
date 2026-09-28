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

Before writing anything, a Harness may check its state:

```powershell
python tools/game-exp/install_harnesses.py --harness codex --check --json
```

The check reports `NOT_INSTALLED`, `CURRENT`, `UPGRADE_AVAILABLE`, or a version-comparison warning and does not modify files. Downgrades are blocked unless `--allow-downgrade` is explicitly supplied.

Legacy 0.17.x shared installs under `~/.agents/tools/game-exp` / `~/.agents/skills/game-exp` are detected but preserved during a single-Harness upgrade. After all three Harnesses have been explicitly migrated, the old shared copy can be removed with:

```powershell
python tools/game-exp/install_harnesses.py --harness all --cleanup-legacy-shared --json
```

The cleanup flag is intentionally invalid for a single-Harness install.

Each Harness now gets an independent runtime under `~/.game-exp/runtimes/<harness>`, an independent Skill copy, and only its own MCP configuration is changed. Upgrading one Harness does not rewrite the others.

## Verify the distribution

Before installing, releasing, or handing this repository to another Harness:

```powershell
python tools/game-exp/distribution_check.py --json
```

The check fails if version markers drift, the canonical GitHub source changes, the install contract stops being Harness-isolated, managed source files are missing, or a repository-bound Codex config leaks back into the standalone distribution.

## Source layout

- `tools/game-exp/`: runtime, CLI, MCP server, domain core, tests.
- `plugins/game-exp/`: portable Skill/plugin package.
- `.github/workflows/game-exp-*.yml`: trusted workflows copied into target projects by bootstrap.
- `.agents/plugins/marketplace.json`: local plugin marketplace descriptor.
- `INSTALL.json`: machine-readable install/upgrade contract.

## Development rule

Develop and release from this repository only. Do not automatically synchronize changes back to application repositories or installed Harness runtimes. A consumer upgrades only when explicitly requested.

Before merging a release change, run core tests, MCP tests, and the standing Conformance suite. Human gates, protected Ledger authority, and Trusted Writer boundaries remain unchanged.

Current version: `0.18.8`.
