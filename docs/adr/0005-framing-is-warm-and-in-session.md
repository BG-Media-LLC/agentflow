# Framing is a warm in-session phase, not a cold stage

Deciding what to build — clarifying intent, surfacing edge cases, producing
documentation, and decomposing work — is done by Framing: an interactive phase
that runs warm in the operator's main session, driven by an Agentflow-owned
skill. Agentflow owns Framing's output contract and records its result, but it
does not host the conversation as a cold workflow stage. Framing ends when the
human approves the resulting Work Graph, which is then content-hashed and
immutable for the Runs that consume it. A Run therefore begins at build,
against an already-approved Work Item; the previous cold `planner` stage is
removed.

## Why

Framing is inherently conversational: its value comes from relentless,
context-accumulating back-and-forth with a human until intent and edge cases
are pinned down. A cold stage is the opposite — a one-shot subprocess with a
serialized prompt, no channel back to the human, and no memory across turns.
Forcing planning into a cold stage produced the failure that dominated wasted
Runs: bad specs the builder then faithfully implemented. It was also the most
expensive stage to run, re-exploring the repository from zero every time.

Planning quality is the highest-leverage input to the whole workflow and the
thing a cold stage is worst at. Moving it to a warm session puts the
interactive strength where it belongs while keeping the mechanical half —
build, validate, ship — cold, parallelizable, and deterministic. The Work
Graph that Framing produces is the boundary object between the two halves and
the only safe source of what may run in parallel; a cold Run must never invent
its own parallelism.

## Trade-off

Agentflow no longer produces work end-to-end inside Runs; part of the workflow
lives in the interactive session it cannot fully replay. We accept this: the
durable, gate-critical evidence is the approved Work Graph and everything
downstream of it. Framing is recorded by its approved output, not by a
transcript of the conversation that produced it. This keeps Agentflow's
identity as the trustworthy gate — approval bound to exact, verified
revisions — rather than an expensive factory that thinks up the work itself.
