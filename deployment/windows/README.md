# Windows private-beta release workflow

This workflow produces the supported tester path:

> Download signed installer → Install for the current user → Launch the shortcut → Browser opens → Play

The tester does not install Python, open a terminal, run package managers, or manage a virtual environment. The build machine still needs Python 3.12, network access to the approved Python package source, Inno Setup 6, Windows SDK `signtool.exe`, and access to the organization’s code-signing certificate.

Defaults require no tester configuration. An operator can copy `private-beta-config.example.json` to `%LOCALAPPDATA%\CDC Sim\config.json` before launch to change approved local settings such as the port or log retention. The runtime rejects unknown fields and remote binding; keep secrets and customer content out of this file.

## What the release contains

PyInstaller creates a one-folder application. Inno Setup installs that folder under `%LOCALAPPDATA%\Programs\CDC Sim`. The application writes checkpoints, structured rotating logs, and support files under `%LOCALAPPDATA%\CDC Sim`, so upgrades and uninstall do not erase committee data.

Only folders named in `release_config.json` enter the build. `_template` supports the editor and `test` is the current visible synthetic package. Any local or customer scenario that is not selected is rejected from the assembled artifact. Replace the synthetic package allowlist with a distribution-approved official beta scenario before inviting external testers if `test` is not the intended evaluation content.

Raw `.py`/`.pyc` files, debug symbols, keys, environment files, save files, battle logs, Git metadata, unselected scenarios, and linked resources are rejected from the assembled bundle. PyInstaller prevents ordinary distribution of raw project source files, but it is not strong anti-reverse-engineering protection. Managed hosting is the stronger source-confidentiality model.

## Build commands

From a PowerShell prompt on the dedicated Windows x64 build machine:

```powershell
# Internal engineering artifact. Signing and installer may be omitted.
.\deployment\windows\build_release.ps1 -Channel qa -SkipInstaller

# Tester artifact. The working tree must be clean and reviewed.
.\deployment\windows\build_release.ps1 `
  -Channel beta `
  -DistributionReviewApproved `
  -CertificateThumbprint '<certificate thumbprint>'
```

`-DistributionReviewApproved` records that the release operator has closed or formally accepted the repository ownership, historical-license, browser asset, native GIS, scenario-content, EULA, and attribution findings. It does not perform or replace that review. Commercial artifacts exclude the historical root `LICENSE`, use `EULA.txt` as the installer terms, reject prohibited copyleft license options in product resources, and require the selected permissive notices for Leaflet, JSZip, pako, and zlib.

The script performs these steps and stops on the first failure:

1. Creates a clean Python 3.12 build environment.
2. Installs the application and exact builder pins, then runs `pip check`.
3. Validates the selected source/resources and all allowlisted scenarios.
4. Runs the application and deployment regression suites.
5. Stamps immutable build metadata and records `pip inspect` output.
6. Creates the PyInstaller one-folder bundle.
7. Signs the application in beta mode.
8. Hashes every bundle file into `release-manifest.json`.
9. Runs the frozen executable’s route, scenario-mount, and checkpoint self-test.
10. Builds and signs the Inno Setup installer in beta mode.
11. Rechecks file hashes and Authenticode signatures.

Artifacts remain local in `deployment/windows/artifacts/`. The workflow has no upload or publishing step.

## Independent validation

The final artifact can be rechecked on a clean Windows machine:

```powershell
.\deployment\windows\validate_release.ps1 `
  -BundlePath '<stage>\bundle' `
  -ManifestPath '<stage>\release-manifest.json' `
  -InstallerPath '<stage>\installer\CDC-Sim-Setup-<version>-win-x64.exe' `
  -PythonExe '<builder-python.exe>' `
  -RequireSignatures
```

Local engineering verification on 2026-09-15 assembled a 256-file, 131,267,968-byte PyInstaller QA bundle and a 34,804,642-byte installer. Bundle policy, file-manifest verification, and the frozen route, GIS import, scenario mount, checkpoint, backup export, and backup import self-test passed. A silent installation, installed-app self-test, and silent uninstall also passed; application data remained separate after uninstall. The QA installer remains local and unsigned, so it is an internal acceptance artifact rather than an externally distributable beta. The current source suite passes 140 tests with one expected symlink-privilege skip, and the release-policy suite passes 5 tests.

For final acceptance, install into a disposable standard-user Windows account, disconnect the source checkout and builder environment, and test install, first launch, duplicate launch, scenario mount, pause/run, checkpoint save/restore, backup/restore, diagnostics, clean stop, repair install, upgrade, and uninstall. Verify that user data survives upgrade/uninstall and the former build still restores its own backup before promoting a release.

## Release decisions and business value

| Change | Commercial readiness and business impact | Difficulty | Timing |
| --- | --- | --- | --- |
| Frozen runtime plus per-user installer | Removes Python and command-line setup, reducing onboarding failure and support time | Medium | Before beta |
| Explicit resource/scenario allowlist | Prevents accidental disclosure of source, customer files, ignored maps, or unreleased packs | Medium | Before beta |
| Separate `%LOCALAPPDATA%\CDC Sim` data | Preserves committee checkpoints across repair, upgrade, and uninstall | Medium | Before beta |
| Waitress single-process launcher | Replaces Flask’s development server while preserving one simulation timeline | Low | Before beta |
| Automatic readiness/browser open | Delivers the promised launch-to-play flow and produces a clear startup failure | Low | Before beta |
| Build identity, dependency inventory, file hashes | Makes tester reports and supplied artifacts traceable to one version/revision | Medium | Before beta |
| Authenticode and signed installer gate | Reduces Windows trust prompts and makes tampering easier to detect | Medium; certificate operations required | Before external beta |
| Full dependency hash lock and artifact SBOM | Improves reproducibility and response to dependency vulnerabilities | Medium | Before external beta if distribution review requires it; otherwise immediately after first internal build |
| Native launcher/tray UI with Open and Exit | Removes the remaining visible console and Ctrl+C shutdown step | Medium | After beta unless tester feedback makes it a blocker |
| Delta updater/rollback service | Reduces update size and supports controlled fleet rollout | High | After beta; use full signed installers between sessions first |

## Known limits

- This repository does not contain a code-signing certificate, Inno Setup, Windows SDK signing tools, or a clean Windows test VM. Those gates can only be completed on the controlled Windows build/acceptance host.
- The root dependency file pins direct packages but not every transitive wheel/hash. The generated dependency inventory records the concrete build, but it is not yet a hash-locked supply-chain input.
- The launcher retains a visible control window. Closing the browser leaves the local server running; the tester saves, then presses Ctrl+C in that window.
- The current commercial profile uses the packaged local grid map. Add offline regional imagery only after the exact dataset permits commercial use and redistribution and its attribution is included.
- A frozen executable hides raw source files but remains inspectable by a customer who controls the machine. Offer a managed deployment when keeping the engine implementation inaccessible is a firm requirement.
- Paid-pack entitlements, publisher signatures, organization authentication, automatic update delivery, crash-report upload, and remote multi-user access are separate product capabilities. This local beta installer does not pretend to enforce them.
