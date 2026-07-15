---
name: agentflow
description: Run and manage software-engineering tasks through the Agentflow deterministic workflow CLI. Use when the user asks to use Agentflow, initialize Agentflow in a repository, start an Agentflow run, or continue work through its planning, verification, approval, merge, or shipping gates.
---

# Agentflow

Use the Agentflow CLI as the workflow authority. Treat model output as a
proposal and CLI state and recorded evidence as fact.

## Start in a repository

1. Work from the target repository root.
2. Run `command -v agentflow` to confirm the CLI is installed. If it is absent,
   explain that installing this skill alone does not install the executable.
   Direct the user to run
   `npx --yes github:daveonthegit/agentflow install` outside an active workflow
   run.
3. Run `agentflow init`. It is safe to rerun and must preserve existing project
   instructions.
4. Follow the repository's `AGENTS.md` and keep its project-specific knowledge
   in that repository. Do not copy it into the Agentflow source repository.

## Start and inspect a run

Start directly from the user's task summary:

```bash
agentflow start "<task summary>"
```

Report the returned run ID, state, and worktree. Inspect persisted state in a
new process with:

```bash
agentflow status <run-id>
```

Run Evidence defaults to Agentflow Home outside the target repository. Use
`AGENTFLOW_HOME` or `--data-dir` only when the user, CI environment, or isolated
test requires an override.

The current kernel stops at `ready`; planner and builder adapters are not
implemented. Do not implement the task in the worktree while claiming
Agentflow performed that stage.

## Record approval

If and only if `agentflow status <run-id>` reports `awaiting_human` and the user
explicitly directs approval, record it with:

```bash
agentflow approve <run-id> --approved-by <human identity>
```

Do not translate ordinary conversational agreement into approval.

## Preserve gate integrity

- Never claim a plan, build, check, review, approval, merge, or deployment
  happened unless Agentflow recorded corresponding evidence.
- Never bypass a failed or unavailable gate by editing run evidence manually.
- Never let an agent's prose override command exit status or test results.
- Require explicit human approval before merge.
- Treat the current CLI as a tracer-bullet MVP. Do not imply that unimplemented
  planner, builder, reviewer, merge, or deployment adapters have executed.
