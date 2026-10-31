# Authoring and distributing scenario packs

Status: package format v1 is implemented. Engine algorithms and universal doctrine remain in the application. A scenario author can change the map, forces, weapons, political setting, committee objectives and event cards through data and the editor without editing engine code.

This is the content packaging foundation for paid packs. Payment processing, organization entitlements, authenticated downloads, publisher signatures and customer runtime packaging are separate commercial work described in [the architecture](../architecture/licensing-ready-architecture.md). The repository's existing license still applies; a metadata field does not replace it.

## Contents and ownership

```text
CDC Sim application
  dlc_loader.py         validates packages and adapts them to the existing engine
  scenario_package.py   package contract, card validation and content checksums
  scenario_pack.py      authoring and release build commands
       |
       +-- Scenario package
             package.json       identity, publisher, version, compatibility, terms
             scenario.json      map configuration and political/committee setting
             units.json         initial forces, factions and equipment references
             weapons.json       weapons and performance data
             battalions.json    force composition and battalion data
             rules.json         existing scenario tuning; no universal doctrine overrides
             objectives.json    chair-assessed objectives and written success criteria
             events.json        chair-prepared rulings using supported engine effects
             maps/              optional terrain, roads, rivers and province data
             assets/            optional supporting images/data
             briefings/         optional text/image reference material
             ATTRIBUTION.md     optional third-party credits and data provenance
             LICENSE.txt        optional package distribution terms
             README.md          optional author/operator instructions
```

The eight JSON files belong to the pack. Python, JavaScript, binaries, credentials, customer saves and logs do not. Supporting files are included in the archive; a generic attachment browser is not implemented.

| Product concept | Existing data location |
| --- | --- |
| Map | `scenario.json.map_config`, `map_center`, `map_zoom`, plus files under `maps/` |
| Units | `units.json` referencing `battalions.json` and `weapons.json` |
| Weapons | `weapons.json`; capability and theater tuning in `rules.json` |
| Political settings | `scenario.json.diplomacy_blocs`, `province_politics`, `cities`, `committee` |
| Objectives | `objectives.json`; older `committee.victory_conditions` remain supported |
| Events | `events.json`; effects use the existing chair adjudication service |
| Metadata | `package.json` |

Map and political settings deliberately stay in the existing scenario schema. Splitting them into new files would add migration work without changing the authoring boundary. The existing five-file scenarios remain loadable.

## Create a pack in the editor

1. Start the local application and open `/editor`.
2. Set the package ID, title, version, publisher, description and distribution terms in Metadata.
3. Use the existing map, forces, weapon, rules and political/committee controls.
4. Add Objectives and Events. Choose faction names already declared by the scenario. The configured global faction token targets all factions.
5. Check the package and correct validation errors before exporting.
6. Export a ZIP draft. Extract your own draft into a new working directory, then run the release build below when the content is ready.

The editor validates all eight JSON documents on the backend without mounting a scenario or changing a running committee. That preview excludes uploaded GIS bytes; validate the complete folder before release. Browser exports are authoring drafts without release checksums. Reopening an existing ZIP in the editor is not yet implemented; maintain the extracted JSON folder as the editable source.

## Create, validate and build from files

From the repository root, with its Python environment active:

```powershell
python scenario_pack.py init scenarios/customers/example/harbor-crisis --id harbor-crisis --name "Harbor Crisis" --publisher "Example MUN"
python scenario_pack.py validate scenarios/customers/example/harbor-crisis
python scenario_pack.py build scenarios/customers/example/harbor-crisis --output releases/harbor-crisis-1.0.0.zip
```

The create command copies the neutral template and adds one example objective and event. Edit the eight JSON documents and add map files; engine code stays unchanged. Both create and build refuse to overwrite existing destinations. Build output must be outside the source folder.

The build stages a snapshot, validates it, computes SHA-256 for every payload file, then creates a ZIP with stable file ordering and timestamps. Rebuilding unchanged content in the same environment produces identical bytes. Archive compression may differ across runtime versions. No source code or customer runtime data is included.

To edit an extracted release, remove its generated `content_hashes` field from `package.json`, increment the version and treat it as a new draft. Retain the original release unchanged. Build generates fresh hashes. Ordinary validation of a sealed release rejects stale hashes.

## Manifest contract

```json
{
  "schema_version": 1,
  "id": "harbor-crisis",
  "version": "1.0.0",
  "name": "Harbor Crisis",
  "description": "A political and logistics crisis around a contested port.",
  "publisher": "Example MUN",
  "license": "Insert approved package distribution terms here.",
  "engine_api_version": 1,
  "required_capabilities": ["chair_objectives.v1", "chair_events.v1"],
  "files": {
    "scenario": "scenario.json",
    "rules": "rules.json",
    "units": "units.json",
    "weapons": "weapons.json",
    "battalions": "battalions.json",
    "objectives": "objectives.json",
    "events": "events.json"
  }
}
```

All shown fields are required; only the generated `content_hashes` field is additionally accepted. Paths in `files` are fixed for v1. `scenario.json` references `units.json` and `rules.json`.

- ID: 1–64 characters, starts with a letter, number or underscore; remaining characters may include dot and dash.
- Version: numeric `major.minor.patch`, no leading zeros or prerelease suffixes, at most 32 characters.
- Name and publisher: nonblank, at most 160 characters each.
- Description: at most 2,000 characters; license text: nonblank, at most 1,000.
- Schema and engine API versions: integer `1`. An unsupported version fails before mounting.
- Capabilities: unique entries from the supported set. A nonempty objectives/events list requires its corresponding capability.
- Build adds a map of relative path to lowercase SHA-256, covering all payload files except the manifest itself.

Package API version describes the data contract, not the engine release number. Use a new package major version for incompatible scenario changes, minor for compatible content additions, and patch for corrections. Change the engine API version only when its supported package contract changes.

## Objectives

```json
{
  "schema_version": 1,
  "objectives": [
    {
      "id": "ceasefire",
      "title": "Negotiate a ceasefire",
      "description": "Keep the relief corridor open.",
      "faction": "GLOBAL",
      "success_criteria": "The chair confirms all delegations accepted the ceasefire.",
      "points": 10
    }
  ]
}
```

Objectives are displayed in the MUN panel for chair assessment. Points are advisory values; no score is awarded or persisted automatically. Success criteria are plain text, not expressions.

Each field in the example is required. IDs must be unique within the objectives list. Titles have a 160-character limit, descriptions and success criteria 4,000. Success criteria must be nonblank. Points must be finite numbers from 0 to 1,000,000. At most 500 objectives are accepted.

## Events

```json
{
  "schema_version": 1,
  "events": [
    {
      "id": "relief-offer",
      "title": "Relief agency offers assistance",
      "body": "Aid is available if delegations agree on safe access.",
      "trigger_note": "Chair may introduce this after the first diplomatic round.",
      "faction": "GLOBAL",
      "effect_type": "none",
      "value": 0,
      "duration_hours": 12,
      "public": true
    }
  ]
}
```

Each event appears as a reusable chair card. **Prepare ruling** fills the existing adjudication form. The chair reviews it and uses the existing apply action to record the ruling and apply its effect. Preparation alone changes no simulation state. Cards are reusable and are not automatically marked as consumed.

| Effect | Existing adjudication behavior |
| --- | --- |
| `none` | Record the ruling without a numerical effect |
| `morale` | Adjust affected units' morale |
| `supply` | Adjust affected units' supply |
| `fatigue` | Adjust affected units' fatigue |
| `combat_modifier` | Add a temporary combat multiplier |
| `speed_modifier` | Add a temporary speed multiplier |

Only effects also enabled by `rules.json.directives.allowed_effects` are accepted. The engine's existing bounds and duration semantics still apply. Numeric effects use the same units as the chair form. `trigger_note` is plain guidance for the chair; there is no automatic clock/condition evaluator.

Every example field is required. Event IDs must be unique within the events list. Title limit is 160 characters; body and trigger note limits are 4,000. Trigger notes must be nonblank. Values must be finite, between -1,000,000 and 1,000,000; multipliers must be 0–100. Duration must be greater than 0 and at most 87,600 simulation hours. `public` must be a JSON boolean. At most 500 events are accepted.

Both card types accept factions declared by units, diplomacy bloc members or delegate roles, plus the global token in `rules.json.directives.default_faction`. `GLOBAL` in these examples is the template's token, not a reserved name imposed on every scenario.

The current application is a chair-operated local tool. `public` controls the existing ruling-record visibility behavior; it does not create authenticated delegate access or conceal authored card data from people who have access to the local application.

## Validation and compatibility

The loader validates the existing scenario, registries and rules first, then the new contract. Derived package metadata and cards are attached to the existing committee view in memory. No engine algorithms or new execution hooks are needed.

Legacy folders without any of the three supplemental documents continue to load unchanged. If objectives or events exist without a manifest, loading fails instead of silently discarding them. New-format packages require all eight JSON files, even when card lists are empty. Unknown card/manifest fields are rejected to catch misspellings and unsupported behavior.

The release builder accepts only the eight root JSON files, the three optional documentation files, and approved data extensions under `maps/`, `assets/` or `briefings/`: JSON, GeoJSON, TIF/TIFF, HGT, PNG, JPEG/JPG, WEBP, Markdown and TXT. It rejects executable content, VRT files, symlinks, junctions, unsafe paths, case collisions, extra runtime files, more than 4,096 files, or more than 4 GiB expanded payload. JSON documents have an 8 MiB limit.

Path checks and checksums do not establish a publisher's identity. An attacker able to modify both payload and manifest can recompute the hashes. Image/GIS decoder isolation and signed provenance remain separate production controls. There is no untrusted ZIP upload or extraction endpoint in this change.

Optional GIS paths retain the existing fallback behavior: a missing layer can still validate. Before shipping a geography-dependent pack, verify the dashboard's GIS status and the expected map manually. A successful JSON check does not certify map accuracy, scenario balance or redistribution rights.

## Install and commercialize

For the current local runtime, place a validated package folder directly under `dlc/`, for example `dlc/harbor-crisis-1.0.0/`, then choose it from the campaign list. Validate after extracting an archive from a trusted publisher and before loading it. No automatic installer or paid-download service is introduced here.

Keep authoring content under `scenarios/official/`, `scenarios/customers/<organization>/` or `scenarios/templates/` as the repository migration proceeds. Deploy release copies to the current `dlc/` adapter until configurable content storage is implemented.

Use a distinct installation directory per package release. Existing saves are associated with the folder's DLC ID and do not enforce a package content digest. Never overwrite a package used by an active committee; retain its exact release and saves for rollback.

For selling packs, the next backend work is:

1. An authenticated organization account and server-side entitlement record keyed by stable package ID.
2. A private catalog mapping package ID/version to an immutable artifact digest; verify publisher signatures and entitlements before installation or session creation.
3. Separate storage for the immutable pack, deployment configuration, and organization-specific saves, records and uploads.
4. A tenant-aware package installer, session pinning and restore compatibility checks.
5. Payment-provider webhooks that update entitlements idempotently, with an explicit expiry/offline policy.

An author must not supply executable Python or JavaScript in a pack. If a scenario needs a new type of simulation mechanic, add a reviewed reusable engine capability in a separate engine release, then allow packs to request it. This preserves one engine across official, customer and paid content.
