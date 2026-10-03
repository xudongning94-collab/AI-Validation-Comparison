# Repository Recovery Instructions

This file is the mandatory startup guide for automated agents and maintainers.

## Repository identity

- The Git repository root must be this `bid-compare-agent` directory.
- `PROJECT_STATE.json` is the machine-readable source of current phase, version, verification count, and next gate.
- `CURRENT_PROGRESS_HANDOFF.md` is the authoritative human-readable handoff.
- `HANDOFF_TO_CODEX.md` is historical context and must not override the two sources above.
- Codex thread IDs and chat history are navigation metadata only. They must never be used as the authoritative recovery source; recover from the repository checkpoint and handoff files.

## Mandatory startup sequence

1. Run `git rev-parse --show-toplevel` and stop if it does not resolve to this directory.
2. Read `PROJECT_STATE.json` and `CURRENT_PROGRESS_HANDOFF.md` before planning work.
3. Run `powershell -ExecutionPolicy Bypass -File scripts/restore_context.ps1`.
4. Inspect `git status --short --branch` before editing.
5. Never discard modified or untracked files during recovery.
6. Use `scripts/restore_context.ps1 -Verify` before claiming the recovered state is valid.

## State update rule

When phase, version, verification count, or the next gate changes, update `PROJECT_STATE.json` first and then update the handoff. Avoid copying dynamic state into other documents unless it is immutable release history.

## Git safety

- Recovery checkpoints use a `codex/` branch.
- Local and remote histories may differ. Fetch and inspect `origin/main`, create an integration branch from it, and cherry-pick the reviewed checkpoint.
- Never force-push `main` as part of recovery.
