# Existing files and proposed ownership

Assessed 2026-09-04 against source commit `3bb8c01`; updated 2026-09-12 for the scenario-package and private-beta work. This maps current files to the proposed categories. Runtime boundaries are being implemented incrementally; the physical directory migration is intentionally deferred. See the [migration plan](commercial-migration-plan.md), [license report](../commercial/license-ip-risk-report.md), [production architecture](licensing-ready-architecture.md), and [private-beta ADR](adr-0001-private-beta-runtime.md).

## Core

| Existing file | Responsibility | Proposed home |
| --- | --- | --- |
| `engine.py` | `SimulationEngine`: timeline, combat, detection, missions, diplomacy, political control, installation effects, state serialization | `core/cdc_sim_core/engine.py`, initially intact |
| `app.py` | `MilitaryUnit`: composition, movement, readiness, weapon profiles and unit combat behavior; this is not the Flask app | `core/cdc_sim_core/units.py` |
| `doctrine.py` | Canonical orders, stances and shared doctrine | `core/cdc_sim_core/doctrine.py` |
| `installations.py` | Persistent military-installation model | `core/cdc_sim_core/installations.py` |
| `gis.py` | `MapEngine`, `ProvinceEngine`, routing, distance and terrain interpretation | `core/cdc_sim_core/gis.py` |
| `dlc_loader.py` | `DLCPackage`, rules/schema validation, cross-reference checks, configured content root, path containment, doctrine composition | `core/cdc_sim_core/scenario_loader.py`; backend later supplies the catalog/root |
| `scenario_package.py` | Versioned data-only manifest, compatibility, inventory, checksums, objectives, and events | `core/cdc_sim_core/scenario_package.py` as a shared contract |

Combat currently spans `engine.py` and `app.py`. Automated routing/detection remains within the engine, GIS and unit modules; no separate AI package exists to move. Extract shared helpers or combat modules only after behavior-preserving moves and numerical comparison checks.

Two responsibilities should eventually move out: deployment-specific content-root/catalog selection from `dlc_loader.py` belongs to backend configuration; filesystem save/log destination selection from `engine.py` belongs to storage adapters. Core keeps save serialization and compatibility semantics. Existing `package` and `storage_dir` arguments support this transition.

## Scenarios

Each tracked package, `dlc/_template/` and `dlc/test/`, contains the five legacy payloads below. A versioned package also contains the manifest and commercial-content documents shown at the end of the table:

| File | Meaning |
| --- | --- |
| `scenario.json` | Metadata, geography references, starting committee/political context and installation placement |
| `rules.json` | Supported scenario-specific tuning; excludes canonical orders and stances |
| `units.json` | Starting formations and their configuration |
| `battalions.json` | Battalion types, personnel, composition and capabilities |
| `weapons.json` | Weapon profiles and range-band data |
| `package.json` | Stable package identity, version, publisher, compatibility, payload inventory, hashes, and provenance hooks |
| `objectives.json` | Chair-facing and faction-facing scenario objectives |
| `events.json` | Data-only event cards; no executable scenario code |

Move `_template` to `scenarios/templates/starter/`, retaining a legacy alias during migration. Move `test` to `tests/fixtures/scenarios/full-spectrum/`; its metadata explicitly calls it a systems-testing sandbox. It can remain available in the developer profile, without being presented as a finished commercial campaign.

`scenarios/official/` holds approved product packs. `scenarios/customers/` should contain policy/documentation and optional ignored development mounts, while actual customer payloads live in separately permissioned content storage. The intentional `dlc/afghan/` exclusion remains unchanged and its payload is outside this follow-up audit.

Referenced local rasters, roads, rivers, province boundaries and briefings are content assets, not engine code. Record their provenance and redistribution rights per package. Scenario settings describe the simulated world; they must not contain hosting credentials or grant organization access.

## Editor

| Existing file/section | Responsibility | Proposed home |
| --- | --- | --- |
| `templates/cdc_editor.html` | Authoring UI and bindings | `editor/templates/cdc_editor.html` |
| `static/js/scenario_authoring.js` | Shared package drafting, validation, import, and ZIP export logic | `editor/static/scenario_authoring.js` |
| `scenario_pack.py` | Create, validate, inspect, and build command-line tooling | `editor/tools/scenario_pack.py` |
| `dem_scanner.py` | Authoring-time inspection and rendering of locally supplied, rights-cleared GeoTIFF files | `editor/tools/dem_scanner.py` |
| `server.py`: `/editor`, `/api/editor_template` | Serve editor resources and validated starter content | Backend editor routes |

The editor uses the shared scenario format and server validation. A future upload/install endpoint must repeat validation server-side rather than trusting editor output.

## Backend and frontend

| Category | Existing files | Explanation |
| --- | --- | --- |
| Backend | `server.py` | Flask pages/APIs, input checks, version/readiness/support/backup routes, global engine/thread lifecycle; migrate into `backend/cdc_sim_backend/` |
| Backend/platform | `beta_runtime.py` | Validated configuration, build metadata, local structured logging, redaction, and support diagnostics |
| Backend/storage | `beta_backup.py` | Bounded customer-checkpoint export/import and legacy checkpoint migration |
| Frontend | `templates/index.html` | Tactical dashboard layout and interaction bindings |
| Frontend | `templates/status.html` | Installation/readiness interface |
| Frontend | `static/js/tactical_engine.js` | Map rendering, display estimates, commands, polling, saves and committee interaction; authoritative simulation remains Python |
| Frontend | `static/css/style.css` | Shared dashboard/editor styles |
| Frontend dependency resources | `static/vendor/` | Pinned Leaflet/JSZip runtime files, checksums, and license notices |
| Served documentation | `templates/chair_guide.html`, `templates/chair_guide_zh.html` | Guides rendered by the app; retain as packaged frontend templates initially |

Move UI resources into `frontend/templates/` and `frontend/static/`, preserving current URLs during the first migration. The build must package these resources so the installed product can run outside a source checkout. Authentication, organization permissions and licensing enforcement belong to backend services.

## Documentation, tests, deployment and root metadata

| Existing files | Category and destination |
| --- | --- |
| `README.md`, `README_zh.md` | Root entry points; detailed manuals move to `docs/user/` with working links |
| `readme_zh.txt` | Legacy Chinese documentation; reconcile with the maintained manual |
| `docs/architecture/` | Migration plan, current file map, target architecture, and private-beta decision record |
| `docs/commercial/` | Engineering license/IP assessment and captured dependency evidence |
| `docs/scenarios/` | Versioned scenario-pack authoring and build guide |
| `docs/beta/` | Tester journey and commercially prioritized quality/release gates |
| `tests/test_regressions.py` | Existing engine/API/loader/GIS/frontend regression baseline |
| `tests/test_scenario_packages.py`, `tests/scenario_authoring.test.cjs` | Package security, compatibility, build, editor, and browser-authoring checks |
| `tests/test_beta_runtime.py`, `tests/test_beta_backup.py`, `tests/test_beta_server.py` | Configuration, privacy, diagnostics, backup/recovery, and tester-facing integration checks |
| `INSTALL_OR_REPAIR.bat`, `START_CDC_SIM.bat` | Source/developer setup and launch conveniences |
| `deployment/windows/` | PyInstaller/Inno Setup release assembly, launcher, policy validation, release manifest, and focused tests |
| `requirements.txt` | Root dependency input; evolve into runtime/authoring groups and platform-specific resolved locks |
| `LICENSE` | Root licensing metadata, preserved pending rights review |
| `.gitignore` | Root repository policy; exclusions are not access control |

`.git/` is repository history, `.venv/` is a local installation, and `__pycache__/` is generated cache. Do not copy them wholesale into the product.

## Configuration and customer data

`beta_runtime.py` now validates the loopback host, port, content root, customer-data root, log rotation, browser launch, and explicit remote opt-in from `%LOCALAPPDATA%\CDC Sim\config.json` plus approved `CDC_*` overrides. `server.py` passes the content and session roots into the existing loader/engine seams. A later backend package should own these adapters; scenario `rules.json` remains simulation content, not application configuration.

`save_*.json`, `battle_log*.txt`, committee records, customer uploads, exports and future audit logs belong in an organization/session data root. A save references a scenario but records one committee's activity; it is not authored scenario content. Keep these files outside source, static directories and release images.
