# Agentflow factory decision map

Unresolved implementation choices for the Agentflow factory. Resolved
decisions do not live here: confirmed behavior belongs in the
[product contract](../architecture/product-contract.md) and hard-to-reverse
trade-offs in [ADRs](../adr/). When a ticket below is answered, record the
outcome in the appropriate durable document and remove the ticket.

## 1. Locking mechanism for single-builder and atomic stage claims

- **Blocked by:** none.
- **Type:** implementation choice.
- **Question:** What mechanism enforces single-builder locking on a Workspace,
  atomic stage claims, and prevention of concurrent `advance` processes on the
  same Run — for example an OS-level file lock in the run directory, a claim
  event in `events.jsonl` with compare-and-append semantics, or a lease file
  with expiry?
- **Answer:** open.

## 2. Adapter self-provisioning approach

- **Blocked by:** none.
- **Type:** implementation choice.
- **Question:** When Agentflow encounters a provider without a working Agent
  Adapter, how should it build, test, and land one through its own workflow —
  a dedicated Run template with adapter-specific contract fixtures, a
  provider-capability probe followed by a generated adapter skeleton, or
  something else — while satisfying the adapter-first gate recorded in the
  product contract?
- **Answer:** open.

## 3. Worktree cleanup and abandoned-run recovery

- **Blocked by:** ticket 1 (recovery must distinguish an abandoned Run from
  one actively claimed by another process).
- **Type:** implementation choice.
- **Question:** How are Workspaces reclaimed and abandoned Runs recovered —
  age-based garbage collection of worktrees, an explicit `agentflow abandon`
  command that appends a terminal event, automatic recovery on next `advance`,
  or a combination?
- **Answer:** open.
