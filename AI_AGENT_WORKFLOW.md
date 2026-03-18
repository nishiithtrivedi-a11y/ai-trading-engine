# AI Agent Git Workflow

This repository uses explicit branch/commit conventions to keep Claude and Codex work traceable.

## Branch Naming

- Codex branches: `codex/<feature-name>`

Never develop directly on `main`.

## Commit Message Prefixes

- Codex commits: `codex: <message>`

Use clear, scoped commit messages.

## Pull Request Policy

1. Create feature branch from up-to-date `main`.
2. Keep PR focused on one coherent change.
3. Run relevant tests before pushing.
4. Open PR into `main`.
5. Merge only after review/checks pass.

## History Safety Rules

- Do not rewrite or force-push shared history unless explicitly approved.
- Do not amend/squash unrelated prior work.
- Preserve existing Codex commit lineage.

## Staging Safety

Before committing:

- Stage only relevant source/test/docs files.
- Exclude secrets and local artifacts:
  - `.env`, keys, credentials, tokens
  - caches (`.pytest_cache/`, `__pycache__/`)
  - generated output (`output/`)
  - editor/system files

If needed, make a small safe `.gitignore` update in the same PR.

## Recommended PR Checklist

- [ ] Branch prefix is correct (`codex/`)
- [ ] Commit prefix is correct (`codex:`)
- [ ] No secrets or local artifacts staged
- [ ] Tests run and summarized
- [ ] PR description includes scope, risk, and validation
