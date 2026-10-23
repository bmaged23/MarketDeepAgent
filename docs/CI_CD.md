# CI and tested image delivery

`checks.yml` runs pinned lightweight tests on Python3.12/3.13, frontend behavior, generated diagram freshness, dataset invariants and secret/runtime-file publication checks. It runs on pushes and pull requests without provider or registry credentials.

`evaluate-and-publish.yml` runs on trusted`main`code/dependency/evaluation/container changes and manual dispatch. It reuses offline CI, then:

1. Builds a Linuxamd64 CPU candidate with pinned dependencies and model revision, without publishing.
2. Starts its own disposable Qdrant/catalog and executes all100 agent scenarios **inside that image**.
3. Independently scores every coordinator/journey answer with two judge calls.
4. Enforces complete references/coverage, separate per-agent regression limits and critical state/ownership/idempotence checks.
5. Exports examples, agent/tool traces and feedback to LangSmith.
6. Runs real HTTP/model/order/persistence smoke checks in another disposable stack.
7. Verifies the image ID matches the successful gate, then publishes`cpu`,`latest`and`sha-<commit>`.
8. Pulls the published SHA tag and repeats container smoke checks.

No image publication happens when an earlier required step fails. The previous registry image remains available. This is image delivery, not deployment of a hosted marketplace.

All inputs are distributable seeded data and bundled model assets, so the release job uses a GitHub-hosted CPU runner rather than accessing a laptop's localhost/database. Local CUDA benchmarking and native GPU support are separately verified; the workflow does not claim a GPU runner.

Required repository secrets:

-`OLLAMA_API_KEY`: account access to the agent/judge models.
-`LANGSMITH_API_KEY`: experiment upload; endpoint is configured for the evaluated EU workspace.
-`DOCKERHUB_USERNAME`,`DOCKERHUB_TOKEN`: public image publication with read/write access; delete permission is unnecessary.

Raw cases, model outputs, tokens and credentials are not uploaded as public GitHub artifacts. Only aggregate summary/gate/publication evidence is retained. Model calls incur provider usage; token counts are recorded but monetary cost is not invented.

Documentation-only pushes avoid repeating live cloud evaluation and unchanged-image publication. Model/reference changes require an explicitly versioned dataset/baseline; do not silently loosen a gate or retry valid low scores to obtain a green release. See [evaluation policy](EVALUATION.md) and`evaluation/release-policy.json`.

Failed-but-completed evaluations are also exported to LangSmith when their files exist, so a quality failure does not hide its traces. The failed gate still prevents all publication steps. Cancellation is respected. Artifact counters and raw judge coverage/arithmetic are both checked.
