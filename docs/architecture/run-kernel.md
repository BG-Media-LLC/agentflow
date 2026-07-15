# Deterministic run kernel

The run kernel is the first real Agentflow vertical slice. It captures a task
and exact repository revision, creates an isolated Workspace, records ordered
Run Evidence, and reconstructs Run State in a later process. It does not invoke
models or claim that planning, building, checking, reviewing, merging, or
shipping occurred.

## Public commands

```bash
agentflow init
agentflow start "<task summary>"
agentflow run <task.json>
agentflow status <run-id>
agentflow approve <run-id> --approved-by <human identity>
```

- `init` installs the canonical project-local Agentflow skill and a managed
  `AGENTS.md` block without replacing existing project instructions.
- `start` captures a Task Spec, resolves the Target Repository and base commit,
  creates one branch and Workspace, records events, and returns `ready`.
- `run` imports a JSON Task Spec into the same kernel for compatibility.
- `status` replays events in sequence and combines the result with captured
  input metadata.
- `approve` appends an explicit approval only when replayed state is
  `awaiting_human`. Conversation text is not approval evidence.

## Agentflow Home

Run Evidence and Workspaces live outside both Agentflow and the Target
Repository. Resolution order is:

1. `--data-dir`
2. `AGENTFLOW_HOME`
3. Platform application-data location

The macOS default is `~/Library/Application Support/Agentflow`. CI and tests use
an override so they cannot contaminate a developer's real runs.

```text
<Agentflow Home>/
├── runs/
│   └── <run-id>/
│       ├── task.json
│       ├── repository.json
│       └── events.jsonl
└── worktrees/
    └── <run-id>/
```

## Event contract

New events contain a one-based `sequence` equal to their line number in
`events.jsonl`. State is projected from event type:

| Event | Resulting state |
| --- | --- |
| `run_created` | `created` |
| `workspace_ready` | `ready` |
| `plan_ready` | `planned` |
| `checks_passed` | `verified` |
| `awaiting_human` | `awaiting_human` |
| `human_approved` | `human_approved` |

`repository_snapshotted` adds evidence without changing state. Legacy events
without sequence numbers remain readable, but any sequence number that is
present must match its line position.

## Module map

- `src/agentflow/__main__.py` — thin CLI adapter.
- `src/agentflow/run_kernel.py` — Run lifecycle interface and implementation.
- `src/agentflow/paths.py` — Agentflow Home resolution.
- `src/agentflow/project_setup.py` — idempotent Target Repository setup.
- `skills/agentflow/` — canonical distributable skill.
- `.agents/skills/agentflow/` — Agentflow's own project-local copy.

## Kernel invariants

- A Run captures one Task Spec and one exact base commit.
- Each Run receives a unique branch and Workspace.
- Run State comes from event replay, not an independently edited status file.
- Approval requires an explicit command, identity, and valid prior state.
- No agent report can override command exit status or recorded evidence.
- Target Repository documentation never becomes Agentflow documentation.

## Known limitations

- No Repository Profile or repository mapper exists yet.
- No planner, builder, tester, reviewer, or merger Agent Adapter exists.
- No command currently advances `ready` into a planning stage.
- Worktree cleanup and abandoned-run recovery are not implemented.
- Approval does not yet bind an Approved Revision because build and review
  stages do not yet produce a candidate revision.
