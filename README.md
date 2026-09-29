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

Supported Harness values: `codex`, `qoder`, `cursor`. Python 3.11+ is required. Local CLI/project setup also requires GitHub CLI (`gh`) authenticated with `gh auth login`. Use `--harness all` only when the user explicitly wants all three updated.

Before writing anything, a Harness may check its state:

```powershell
python tools/game-exp/install_harnesses.py --harness codex --check --json
```

The check reports `NOT_INSTALLED`, `CURRENT`, `UPGRADE_AVAILABLE`, or a version-comparison warning and does not modify files. `CURRENT` now requires more than a matching version string: the managed-runtime digest, required runtime entrypoints, installed game-exp Skill metadata, and selected Harness MCP entry must match the current source. This also detects incomplete or drifted installs even when their semantic version matches. Downgrades are blocked unless `--allow-downgrade` is explicitly supplied.

Legacy 0.17.x shared installs under `~/.agents/tools/game-exp` / `~/.agents/skills/game-exp` are detected but preserved during a single-Harness upgrade. After all three Harnesses have been explicitly migrated, the old shared copy can be removed with:

```powershell
python tools/game-exp/install_harnesses.py --harness all --cleanup-legacy-shared --json
```

The cleanup flag is intentionally invalid for a single-Harness install.

Each Harness gets an independent runtime under `~/.game-exp/runtimes/<harness>`, an independent game-exp Skill copy, and only its own MCP configuration is changed. Upgrading one Harness does not rewrite the others.

The 1.2 install/upgrade command also synchronizes the **latest semantic-version tags** of two companion Skills into that same Harness:

- `godot-prototype-studio` from `https://github.com/siskosun/godot-prototype-studio`
- `h5-game-prototype-agent` from `https://github.com/siskosun/h5-game-prototype-agent`

The companion sync installs runtime Skill files only; it does not copy their tests, CI, audit/dev history, or application repositories. `--harness all` is still required to update all Harnesses. If a companion repository has no semantic-version tag or cannot be fetched, the install command reports an explicit failure instead of silently installing an unversioned snapshot. Harness installation is transactional across the managed game-exp runtime/Skill/config and both companion Skill targets: a failure restores the pre-install state instead of leaving a partially upgraded managed target.

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

v0.21 adds Evaluation Evidence v1: content-addressed Evaluation Profiles, trusted replay/check evidence against frozen Candidate bytes, tri-state human-comparison eligibility, and optional incumbent/challenger human A/B annotations. Automated screening remains evidence only and never changes lifecycle.

Current version: `1.2.1`.

After a completed implementation iteration, game-exp projects a unified Chinese delivery card from `work.release.delivery`: what changed, a verified immediate/local playable entry or retained artifact fallback, previous-version context, 1-3 playtest focus points, and natural-language next intents. In 1.2.1, public-repository handoff stores immutable executor-produced versions on `gh-pages` and deploys them through a managed GitHub Actions Pages workflow keyed by source SHA; the Board can recover an older verified shareable URL for the previous Candidate. The card is read-only; `保留这版` never means SELECTED, and Review/selection still use the existing human gates.

For a brand-new prototype with no existing repository, local CLI/stdio MCP can now use `project-create` to create the GitHub repository, seed the latest tagged Godot/H5 starter, install game-exp, push `main`, and run complete project initialization. New repositories default to public so GitHub Rulesets work on the intended free-plan path. Existing private repositories remain supported when their plan provides the required protection.

Release history: see `CHANGELOG.md`.


## 1.2.1 pre-merge gate

Before merging a release change, run:

```bash
python tools/game-exp/premerge.py --json
```

This runs the full unit suite with the pinned MCP SDK, distribution integrity checks, and Python compile validation.
