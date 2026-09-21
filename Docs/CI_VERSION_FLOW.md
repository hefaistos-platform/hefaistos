# Automatic Versioning Setup (GitHub Actions)

This repository is configured with three workflows:

- `.github/workflows/sharp-version.yml`
- `.github/workflows/release-tag.yml`
- `.github/workflows/version-changelog.yml`

## 1) Set repository defaults

1. In GitHub repository settings, set default branch to `main`.
2. Ensure `VERSION` exists in repo root (already added).

## 2) Allow Actions to write

In repository settings:

1. Go to `Settings -> Actions -> General`.
2. Under `Workflow permissions`, select `Read and write permissions`.
3. Save.

Without this, workflows cannot push `VERSION` commits or git tags.

## 3) Branch protection for release branch

If branch protection is enabled on `main`, allow the version workflow to push:

1. Go to `Settings -> Branches -> Branch protection rules`.
2. Edit rule for `main`.
3. Keep required checks as needed.
4. Enable bypass or push allowance for GitHub Actions bot.

Recommended: allow only workflow-based version commit pattern:

- commit message contains `[skip version bump]`
- author `github-actions[bot]`

## 4) How SHARP auto bump works

On each push to `main`:

1. Workflow inspects commits in `before..after`.
2. Calculates bump (`major|minor|patch`) from commit messages.
3. Increments root `VERSION`.
4. Computes SHARP artifact version as `VERSION-sharp.${GITHUB_RUN_NUMBER}`.
5. Commits updated `VERSION` back to the release branch with:
   - `chore(version): bump to X.Y.Z [skip version bump] [skip ci]`
6. Updates README platform badge (`hefaistos-version-badge`) to the same base version.
7. Generates `Versions/vX.Y.Z/changelog.md` for that change set.

The `[skip version bump]` marker prevents version workflow loops.

## 5) How to create stable release tag

Run workflow `Create Stable Release Tag` manually:

1. Open `Actions -> Create Stable Release Tag`.
2. Click `Run workflow`.
3. Optional: set `target_sha` (if empty, current release branch HEAD is used).
4. Workflow validates commit ancestry on the release branch (`main`).
5. Workflow creates and pushes annotated tag `vX.Y.Z`.

## 6) Commit message conventions (important)

Use conventional commit subjects for predictable bumps:

- `feat: add tenant report export` -> `MINOR`
- `fix: handle null owner in serializer` -> `PATCH`
- `refactor(core)!: drop legacy policy endpoint` -> `MAJOR`
- commit body with `BREAKING CHANGE:` -> `MAJOR`

If conventions are not followed, workflow defaults to `PATCH` unless breaking markers are present.

## 7) Version changelog generation (`Versions/`)

On each SHARP version bump:

1. Workflow `SHARP Version Bump` creates `Versions/vX.Y.Z/changelog.md`.
2. Sections are filled from commit subjects in that push range:
   - `Fixes`: commits starting with `fix:`
   - `Removals`: commits indicating deletion/removal or breaking `!`
   - `Changes`: all remaining commits
3. `Database Migrations` lists migration files changed in the same commit range (`backend/**/migrations/*.py`).

When a stable tag `v*` is pushed:

1. Workflow `Generate Version Changelog` runs.
2. It backfills changelog only when `Versions/vX.Y.Z/changelog.md` is missing.
3. Sections are filled from commit subjects between previous tag and current tag:
   - `Fixes`: commits starting with `fix:`
   - `Removals`: commits indicating deletion/removal or breaking `!`
   - `Changes`: all remaining commits
4. The file is committed to the release branch (`main`) by `github-actions[bot]` using skip markers.

## 8) Operational notes

- First release tag in this repo will be based on current root `VERSION`.
- If rerunning the same SHARP workflow run, `GITHUB_RUN_NUMBER` remains tied to that run.
- Stable tags are immutable. If wrong tag is created, create a new patch/minor bump and tag that next version.
