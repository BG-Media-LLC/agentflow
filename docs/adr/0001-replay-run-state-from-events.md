# Replay Run State from append-only evidence

Agentflow derives Run State by replaying ordered events instead of maintaining a
separately mutable status record. This makes transitions auditable and lets a
fresh process reconstruct authority, at the cost of enforcing event ordering
and evolving event compatibility deliberately.
