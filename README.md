# CDC Sim

CDC Sim is a browser-based military and political simulation engine for Model United Nations crisis committees. Chairs mount a self-contained DLC, operate the simulation from a tactical dashboard, adjudicate delegate directives, and export situation reports.

The project follows one strict boundary:

- The core contains reusable algorithms, validation, persistence, APIs, UI, and universal command doctrine.
- Every DLC contains battle data plus scenario-specific or exceptional rules: map, order of battle, weapons, battalions, diplomacy, committee material, and theater tuning.
- Tactical orders and combat stances are defined once in **doctrine.py**. A DLC cannot redefine them.
- The core does not invent missing scenario combat or mission tuning. An incomplete or incompatible DLC is rejected before it can replace a running committee.

## Quick start on Windows

Requirements:

- Windows 10 or 11
- Python 3.12 or newer
- Internet access for the current Leaflet, map-tile, and JSZip CDN assets

First installation:

1. Double-click **INSTALL_OR_REPAIR.bat**.
2. Wait for the local environment and dependencies to finish installing.
3. Double-click **START_CDC_SIM.bat**.
4. Open http://127.0.0.1:5000/status.
5. Confirm the readiness page reports that dependencies and DLCs are valid.
6. Open http://127.0.0.1:5000 and mount a scenario.

Nothing is installed globally. Python packages are kept in the project’s **.venv** directory.

Manual startup:

```powershell
.\.venv\Scripts\python.exe server.py
```

## Main pages

| Address | Purpose |
| --- | --- |
| http://127.0.0.1:5000 | Chair/CDC tactical dashboard |
| http://127.0.0.1:5000/status | Dependency and package readiness check |
| http://127.0.0.1:5000/editor | DLC builder |
| http://127.0.0.1:5000/chair_guide | English chair guide |
| http://127.0.0.1:5000/chair_guide_zh | Chinese chair guide |

## Architecture

```text
Browser dashboard
        |
        v
Flask API (server.py)
        |
        v
Simulation engine (engine.py)
   |          |          |             |
   v          v          v             v
Units      GIS/map    Save/log state  Core doctrine
(app.py)   (gis.py)                   (doctrine.py)
        ^
        |
Validated battle package (dlc_loader.py)
        |
        v
scenario.json + rules.json (scenario-specific) + units.json
+ battalions.json + weapons.json + maps/
```

A DLC is loaded transactionally. The loader combines its validated battle rules with an isolated copy of the core doctrine, then validates paths, JSON structure, cross-file references, finite numbers, map configuration, unit types, starting stances, and the complete resolved contract. Only after construction succeeds does the server stop the previous heartbeat and activate the new engine.

## DLC package contract

Each playable folder under **dlc/** must contain:

```text
dlc/my_committee/
├── scenario.json
├── rules.json
├── units.json
├── battalions.json
├── weapons.json
└── maps/
    ├── dem_tiles/          optional GeoTIFF elevation tiles
    ├── roads.tif           optional raster or GeoJSON roads
    ├── rivers.geojson      optional river lines
    └── provinces.geojson   optional province polygons
```

Folders beginning with an underscore are support packages and are not shown on the mount screen. **dlc/_template** is the neutral starter used by the DLC builder.

### scenario.json

This file owns committee identity, map placement, map file paths, diplomacy, and the names of the initial-units and rules files.

Required top-level fields:

- **scenario_name**
- **description**
- **map_config**
- **initial_units_file**
- **simulation_rules_file**
- **committee**
- **diplomacy_blocs**

Example:

```json
{
  "scenario_name": "Example Crisis",
  "description": "Chair-facing scenario description.",
  "map_center": [0.0, 0.0],
  "map_zoom": 5,
  "initial_units_file": "units.json",
  "simulation_rules_file": "rules.json",
  "map_config": {
    "bounds": {
      "min_lon": -10.0,
      "max_lon": 10.0,
      "min_lat": -10.0,
      "max_lat": 10.0
    },
    "grid_resolution": [200, 200],
    "dem_analysis_resolution": [1200, 1200],
    "fallback_elevation_m": 0.0,
    "terrain_elevation_scale_m": 5000.0,
    "terrain_cost_multiplier": 50.0,
    "terrain_cost_exponent": 2.0,
    "pathing": {
      "road_cost": 0.5,
      "river_penalty_default": 50.0,
      "river_penalty_heavy": 500.0,
      "river_penalty_engineer": 10.0
    },
    "dem_dir": "",
    "dem_file": "",
    "roads_file": "",
    "rivers_file": "",
    "provinces_file": "",
    "province_name_property": ""
  },
  "committee": {
    "committee_name": "Example Crisis Committee",
    "committee_type": "continuous_crisis",
    "simulation_scope": "military_political_crisis",
    "start_date": "D00",
    "chair_visibility": "full",
    "delegate_visibility": "fog_of_war",
    "public_briefing": "Delegate-facing briefing.",
    "rules_of_engagement": [],
    "delegate_roles": [],
    "victory_conditions": [],
    "staff_notes": "Private chair notes."
  },
  "diplomacy_blocs": []
}
```

All configured paths must be relative and remain inside the DLC folder. A package cannot read arbitrary files elsewhere on the computer.

### rules.json

**rules.json** is required and currently uses **schema_version 1**. It owns scenario-specific tuning and special mechanics. It must not contain **orders** or **stances**; those universal sections come from **doctrine.py**.

| Section | Controls |
| --- | --- |
| **clock** | Default speed, permitted speed range, heartbeat pacing, game-time conversion |
| **resources** | Shared resource scale for morale, supply, fatigue, and suppression |
| **state_limits** | Log, committee-record, SITREP, and state-feed retention |
| **unit_defaults** | Default type, stance, resources, status, and modifier values |
| **footprint** | Personnel-to-map-radius calculation |
| **composition** | Composition-derived organization floor |
| **unit_types** | Fixed/composition stats, icons, capabilities, terrain behavior, combat eligibility, frontage, and detection profile |
| **readiness** | Supply, fatigue, suppression, and morale effects |
| **recovery** | Idle recovery, suppression decay, and entrenchment |
| **movement** | Arrival tolerance, route limit, fatigue, and supply consumption |
| **defense** | Scenario digging rates, fortification costs, supply thresholds, and suppression penalties |
| **detection** | Visibility, distance probability, contact memory, and status visibility |
| **tactical_support** | Capability-based allied support aura |
| **political_influence** | Influence range, rate, excluded states, and faction weights |
| **combat** | Cover, direct-fire equations, frontage, penetration, elevation, evasion, and routing |
| **missions** | Bombardment, airstrike, and air-defense behavior |
| **geography** | Line-of-sight and capability names used by pathfinding |
| **directives** | Allowed chair-adjudication effects and defaults |
| **modifiers** | Allowed modifier types, values, and durations |

Unit types remain DLC-defined because they represent battle data. Combat stances and tactical orders are core doctrine because their meaning is consistent across battles. A DLC chooses a unit's starting stance by referencing a core stance ID but cannot change the stance definitions.

A unit-type profile chooses either:

- **stats_source: composition** — combat statistics come from battalions; or
- **stats_source: fixed** — statistics come from the profile’s **fixed_stats** object.

Capabilities connect data to generic engine behavior. The starter rules use:

- **bombard**
- **airstrike**
- **air_defense**
- **tactical_support**
- **river_engineer**
- **heavy_river_crossing**

These names can be changed in **rules.json** as long as unit or battalion capability lists use the matching value.

Political influence is a signed scenario axis. A positive faction weight pushes a province toward the positive side, a negative weight pushes toward the negative side, and zero means that faction does not automatically alter territorial influence. The meaning of each side must be documented in the committee brief.

### battalions.json

Battalions provide composition-derived statistics.

Required numerical fields:

- **size**, a positive whole-number personnel complement used for deployment estimates
- **speed**
- **soft**
- **hard**
- **ap**
- **armor**
- **defense**
- **breakthrough**
- **org**
- **softness** from 0 to 1
- **terrain**
- **recon_power**, which may be negative
- **movement_supply_cost**, which must be non-negative

**capabilities** is a list of behavior names defined by the DLC’s rules. A missing or zero **size** is rejected because it would create a zero-personnel deployment that cannot appear as an active map unit.

Example:

```json
{
  "light_infantry": {
    "name": "Light Infantry Battalion",
    "size": 600,
    "speed": 8.0,
    "soft": 25.0,
    "hard": 4.0,
    "ap": 40.0,
    "armor": 0.0,
    "defense": 30.0,
    "breakthrough": 12.0,
    "org": 65.0,
    "softness": 1.0,
    "terrain": 1.2,
    "recon_power": 0.3,
    "movement_supply_cost": 0.02,
    "capabilities": []
  }
}
```

### weapons.json

Every weapon requires a display name, range in kilometres, and an explicit indirect-fire flag.

```json
{
  "field_mortar": {
    "name": "Field Mortar",
    "range": 5.0,
    "indirect_fire": true
  }
}
```

**indirect_fire: true** allows fire without direct terrain line of sight. Range alone no longer silently determines this behavior.

### units.json

Each unit specifies its scenario identity and starting state.

Important fields:

- **name**, **faction**, and optional **icon**
- **personnel** and **equipment_level**
- **lon** and **lat**
- **unit_type**, referencing **rules.json → unit_types**
- **stance**, referencing a core stance ID from **doctrine.py**
- **composition**, referencing battalion IDs
- **primary_weapon**, referencing a weapon ID
- optional explicit **capabilities**
- optional morale, supply, fatigue, suppression, and entrenchment
- optional saved **order_mode**, referencing a core tactical-order ID

Units may use a fixed-stat type without battalion-derived statistics, but all referenced battalion and weapon IDs must still be valid for the saved unit data.

## Operational orders: task + stance

The selected-unit dashboard combines Tactical Order and Combat Stance into one **Operational Order** panel. They are related but independent:

- **Task** answers “what should this unit do, and where?”
- **Stance** answers “how should this unit execute the task?”
- Issuing a task retains the selected stance. Changing stance retains the active task.

Select any unit marker directly; there is no need to release the previous selection first.

| Order | Behavior |
| --- | --- |
| **Hold** | Stops the unit, clears its route, and keeps its current stance. Stationary ranged fire still follows that stance. |
| **Relocate** | Moves directly to one destination. It does not initiate ranged combat while moving, but it defends itself at close contact. |
| **Planned Route** | Follows multiple chair-selected waypoints with the same holding-fire behavior as Relocate. Keep clicking to add waypoints, then authorize once. |
| **Assault** | Advances at the core assault-speed multiplier, pauses when a detected enemy enters weapon range, engages if its stance permits ranged fire, and resumes if contact clears. |
| **Defend Here** | Stops, recovers, and builds fieldworks at the normal prepared-defense rate while retaining the current stance. |
| **Fortify** | Builds fieldworks faster while consuming supply and adding fatigue. Low supply suspends construction; completed works automatically transition to Defend Here. |

| Stance | Main tradeoff |
| --- | --- |
| **Aggressive** | Full combat power with little concealment |
| **Defensive** | Lower visibility and extra base cover |
| **Stealth** | Strong concealment and automatic evasion, but slower and weaker |
| **Recon** | Faster movement and much better detection, but reduced combat power |
| **Reserve** | Faster recovery, but slower movement and reduced combat power |
| **Hold Fire** | Withholds ranged fire while preserving close-contact self-defense |

The panel shows the effective result of the current combination. Relocate and Planned Route withhold ranged fire regardless of stance; Hold Fire also suppresses ranged fire during otherwise combat-capable tasks; close-contact self-defense remains available. Defend and Fortify create fieldworks in any stance, while Defensive stance supplies its own cover bonus.

Prepared Defense is shown as a percentage. Suppression slows construction, movement abandons fieldworks, and a stationary unit can continue using an existing position. Universal task/stance behavior and labels come from **doctrine.py**; scenario digging rates, resource costs, detection tuning, and combat coefficients remain in **rules.json**.

To deploy a new unit:

1. Open the deployment panel.
2. Select at least one battalion. Its DLC-defined **size** produces the base personnel estimate.
3. Enter a unit name and faction, and adjust deployed personnel if the formation is understrength.
4. Select the drop zone.

The API rejects zero-personnel deployments. After acceptance, the dashboard refreshes immediately, centers the map on the drop zone, and selects the new symbol.

## Creating a DLC

Recommended workflow:

1. Open **/editor**.
2. Load the neutral crisis template.
3. Enter scenario and committee information.
4. Configure map bounds and optional map files.
5. Tune the common rule fields.
6. Use Advanced Rules JSON for new battle-specific unit types, capabilities, or detailed formulas. Core orders and stances are read-only.
7. Define weapons and mark each as direct or indirect fire.
8. Define battalion recon, logistics, combat data, and capabilities.
9. Place units using DLC-defined types and a core starting stance.
10. Run **Check Package**.
11. Export the ZIP.
12. Extract it to **dlc/<safe_id>/**.
13. Open **/status** and confirm the package validates before committee day.

Safe IDs use letters, numbers, underscore, dash, or dot. DLC folder names cannot begin with an underscore if they should appear on the mount screen.

## Chair operating workflow

Before committee:

1. Run the readiness check.
2. Mount the correct DLC.
3. Verify the scenario name, map center, units, factions, and provinces.
4. Keep the simulation paused.
5. Create a manual save.
6. Review rules, political-axis meaning, diplomacy, and delegate visibility.

During committee:

1. Resume only when simulation time should advance.
2. Translate written directives into explicit Relocate, Planned Route, Assault, Defend, Fortify, mission, diplomacy, modifier, or adjudication actions.
3. Publish only information delegates are permitted to know.
4. Save before major adjudications.
5. Export public or staff SITREPs as needed.

After committee:

1. Pause the simulation.
2. Create a final save.
3. Export the final SITREP and retain the structured log.

## Persistence and remounting

- The simulation autosaves after accepted commands and chair edits.
- Manual saves are written atomically.
- Loading always returns the engine to a paused state.
- Save files are tied to their DLC and rules schema.
- Active waypoints, explicit order modes, prepared defenses, airstrike bases, targets, modifiers, diplomacy, detection, committee records, and logs are restored.
- Mounting a different DLC builds the replacement completely before stopping the old heartbeat.

## Security and deployment

The default server listens only on **127.0.0.1**.

To expose it on a trusted local network:

```powershell
$env:CDC_HOST = "0.0.0.0"
$env:CDC_PORT = "5000"
.\.venv\Scripts\python.exe server.py
```

The current application does not provide authentication or role-based API permissions. Do not expose it to the public internet. A chair machine on a private conference network is the intended deployment.

The current dashboard also loads Leaflet, map tiles, and JSZip from external services. A fully offline conference deployment must vendor those assets and provide offline tiles.

## Tests

Run the complete regression suite:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The suite covers the core-doctrine/DLC boundary, independent task and stance changes, deployment strength, assault contact, holding fire while relocating, stance-independent fortification, save integrity, remount shutdown, malformed commands, admin-edit conflicts, editor data, GIS boundaries, and readiness routing.

For a package-level check, open **/status**. Invalid DLC cards show their validation errors and cannot be mounted.

## Troubleshooting

### The system Python reports missing NumPy or Rasterio

Use **.venv\Scripts\python.exe**, not a machine-wide Python installation. Run **INSTALL_OR_REPAIR.bat** if the local environment is missing or damaged.

### A DLC does not appear

- The folder name must not begin with an underscore.
- It must be directly below **dlc/**.
- Open **/status** and read its validation errors.
- Confirm **scenario.json** points to **rules.json** and **units.json**.

### A legacy DLC is rejected

Version 1 packages now require:

- **simulation_rules_file** in **scenario.json**
- a complete **rules.json**
- **terrain_cost_exponent** and complete pathing values in map configuration
- **indirect_fire** on every weapon
- positive whole-number **size**, **recon_power**, and **movement_supply_cost** on every battalion
- unit types that exist in **rules.json** and starting stances that exist in core doctrine
- a complete **defense** section
- no embedded **orders** or **stances** sections; remove them from legacy **rules.json** files

Start from **dlc/_template** and copy scenario-specific data into the new format.

### Terrain falls back to plains

Check that:

- Rasterio is installed in the local environment.
- DEM paths are relative to the DLC.
- Files exist and use a geographic longitude/latitude coordinate system.
- DEM coverage overlaps the configured bounds.

The mount response and readiness page report map-data warnings.

### An airdropped unit does not appear

- Confirm the selected battalions have positive **size** values in **battalions.json**.
- Confirm Deployed Personnel is greater than zero.
- Read the rejection message instead of dismissing it; the server will not accept an invisible zero-strength unit.
- If the request succeeds but the map does not refresh, reload the dashboard and open **/status** to check the mounted package.

### The map or ZIP export is unavailable

The current UI uses external CDN assets. Confirm internet access, reload the page, and open **/status**. This does not affect backend DLC validation.

## Project layout

| Path | Responsibility |
| --- | --- |
| **server.py** | Flask routes, validation boundary, mount lifecycle |
| **engine.py** | Clock, detection, politics, combat, missions, persistence |
| **app.py** | Rule-driven unit model and movement |
| **doctrine.py** | Universal tactical orders, combat stances, and interaction policy |
| **gis.py** | DEM, terrain, roads, rivers, pathfinding, provinces |
| **dlc_loader.py** | Safe paths and complete package/rules validation |
| **templates/** | Dashboard, editor, readiness page, chair guides |
| **static/** | Browser logic and styling |
| **dlc/_template/** | Neutral schema version 1 starter |
| **dlc/afghan/** | Example historical scenario DLC |
| **tests/** | Regression suite |

## Design rules for contributors

- Keep universal task/stance doctrine in **doctrine.py** and cover every change with regression tests.
- Do not add scenario names, faction names, battalion IDs, weapon IDs, unit-type names, map coordinates, or battle-specific coefficients to core Python.
- Add scenario tuning and exceptional mechanics to **rules.json** and validate them before use.
- Add unit-specific characteristics to unit, battalion, or weapon data.
- Keep path and numeric safety checks in the core.
- Reject incomplete packages rather than silently inventing values.
- Preserve transactional mounts and atomic saves.
- Add a regression test whenever a rule or state transition changes.
