# Verified release — 23 October 2026

The candidate passed the complete pipeline and was published publicly.

- Source commit: `cdf3f28575bc0777aef12cf91194e3f80d2d54ef`.
- [Successful GitHub release run](https://github.com/bmaged23/MarketDeepAgent/actions/runs/39986061885).
- [Public Docker Hub repository](https://hub.docker.com/r/bmaged23/market-deep-agent).
- Tags: `cpu`, `latest`, `sha-cdf3f28575bc0777aef12cf91194e3f80d2d54ef`.
- Registry digest: `bmaged23/market-deep-agent@sha256:c30936dd22c71e0ecdfb81725028e14b45495295d3544194c525fcf970835114`.
- Gated local image ID: `sha256:ec8cd29cb9b085f525e14e83c88ca6390dbab76a7beffdb1096f627f7fa3a4db`.
- Application fingerprint shared by Docker CPU and native GPU: `7d7ec598dc23523ed4ba5317fc31484323b888612554c4e5d4834a629531d5b8`.

Verified by the successful run: Python 3.12/3.13 offline tests, candidate build, 100 live scenarios inside the image, 145 answers/290 valid judge assessments, frozen coverage/quality/critical-state gate, LangSmith export, real API/model/order/persistence smoke, exact-image publication, public pull and repeated smoke. 184 Python tests and 21 frontend tests also passed locally.

Both final CPU and GPU workflows passed 100/100. CPU answer means: correctness 90.34%, completeness 93.10%, relevance 95.00%, faithfulness 95.69%. See [evaluation](EVALUATION.md) and [measured latency/resources](PERFORMANCE.md).

The public tags were independently read anonymously from Docker Hub and all matched the digest above. LangSmith experiment `market-image-39986061885-1`, ID `cefb3eaf-5e41-43d9-8c21-bfba47f91ea3`, was independently verified to contain all 100 frozen root case IDs. Full model/tool traces remain private; aggregate evidence is [recorded here](../../evaluation/results/release-verification.json).

The public image is Linux amd64 CPU. Native CUDA inference and workflows were tested on GTX 1660 Ti 6 GB; no public GPU image or universal device compatibility is certified. Fresh CUDA wheel installation was interrupted by disk limits; matching installed CUDA libraries were reused locally. The frozen set is synthetic regression data, not human-adjudicated production traffic. Long-term preference memory is disabled in these live journeys and has separate unit tests. Earlier failed/interrupted attempts remain preserved.

The existing hosted demo remains available; it is not a newly recorded release video. This pipeline publishes images, rather than deploying a public website.
