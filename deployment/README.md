# CDC Sim deployment boundary

This directory contains supported product-delivery workflows. The root batch files remain development conveniences; they are not tester installers and they are not release inputs.

The first implemented target is a per-user Windows private-beta installer. It freezes the Python runtime and dependencies, bundles only explicitly selected scenarios and UI assets, keeps customer data outside the application directory, and validates the assembled artifact before it can be handed to a tester.

No workflow in this directory uploads, publishes, or deploys an artifact. Promotion remains an operator-controlled local step after licensing, security, content-rights, and acceptance reviews.

## Supported deployment paths

| Path | State | Intended use |
| --- | --- | --- |
| Windows x64 per-user installer | Implemented build definition; requires Windows build tools and signing for beta | Selected private-beta chairs |
| Unsigned Windows QA bundle | Implemented | Internal packaging and acceptance checks only |
| Vendor-hosted organization service | Architecture proposed in `docs/architecture/licensing-ready-architecture.md` | Preferred commercial model after authentication and isolation |
| Customer-hosted/offline enterprise | Proposed | Later, after licensing controls and support contracts are defined |

See [windows/README.md](windows/README.md) for the release gates and local build procedure.
