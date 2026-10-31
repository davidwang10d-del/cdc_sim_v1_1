# ADR 0001: Private-beta runtime and data boundaries

- **Status:** Accepted for the Windows private beta
- **Date:** 2026-09-05
- **Decision owners:** CDC Sim product and engineering
- **Related:** [licensing-ready architecture](licensing-ready-architecture.md), [Windows release workflow](../../deployment/windows/README.md), [beta tester guide](../beta/beta-tester-guide.md)

## Context

Invited testers need a `Download -> Install -> Launch -> Play` experience without Python, a command line, or repository access. CDC Sim also needs to keep the existing simulation behavior, support versioned scenario products, preserve committee data across upgrades, and produce useful support evidence without collecting scenario content or secrets.

The current engine owns an in-memory clock and mutable committee state. Running several web-server processes against one session would create competing simulations. The existing GPL and third-party distribution review also remains a release gate; packaging decisions do not change those rights.

## Decision

### 1. Ship a signed, one-folder Windows application

The beta release workflow builds a PyInstaller one-folder application and wraps it in a per-user Inno Setup installer. The installed launcher starts Waitress, opens the readiness page, and prevents a second local engine instance. Release validation rejects Python source, Git metadata, customer saves, private keys, and non-allowlisted scenarios.

This gives ordinary testers an executable rather than a source checkout. PyInstaller packaging is a delivery boundary, not strong protection against a determined administrator or reverse engineer. Vendor-hosted delivery remains the stronger future option when implementation secrecy is mandatory.

### 2. Keep application, content, configuration, and customer data separate

The beta uses these logical locations:

```text
Program Files / installed release
  executable, engine, backend, UI, approved dependencies
  dlc/<scenario-id>/                 read-only scenario packages

%LOCALAPPDATA%/CDC Sim/
  config.json                        operator configuration
  sessions/<scenario-id--version>/  committee checkpoints and log
  logs/                              rotating runtime diagnostics
  support/                           user-created diagnostic reports
```

The package manifest ID and version select a session directory. Legacy unversioned scenarios keep their ID-based directory. On first use, compatible root-level checkpoints may be copied into the new session location; original files remain untouched.

Runtime configuration is validated before startup. Defaults bind to `127.0.0.1`, open a browser, and use `%LOCALAPPDATA%`. A JSON configuration file and an explicit allowlist of `CDC_*` environment overrides support operators and future deployments. Application/content/data paths must not overlap. Binding beyond loopback requires an explicit remote setting and is reserved for an authenticated deployment.

### 3. Make readiness the launch gate

The launcher opens `/status` after the server responds. That page reports the product version, release channel, dependency readiness, writable customer storage, and scenario validation. An invalid unused scenario is a warning when at least one usable scenario exists. The dashboard retains a persistent reconnect message and a route back to readiness.

Health and version endpoints expose only operational facts. They do not return filesystem paths, Python details, environment variables, customer identifiers, or scenario payloads.

### 4. Keep support data local and privacy-bounded

Runtime events are structured JSON records written to rotating local files. Unexpected failures receive a random support ID; public API responses stay generic while the local log retains a bounded diagnostic record. User-created diagnostics contain product/build facts and boolean health results, with no absolute paths, environment dump, checkpoint data, map data, scenario content, or credentials. There is no automatic telemetry in this beta.

Local support and backup endpoints require both a loopback client and an application request header. This prevents ordinary remote callers and accidental browser navigation from triggering those operations. These controls are not a substitute for authentication in a network deployment.

### 5. Back up customer checkpoints through a constrained archive

The dashboard can export and import a scenario-specific ZIP. The archive contains a manifest, hashes, up to three compatible manual checkpoints, and an optional committee log. It never contains engine code, configuration, scenario packages, or executables.

Import validates archive size, expanded size, names, duplicate/case-colliding paths, links, encryption, hashes, JSON, save-format compatibility, and scenario ID before writing. Checkpoints are replaced transactionally with rollback on failure. Import pauses the simulation and does not silently load a checkpoint; the chair chooses **Restore** afterward.

### 6. Keep browser runtime dependencies local

Leaflet 1.9.4 and JSZip 3.10.1 are bundled with recorded hashes and license texts. The generated Clean map works without a network connection. Topographic and administrative tile layers remain optional online services and need provider approval or replacement before commercial offline deployment.

## Consequences

- Testers get a repeatable install and startup path without managing Python.
- Updates can replace immutable application files while retaining `%LOCALAPPDATA%` customer data.
- Scenario packs can be sold and versioned independently from the engine, while a later entitlement service controls catalog and mount authorization.
- One application process owns one local committee. Multi-committee and organization hosting require isolated processes plus authentication, authorization, and managed storage.
- A signed installer, artifact malware scan, clean-Windows acceptance test, distribution-rights clearance, and final third-party notices remain mandatory before an external beta artifact is sent.
- Graceful tray-based shutdown, automatic update/rollback, identity, roles, telemetry consent, entitlements, and enterprise deployment controls are later product increments. They must not enter simulation calculations or make saved customer data inaccessible on a licensing failure.

## Rejected alternatives

| Alternative | Reason |
| --- | --- |
| Give testers a source ZIP and batch files | Exposes implementation and requires Python/dependency knowledge. |
| Store saves beside the executable | Upgrades and uninstall can destroy customer data; installed directories may not be writable. |
| Put scenario data into engine modules | Couples paid/customer content to engine releases and weakens content-rights isolation. |
| Run Flask's development server in the packaged beta | It is unsuitable as the supported distribution server and gives weaker lifecycle controls. |
| Start several workers for one committee | Each worker would own different mutable engine state and clock behavior. |
| Add a client-only license flag to package JSON | Customer-editable content cannot enforce entitlements. |
| Collect automatic crash uploads in the first beta | Consent, retention, tenancy, and privacy controls are not implemented. Local diagnostics provide a safer first support path. |
