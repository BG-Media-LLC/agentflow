# Agentflow product and architecture contract

This is the canonical contract for the Agentflow factory: the agreed behavior
Agentflow must exhibit, with every statement classified as either implemented
or target. Domain terms are defined in [`../../CONTEXT.md`](../../CONTEXT.md);
kernel mechanics, event contracts, and evidence layout are detailed in
[`run-kernel.md`](run-kernel.md); unresolved implementation choices live in
[`../decisions/agentflow-factory.md`](../decisions/agentflow-factory.md). This
document does not duplicate those sources.

## How to read this contract

Every behavior statement carries one of two classifications:

- **Implemented** — enforced by code in `src/` today and covered by the test
  suite. `run-kernel.md` describes the mechanism.
- **Target** — agreed direction that no code enforces yet. Target behavior
  must never be described as implemented; when a target item lands, its
  classification changes here and the mechanism is documented in the
  architecture docs.

## Run lifecycle

- **Implemented.** A Run captures one immutable Task Spec and one exact base
  commit, starts only from a clean Target Repository checkout, and proceeds
  through planner, builder, checks, and reviewer stages driven by replayed
  state. `advance` performs one stage per invocation.
- **Implemented.** Planner, builder, and reviewer outputs must satisfy strict
  versioned role contracts; the builder's authoritative Git diff must be a
  subset of planned paths and must equal its reported file list.
- **Implemented.** A fresh process can replay a Run's events and continue from
  the recorded state.
- **Target.** Explicit plan approval, a tester role, bounded builder-fix retry
  loops, a constrained Merge Agent, and Post-Merge Verification. Merge and
  deployment remain manual after approval until these exist.

## Evidence

- **Implemented.** Run Evidence is append-only, sequence-numbered, and stored
  in Agentflow Home, outside both the Agentflow repository and every Target
  Repository. Run State is projected from event replay, never from an
  independently mutable status file.
- **Implemented.** Authoritative checks execute outside model reasoning
  against the exact candidate SHA, must leave the Workspace clean, and their
  raw results become Run Evidence. No agent report can override command exit
  status or recorded evidence.
- **Target.** Evidence-driven improvement: Improvement Proposals generated
  from repeated Run Evidence, evaluated against fixtures, and gated by an
  Adoption Gate.

## Approval

- **Implemented.** The workflow records `awaiting_human` only after checks
  pass and review does not block. Approval requires an explicit command, a
  human identity, a clean Workspace, and the exact Candidate Revision SHA.
  Conversation text is never approval evidence.
- **Implemented.** Any code change after approval invalidates it; the new
  revision must pass verification and approval again.
- **Target.** Approval-scoped merge automation: a Merge Agent may act only on
  a current Approved Revision after deterministic policy gates.

## Repository Profile boundary

- **Implemented.** Each Target Repository owns its Repository Profile,
  architecture, commands, glossary, and repository map. A Run records the
  profile by path, hash, and source fingerprint, and refuses to advance when
  the profile is stale or fails its integrity check. Target Repository
  documentation never becomes Agentflow documentation.
- **Target.** Deeper profile discovery: inferring entry points, architecture,
  and repository-specific domain language rather than the current shallow map.

## Concurrency

- **Implemented.** Each Run receives a unique Git branch and Workspace at
  start. Concurrent Runs never share a checkout, and a Workspace is never the
  Target Repository's primary checkout.
- **Target.** Single-builder locking on a Workspace. Workflow sequencing
  invokes at most one builder stage per `advance`, but no lock prevents a
  second builder process from entering the same Workspace.
- **Target.** Atomic stage claims, so that exactly one process can claim and
  execute a given stage of a Run.
- **Target.** Prevention of concurrent `advance` processes on the same Run.
  Today two simultaneous `advance` invocations on one Run are not blocked;
  operators must avoid this manually. The locking mechanism is an open choice
  in the [decision map](../decisions/agentflow-factory.md).

## Agent Adapters

- **Confirmed decision.** A model provider without a working Agent Adapter
  must have one built, tested, and landed before Agentflow coordinates work
  through that provider. Coordinating work through an unadapted provider is
  not permitted as a workaround.
- **Implemented.** Claude and Codex adapters, plus a deterministic fake for
  tests. Their executables are overridable via the `AGENTFLOW_CLAUDE` and
  `AGENTFLOW_CODEX` environment variables. Changing an adapter must not change
  workflow state semantics, verification rules, or approval authority.
- **Implemented.** Planner and reviewer roles run read-only; the builder role
  is constrained by role instructions and the kernel's planned-path diff
  enforcement rather than an operating-system sandbox in the Claude adapter.
- **Target.** Automatic adapter self-provisioning: Agentflow detecting a
  missing adapter and building, testing, and landing one through its own
  workflow before use. Until this exists, adapters are built through
  documented Bootstrap Development. The provisioning approach is an open
  choice in the [decision map](../decisions/agentflow-factory.md).
