# Contributing / repo ops

Public repo, only the owner (`mkmlman`) has write access; everyone else can only
clone, fork, and open PRs.

**Branch ruleset — "protect main"** (Settings → Rules, or REST):
- `main` requires changes to come through a PR; branch deletion and force-push are blocked.
- Owner (admin role) bypasses everything; the GitHub Actions bot does **not** bypass —
  PR merges are used instead so no token is needed.

**Key gotchas learned:**
- `GITHUB_TOKEN` cannot push to a PR-protected branch on a personal repo, and it
  cannot be added to a ruleset bypass list. To archive digests automatically, the
  workflow pushes to a `digest-*` branch and `gh pr merge --squash` it — a PR merge
  satisfies the "changes via PR" rule, so no PAT is required.
- The `gh` CLI in workflows needs `env: GH_TOKEN: ${{ github.token }}`.
- "Allow GitHub Actions to create and approve pull requests" (Settings → Actions →
  General → Workflow permissions) is **off by default** for personal repos and must
  be enabled, or the bot's PR creation fails with
  `GitHub Actions is not permitted to create or approve pull requests`.
- The workflow commit step is gated with `if: github.event_name != 'push'` so the
  PR merge's own push-triggered run doesn't re-commit (prevents infinite loops).
- Wiki is disabled; Issues and forking remain enabled.
