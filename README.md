# game-exp

`game-exp` is the canonical standalone source repository for the trusted game experiment control plane.

Repository: `https://github.com/siskosun/game-exp`

This repository is the only development source of truth. `toy2game`, `game-exp-sandbox`, and locally installed Harness copies are consumers/snapshots, not mirrors that must be updated on every change.

## Install or upgrade

Clone this repository and run the bundled installer. The same installer is used for upgrades.

```powershell
git clone https://github.com/siskosun/game-exp.git
cd game-exp
python tools/game-exp/install_harnesses.py --json
```

The migrated 0.17.0 baseline preserves the existing shared-runtime installer. Harness-isolated upgrades are the first post-migration optimization.

## Source layout

- `tools/game-exp/`: runtime, CLI, MCP server, domain core, tests.
- `plugins/game-exp/`: portable Skill/plugin package.
- `.github/workflows/game-exp-*.yml`: trusted workflows copied into target projects by bootstrap.
- `.agents/plugins/marketplace.json`: local plugin marketplace descriptor.

## Development rule

Develop and release from this repository only. Do not automatically synchronize changes back to application repositories or installed Harness runtimes. A target repository or Harness upgrades only when explicitly requested.

Before merging a release change, run core tests, MCP tests, and the standing Conformance suite. Human gates, protected Ledger authority, and Trusted Writer boundaries remain unchanged.

Current migrated baseline: `0.17.0`.
