# Release verification

Status: candidate validation in progress; no new public MarketDeepAgent image or remote release run is certified yet.

Verified locally:

- Native GPU BGE inference on GTX1660Ti, pinned torch2.6cu124/SAT5.1.2 and1024-dimensional output.
- Original100-case source baseline and145-answer/290-judgment baseline completed, with failures retained.
- CPU/GPU worker measurements and numerical vector agreement recorded in PERFORMANCE.md.
- Earlier CPU candidate passed actual health/readiness, UI/API, catalog100, BGE search, signup/session/CSRF, cart/quote, confirmed COD/idempotence, stock and persistence smoke checks.

The latest candidate and final remote CI/publication/pull checks must be recorded here with exact commit, run URL, tag and digest before this release is called complete. Earlier image pilots and source baselines do not substitute for the final tested image.
