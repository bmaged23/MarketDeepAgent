# Project instructions for coding assistants

Before working on MarketDeepAgent, read `description/READ_FIRST.md` and `description/CURRENT_STATUS.md`, then the relevant description pages and source files. `description/` is the user's local, Git-ignored project context for LLMs.

For every project addition, modification, rename, or removal, update the affected description pages and append a dated entry to `description/CHANGELOG.md` in the same task. Keep `description/FILE_MAP.md` current; refresh observed status only after verifying it. Record removed paths, replacements, behavioral effects, and validation results. Never copy secrets or customer personal data into descriptions.

Keep `/description/` excluded in `.gitignore`. If the folder is absent in a fresh clone, reconstruct its context from source and verified state without inventing historical entries.

Agent folders represent distinct roles. Each role keeps its own `agent.py`, `tools.py`, and `prompts/` folder. Current roles are retrieval, cart, and customer. Customer coordinates the retrieval and cart specialists. Shared application helpers belong in `app/utils/`; feature business logic remains in its own service.
