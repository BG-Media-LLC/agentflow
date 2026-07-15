# Store Run Evidence outside repositories

Agentflow stores mutable Run Evidence and temporary Workspaces in Agentflow
Home rather than the Agentflow repository or a Target Repository. This prevents
workflow state from polluting project history and gives concurrent Runs isolated
storage, while requiring explicit backup, cleanup, and portability policies.
