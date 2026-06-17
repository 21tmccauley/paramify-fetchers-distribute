# paramify_issues — uploader (NOT BUILT)

Placeholder for the Wiz-style "write assessment findings back to Paramify"
uploader. Where the built [`paramify_evidence/`](../paramify_evidence/) uploader
attaches evidence files to an evidence set, this stage would post assessment
intake (e.g. `POST /assessment/{id}/intake`, multipart CSV + artifact JSON).

**Status: not built.** `uploader.py` and `uploader.yaml` are empty stubs. This
is the second uploader the framework needs to unblock the Wiz category. To
build it, mirror the structure and auth pattern of `../paramify_evidence/`
(HTTPS-only token guard, `--dry-run`, `--config`, per-item failure isolation,
non-zero exit on real errors).
