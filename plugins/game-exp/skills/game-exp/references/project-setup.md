# game-exp complete project setup

## Completion contract

A repository is `PROJECT_READY` only when the trusted control plane is actually enforceable. Installing files is not enough.

Required state:

- `game-exp/ledger` exists;
- exactly one write-capable Deploy Key named `game-exp trusted writer` exists;
- Environment `game-exp-trusted-writer` exists and its deployment branch policy allows only `main`;
- Environment secret `GAME_EXP_WRITER_KEY` exists;
- the legacy repository-scoped `GAME_EXP_WRITER_KEY` secret does **not** exist;
- GitHub Immutable Releases are enabled;
- the seven 1.0 Rulesets match the verified production semantics:
  - `game-exp ledger immutable`;
  - `game-exp ledger writer`;
  - `game-exp experiment immutable`;
  - `game-exp experiment lifecycle`;
  - `game-exp immutable refs immutable`;
  - `game-exp immutable refs creation`;
  - `game-exp protected main`;
- repository Actions default `GITHUB_TOKEN` permission is read-only and Actions cannot approve pull requests;
- the Trusted Writer self-test succeeds;
- repo-level `game_exp_doctor` returns `PASS`.

Anything less is incomplete.

## Trust modes

1.0 makes the main-branch trust assumption explicit.

### single-principal

Use only when the repository has one effective write principal.

- `main` still requires pull-request flow;
- no independent approval is required;
- the writer secret remains available only through the main-only Environment.

### multi-principal

Use when more than one person or automation principal can write the repository, or when the owner is an organization.

- `main` requires at least one approving review;
- the last pusher cannot satisfy the final approval requirement;
- the writer secret remains available only through the main-only Environment.

`project-init --trust-mode auto` detects the mode from repository ownership and visible write principals. If the initializer cannot determine that safely, it must fail and require an explicit `single-principal` or `multi-principal` choice.

Changing trust mode is a repository-security decision, not a lifecycle decision.

## Why the Environment is mandatory

The private Deploy Key used by Trusted Writer must not be a repository-level Actions secret.

A repository secret is available to eligible workflows across the repository. That allows a write-capable collaborator to modify a workflow on another branch and attempt to consume the secret.

1.0 instead stores `GAME_EXP_WRITER_KEY` in the `game-exp-trusted-writer` Environment and restricts that Environment to `main`. Jobs that need the private key declare:

```yaml
environment: game-exp-trusted-writer
```

Unprivileged build/test/replay jobs do not receive the key.

During upgrade from pre-1.0, project-init:

1. creates or repairs the Environment;
2. restricts it to `main`;
3. rotates the Trusted Writer Deploy Key when needed;
4. writes the private key only to the Environment secret;
5. removes the legacy repository secret;
6. verifies the final secret scope.

Never log, return, attach, commit, or persist the private key.

## Ruleset model

1.0 separates rules that must never be bypassed from rules that the Trusted Writer must be able to cross.

### Never-bypass rules

DeployKey receives no bypass for:

- Ledger deletion;
- Ledger non-fast-forward update;
- experiment-branch non-fast-forward update;
- protected immutable-tag update/deletion/non-fast-forward;
- protected-main pull-request/deletion/non-fast-forward rules.

### Writer-bypass rules

The Trusted Writer Deploy Key may bypass only the narrow rules required to operate the protocol:

- Ledger creation/fast-forward update;
- canonical experiment branch creation/deletion;
- immutable experiment/Candidate/Rehearsal tag creation.

Doctor validates the required minimum Ruleset semantics, not only Ruleset names. Weakening a required rule or adding writer authority where it is forbidden makes Doctor fail. Stricter user protection—such as extra reviewers, CODEOWNERS, resolved-review requirements, signatures, or narrower merge methods—is preserved and remains valid.

## Local prerequisites

CLI and local stdio MCP setup require Python 3.11+, Git, `uv`, and GitHub CLI (`gh`). Authenticate `gh` before running setup with `gh auth login`.

## New-project sequence

### Preferred path for a brand-new prototype

When no repository exists yet, prefer local `game_exp_project_create` or CLI `project-create`.

The command:

1. takes a repository name plus `godot` or `h5`;
2. fetches the latest tagged companion starter (GPS for Godot, H5 Game Prototype Agent for H5);
3. creates an isolated local Git working tree on `main`;
4. installs game-exp workflows/runtime, including the managed `game-exp-pages.yml` static Pages deployment workflow, and a valid repository-root project policy;
5. creates and pushes a GitHub repository with the requested visibility; default visibility is public;
6. runs project-init, Trusted Writer self-test and final Doctor;
7. returns `PROJECT_READY` or an explicit blocker while preserving the created repository for repair/resume.

For H5, `probe` is the default starter for a new gameplay idea; `slice` uses the minimal DOM slice starter. For Godot, project-create uses the canonical GPS 2D starter plus a repository-root source-bundle policy. Runtime/playable evidence still comes from GPS.

Never overwrite an existing local directory or GitHub repository. New prototype repositories default to public so the normal free-plan Ruleset path is available. For an existing private repository, do not silently change visibility; report the protection/plan blocker and let the user decide. If setup stops after repository creation, resume with project-init instead of creating another repository.

### Existing/manual repository path

1. Create/initialize the source repository.
2. Ensure a valid `.game-exp/project-policy.json` exists.
   - locked Node/npm may be inferred from `package.json` plus `package-lock.json` / `npm-shrinkwrap.json`;
   - unknown project types require an explicit policy.
3. Install game-exp runtime/Skill/workflows with `bootstrap.py`.
4. Commit and push those files to `main`.
5. Run `game_exp_project_preflight` or CLI `project-preflight`.
6. Stop on any material plan/permission/source blocker.
7. Run `game_exp_project_init` through local stdio MCP, or CLI `project-init`, using a repository administrator principal.
8. The initializer resolves/validates trust mode, creates or repairs controls idempotently, runs the Trusted Writer self-test, then runs Doctor.
9. Declare `PROJECT_READY` only when the initializer returns `status=PASS` and `complete=true`.
10. Only then start first-experiment onboarding.

## Project policy gate

Repository trust setup and project build policy are separate, but both must be valid before Candidate/Rehearsal execution.

Project policy schema v2 remains the normal build policy:

- `node-npm` requires an exact `toolchain.node_version`;
- other adapters use argv-only install/test/build commands;
- an unknown clean repository type fails bootstrap instead of receiving a guessed Node policy.

Project policy schema v3 adds the protected evaluation command and Evaluation Evidence v1 contract.

## GitHub plan gate

If GitHub reports that required Rulesets are unavailable for the repository/account:

- return `BLOCKED_PLAN / RULESETS_PLAN_UNSUPPORTED`;
- do not create a degraded writer path;
- for a private existing repository, surface the material plan/visibility choices;
- never silently change an existing repository's visibility.

New repositories default to public. There is no "weak private Free" compatibility mode. game-exp requires enforceable repository protection for a protected Ledger.

## Admin identity boundary

Complete project setup is repository-administration work.

- `game_exp_project_preflight` is read-only.
- `game_exp_project_init` is allowed only through local stdio MCP.
- CLI `project-init` is also allowed locally.
- Shared/streamable HTTP MCP must reject complete project initialization.
- Generated private-key material lives only in a temporary local directory until it is written to the Environment secret, then is deleted.

## Provisioning order

Order matters:

1. preflight admin access, plan support, and committed game-exp workflow source;
2. initialize the orphan Ledger ref;
3. create/repair the main-only Trusted Writer Environment;
4. establish the single Trusted Writer Deploy Key and Environment secret;
5. remove any legacy repository-scoped writer secret;
6. enable Immutable Releases;
7. harden repository Actions defaults;
8. create/update the seven verified 1.0 Rulesets for the selected trust mode;
9. remove obsolete pre-1.0 split Rulesets;
10. run the Trusted Writer self-test;
11. run Doctor.

Ledger creation happens before its creation rule becomes active.

## Idempotency and repair

Rerunning project-init against a healthy repository must preserve working controls and return PASS.

Fail closed when:

- another write-capable Deploy Key exists;
- multiple Trusted Writer write Deploy Keys exist;
- the writer Environment is not main-only;
- the Environment secret is missing;
- the legacy repository secret still exists and cannot be removed;
- any required Ruleset falls below the verified minimum security semantics;
- repository administration permission is absent;
- plan support is insufficient;
- the Trusted Writer self-test fails;
- final Doctor is not PASS.

If the exact Trusted Writer key exists but only the secret is missing, rotate that key rather than pretending the secret is recoverable.

## Why self-test is required

Presence checks alone are insufficient. The self-test proves:

- Trusted Writer can advance the Ledger;
- same request + same payload replays idempotently;
- same request + different payload is rejected;
- stale Ledger head is rejected;
- lost-response recovery does not create a duplicate mutation;
- ordinary workflow authority cannot bypass Ledger protection.

A skipped self-test means the project remains `INCOMPLETE`.

## First experiment boundary

`PROJECT_READY` means only that the trusted control plane is operational. It does not create an experiment, approve a human gate, or imply Candidate quality.

Continue with `references/onboarding.md`.
