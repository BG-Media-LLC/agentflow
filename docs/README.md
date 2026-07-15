# Agentflow documentation

This directory records Agentflow's generic workflow architecture and
development practices. Project-specific knowledge for a Target Repository must
remain in that repository.

## Read first

- [`../CONTEXT.md`](../CONTEXT.md) — canonical domain language.
- [`architecture/run-kernel.md`](architecture/run-kernel.md) — implemented
  deterministic kernel and evidence layout.
- [`development/dogfooding.md`](development/dogfooding.md) — self-hosting
  threshold and operating procedure.
- [`roadmap.md`](roadmap.md) — dependency-ordered path from the kernel to a
  complete engineering workflow.
- [`adr/`](adr/) — hard-to-reverse architectural decisions and their reasons.

## Documentation split

Agentflow owns only reusable workflow concepts, interfaces, evidence contracts,
and generic operating guidance. Each Target Repository owns its Repository
Profile, architecture, commands, glossary, decisions, and generated repository
map. Agentflow may retain references and integrity metadata for those documents,
but not copy their contents into this repository.
