# Agent instructions

## Agent skills

### Issue tracker

GitHub Issues are the tracker for this repository. See `docs/agents/issue-tracker.md`.

### Triage labels

Use the repository's default five-role vocabulary. See `docs/agents/triage-labels.md`.

### Domain docs

This is a single-context repository: use root `CONTEXT.md` and `docs/adr/`. See `docs/agents/domain.md`.

<!-- agentflow:start -->
## Agentflow

When the user explicitly asks to use Agentflow, follow the project-local
`agentflow` skill. Do not bypass its verification or human-approval gates.
<!-- agentflow:end -->
