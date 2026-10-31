# CDC Sim

Beginner-safe English manual | [中文说明](README_zh.md)

CDC Sim is a browser-based military and political simulation engine for Model United Nations crisis committees. A chair mounts a scenario, moves units on a map, resolves combat and support missions, records crisis rulings, manages political control, saves checkpoints, and exports situation reports.

**Release status:** The version already available from the [public GitHub repository](https://github.com/davidwang10d-del/cdc_sim_v1) is free to download under its existing GPLv3 license. David the Hedgehog is the public maintainer name. Commercial licensing and paid scenario packs are future plans; the local QA installer and draft EULA below are not the terms of the current public release and have not been uploaded.

> **Scenario packs:** DLC is the current runtime name for a local scenario folder. Versioned packs can now contain metadata, objectives and event cards alongside their map, forces, weapons and political settings. See the [scenario pack authoring guide](docs/scenarios/scenario-pack-format.md) for editor and build instructions. Payment and entitlement services are not implemented yet. The hidden `_template` supplies the neutral authoring starter; a playable pack is required to open the tactical dashboard.

The project follows one strict boundary:

- The core contains reusable algorithms, validation, persistence, APIs, UI, and universal command doctrine.
- Every DLC contains battle data plus scenario-specific or exceptional rules: map, order of battle, weapons, battalions, diplomacy, committee material, and theater tuning.
- Tactical orders and combat stances are defined once in **doctrine.py**. A DLC cannot redefine them.
- The core does not invent missing scenario combat or mission tuning. An incomplete or incompatible DLC is rejected before it can replace a running committee.

## Private beta

Invited testers should receive a signed Windows installer named `CDC-Sim-Setup-<version>-win-x64.exe`. The installer provides the intended **Download -> Install -> Launch -> Play** flow and does not require Python, a command prompt, this repository, or manual dependency installation.

The repository contains the local release workflow; it is not itself a released beta installer. Before sending a build, complete the signing, malware scan, distribution-rights review, and clean-Windows acceptance gates in the [product quality priorities](docs/beta/product-quality-priorities.md). Testers should follow the [private beta tester guide](docs/beta/beta-tester-guide.md).

The packaged application opens a readiness page, reports its version, stores customer data below `%LOCALAPPDATA%\CDC Sim`, and keeps scenario content separate from the engine and committee checkpoints. Leaflet and JSZip are bundled locally. The packaged local map and normal chair controls launch without a map-service account or network tile provider.

Commercial artifacts display [EULA.txt](EULA.txt) and deliberately exclude the repository's historical `LICENSE` file. That packaging choice does not erase rights already granted in older public copies; ownership and relicensing authority must be cleared before any proprietary external beta.

Source users and contributors can still use `INSTALL_OR_REPAIR.bat` and `START_CDC_SIM.bat`. Those files are development conveniences, not the tester distribution path, and require 64-bit Python 3.12. See [Manual install and startup](#manual-install-and-startup).

## First beta launch

1. Install the signed beta supplied through the private test channel.
2. Open **CDC Sim** from its Windows shortcut and keep its control window open.
3. Wait for the readiness page to open automatically. Confirm the expected product version, writable customer storage, and at least one ready scenario.
4. Choose **Open CDC Sim**, then select an available scenario.
5. Confirm `[ PAUSED ]` is visible. Open **Saves** and create Checkpoint 1 before issuing orders.

Mounting a scenario always starts from its authored state. To continue earlier work, mount the same scenario and explicitly restore a compatible checkpoint. Before stopping or upgrading, pause, save a checkpoint, and download an external backup. Closing the browser does not save the committee.

## Commercialization documents

- [Existing-file map and proposed ownership](docs/architecture/repository-file-map.md)
- [Incremental repository migration plan](docs/architecture/commercial-migration-plan.md)
- [Licensing-ready product, packaging, update, and deployment architecture](docs/architecture/licensing-ready-architecture.md)
- [Accepted private-beta runtime decision](docs/architecture/adr-0001-private-beta-runtime.md)
- [Engineering license and IP risk report](docs/commercial/license-ip-risk-report.md)
- [Scenario-pack authoring and distribution contract](docs/scenarios/scenario-pack-format.md)
- [Private-beta product quality priorities and release gates](docs/beta/product-quality-priorities.md)
- [Windows executable and installer workflow](deployment/windows/README.md)

## Main pages

| Address | Purpose |
| --- | --- |
| http://127.0.0.1:5000 | Chair/CDC tactical dashboard |
| http://127.0.0.1:5000/status | Runtime and scenario readiness check |
| http://127.0.0.1:5000/editor | Scenario builder |
| http://127.0.0.1:5000/chair_guide | English chair guide |
| http://127.0.0.1:5000/chair_guide_zh | Chinese chair guide |

Use [http://127.0.0.1:5000/zh](http://127.0.0.1:5000/zh) to open the main dashboard in Chinese. The **English** and **中文** buttons remember the language in that browser.

## Dashboard: what every area does

### Before a DLC is mounted

- **English / 中文** changes the dashboard language and reloads the page.
- **Scenario Builder** opens the editor in a new tab. It does not mount or install the exported DLC for you.
- **Guide** opens the chair guide.
- **AVAILABLE SCENARIOS** lists validated folders directly inside `dlc`. Valid entries can be mounted; invalid entries show validation errors. A folder whose name starts with `_` is hidden.

### Top clock and map bar

| Control | Exact effect |
| --- | --- |
| `▶` | Resumes simulation time. Movement, combat, recovery, missions, occupation, and expiring effects advance. |
| `⏸` | Pauses simulation time. Use this before adjudicating or explaining a result. |
| `DEFAULT` | Sets the DLC's default simulation speed. |
| `MAX` | Sets the DLC's maximum allowed speed. |
| Number + `SET` | Requests a custom speed multiplier. The DLC defines the minimum and maximum; invalid values are rejected. |
| `Local map` | Packaged dark grid basemap with no external map-service dependency. |
| `Roads` | Shows or hides the DLC road overlay when road data is available. |
| `Airdrop` | Opens the new-unit deployment panel. |
| `Zeus` | Opens chair-only edits: modifiers, personnel, cities, province politics, and diplomacy. |
| `MUN` | Opens committee information, crisis adjudication, public records, and SITREP export. |
| `Guide` | Opens the guide that matches the saved language. |
| `Saves` | Opens the three manual checkpoints and scenario reset. |
| `Editor` | Opens the DLC builder in a new tab. |

The upper-left **LOCAL GIS FEATURES** card reports Elevation, Roads, Rivers, and Provinces. `ON` means the local data is active. `OFF · DEFAULT` means CDC Sim is using its safe fallback. Red means the feature was configured but is unreadable and should be investigated.

The lower-right **LIVE THEATER INTEL** feed records system, movement, combat, and chair events. It is operational history, not an automatic save.

## Reading the clock and unit telemetry

### Simulation time versus real time

The clock uses `Dxx HH:MM:SS`. `D00 06:30:00` means day 0, 06:30 in the scenario; it does not mean the computer's current time. The clock advances only while **RUN** is active. The speed multiplier controls how quickly scenario time passes compared with real time. Pausing freezes movement, combat, recovery, construction, occupation changes, mission flight/progress, and temporary-effect countdowns. Selecting units, changing panels, saving, and preparing an order can still be done while paused.

### What every unit value means

| Displayed value | Plain-language meaning | What to remember |
| --- | --- | --- |
| **Status** | What the unit is doing now, such as holding, moving, defending, constructing, bombarding, outbound, or returning. | A status is the current activity; the Operational Order panel is the authoritative task and stance. |
| **Personnel Alive** | Current living personnel after direct combat and mission casualties. | This is headcount, not combat power. A small ready formation can outperform a larger exhausted one. At `0`, the formation has no effective living strength. |
| **Morale** | The formation's willingness, cohesion, and psychological ability to keep fighting. | Higher is better. Low morale reduces combat effectiveness but never orders an automatic retreat, surrender, or movement. |
| **Supply** | Available ammunition, fuel, food, spare parts, and general logistics on the DLC resource scale. | Higher is better. Movement, Fortify, construction, bombardment, and airstrikes consume it; insufficient supply can block or pause actions. |
| **Fatigue** | Accumulated exhaustion. | Lower is better. Movement and demanding work/missions raise it; idle recovery reduces it. High fatigue lowers combat and movement readiness. |
| **Supp. / Suppression** | Immediate disruption and inability to operate freely under pressure or fire. | Lower is better. It reduces combat and movement readiness and slows fieldwork/construction. It decays over simulation time at the DLC rate. |
| **Prepared Defense** | This unit's fieldwork progress as a percentage of the DLC maximum entrenchment. | Defend/Fortify raises it. It improves protection, but moving abandons the prepared position. |
| **Fort Cover** | Additional cover supplied by nearby operational allied installations. | It belongs to the installation's area effect, not to the unit's own Prepared Defense bar. Destroying/leaving the site removes it. |
| **MOV** | Current effective movement speed after unit data, terrain, readiness, stance, and task modifiers. | It is not merely the battalion's theoretical speed. `0` means the unit cannot currently move. |
| **Altitude** | Local elevation from the active GIS elevation package or its fallback. | Elevation can affect line of sight and combat when the DLC enables those rules. |
| **Def. Radius** | The formation's physical/defensive map footprint. | It is not weapon range. Weapon cards and range bands determine firing reach. |
| **City Influence** | The city area currently affecting the unit and its configured strength. | `None · 0.00` means no authored city effect at that coordinate. |
| **Effective Complexity** | Combined terrain and city complexity used by movement, concealment, cover, frontage, and fatigue rules. | A larger value generally means more difficult terrain, but exact coefficients belong to the DLC. |
| **OOB** | Order of battle: battalion types and counts composing the formation. | OOB supplies personnel complement, mobility/protection data, capabilities, and mounted weapon groups. |
| **Weapon Groups** | Actual mounted groups aggregated from the unit's battalions. | Only weapons whose role and range band match the action and distance contribute firepower. |
| **Armor / Armor Gen** | Numeric protection and its descriptive technology generation. | Armor is the value used by penetration calculations. Generation labels technology; it does not replace the numeric armor value. |
| **Aircraft Type** | The selected aircraft mission profile for an airstrike-capable formation. | It controls effective flight speed, sortie range, footprint, accuracy, payload, costs, and air-defense exposure. |

### Morale, precisely

The shipped DLCs display morale on a percentage-style scale. The meter is red at `0–25`, amber above `25` through `50`, and green above `50`. These colors are warnings only; they do not trigger automatic retreat or surrender.

For unit types whose DLC profile enables morale, the engine multiplies combat effectiveness by `max(morale_floor, current morale) / morale_scale`. Both values come from the active DLC, so do not assume that two different DLCs use identical morale tuning. Direct combat and airstrike shock can reduce morale. A qualifying idle or defending unit recovers morale over simulation time, up to its composition-derived maximum organization. The **Reserve** stance multiplies recovery according to core doctrine.

Do not confuse the two chair controls:

- **MUN → morale** immediately adds or subtracts morale points, clamped to the unit's allowed range.
- **Zeus → Morale multiplier** changes the rate of later morale recovery for the specified duration; it does not immediately add morale.

Morale is also separate from personnel, supply, fatigue, and suppression. Changing one does not silently rewrite the others.

## Using the tactical map: exact steps

### Select and inspect a unit

1. Click the unit symbol on the map. Clicking empty map space does not select a unit.
2. The right-side telemetry panel shows faction, status, personnel, morale, supply, fatigue, suppression, prepared defense, coordinates, speed, elevation, radius, city influence, terrain complexity, battalion composition, and primary weapon.
3. Scroll inside that panel to reach **Operational Order** and any **Support Mission** controls.
4. Click another unit symbol to switch selection directly, or click **Release** to select nothing.

### Understand task versus stance

- **Task** says what the unit will do and where: Hold, Relocate, Planned Route, Assault, Defend Here, or Fortify.
- **Combat Stance** says how it behaves: fire discipline, concealment, speed, recovery, reconnaissance, cover, and combat multiplier.
- Changing the task keeps the stance. Changing the stance keeps the task.
- `Relocate` and `Planned Route` withhold active ranged fire even if the stance normally permits it. Close-contact self-defense remains available.
- `Hold Fire` blocks ranged fire for other tasks too, but still preserves close-contact self-defense.

### Change a stance

1. Select the unit.
2. In **Combat Stance**, open the dropdown.
3. Choose a stance.
4. Read the shown combat, speed, cover, and behavior summary.
5. Click **Set Stance**. Merely choosing an item in the dropdown does not apply it.

| Stance | Use it when | Cost/tradeoff |
| --- | --- | --- |
| Aggressive | You want normal full combat power and normal movement. | Minimal concealment and no extra base cover. |
| Defensive | You want normal firepower with lower visibility and protection. | No speed or recovery bonus. |
| Stealth | You want to reduce the chance of detection. | Half movement speed, weaker combat, and weaker reconnaissance. |
| Recon | You need faster scouting and much stronger detection. | More visible and reduced combat power. |
| Reserve | You want faster recovery. | Slower movement and substantially reduced combat power. |
| Hold Fire | You must prevent active ranged fire. | Low combat multiplier; only close-contact self-defense remains. |

### Issue each task

**Hold**

1. Select the unit.
2. Click **Hold**. It takes effect immediately; no map click is needed.
3. The route is cleared and the unit stops, but its current stance remains active.

**Relocate**

1. Select the unit and click **Relocate**.
2. Click one destination on the map.
3. Review the dashed line, coordinates, and destination terrain in the authorization card.
4. Click **AUTHORIZE**. Click **ABORT** if the point is wrong.
5. The unit follows a GIS route and does not initiate ranged combat while moving.
6. If the unit detects a hostile whose threat envelope crosses the remaining route, the engine calculates a new path around that contact while preserving the original destination. The map and telemetry card update to show **CONTACT-AVOIDANCE ROUTE**.

The temporary threat envelope combines both formations' physical footprints, the hostile's direct-fire reach, the core safety margin, and terrain/road/river routing costs. It uses only contacts known to the relocating faction—there is no omniscient avoidance. The cost is deliberately high but finite: if the destination is inside the envelope or no clean detour exists, the unit can still proceed and use close-contact self-defense. An unchanged contact does not trigger repeated route calculations; a materially moved or newly detected threat can trigger another detour after the core cooldown.

**Planned Route**

1. Select the unit and click **Planned Route**.
2. Click waypoint 1, then waypoint 2, and continue in travel order. Each click adds a numbered waypoint.
3. Review the entire dashed route.
4. Click **AUTHORIZE** only after the last waypoint. The DLC limits the maximum number of waypoints.

**Assault**

1. Select a direct-combat unit and click **Assault**.
2. Click the final objective.
3. Review and click **AUTHORIZE**.
4. The unit advances at the core assault-speed multiplier and fights detected enemies while continuing to close. It halts only when a detected hostile physically blocks the advance at close ground contact, then resumes when that contact clears.

**Defend Here**

1. Select a direct-combat unit at the location to defend.
2. Click **Defend Here**. No map click is needed.
3. The unit stops, recovers, and constructs prepared defense at the normal DLC rate. Movement later abandons its fieldworks.

**Fortify**

1. Select a direct-combat unit with enough supply.
2. Click **Fortify**. No map click is needed.
3. The unit builds fieldworks faster while consuming supply and accumulating fatigue. Suppression slows construction; insufficient supply suspends it.
4. At maximum preparation, the task automatically becomes **Defend Here**.

### Build and attack military installations

Military installations are persistent map entities, not units and not another name for Fortify. **Fortify** prepares temporary fieldworks attached to one formation; moving that formation abandons them. **Military Construction** creates a separate site with its own owner, map symbol, construction progress, integrity, armor, effect radius, and save state.

To build one:

1. Stop a living ground-combat unit at the intended coordinate and select it.
2. Scroll to **Military Construction**. Choose a DLC-defined type such as **Fortification** or **Radar Site**.
3. Read its duration, total supply cost, and operational effect, then click **Build at Current Position**.
4. Press **Run**. The builder must remain within the DLC work radius in `CONSTRUCTING` status. Work consumes supply and adds fatigue; suppression slows it and the DLC stop-supply threshold pauses it.
5. **Hold**, movement, or a support mission pauses work without deleting the site. Return the builder, select the same type, and click **Resume Construction**.
6. When progress reaches 100%, the site becomes operational. Save a manual checkpoint if it must survive a restart.

The supplied Fortification adds cover to allied formations inside its effect radius. The supplied Radar Site makes probability-based contacts on hostile units and military sites inside its range. A destroyed site loses every effect but remains visible as a wreck and in the committee record.

To attack a site, select a capable hostile unit and start **Assault**, **Bombard Area**, or **Launch Airstrike**. While the targeting prompt is active, click the site's diamond symbol and authorize the order. Direct fire requires contact or close range and uses the attacker's eligible `direct_fire` weapon bands. Bombardment uses indirect `bombard` weapons; airstrikes use the selected aircraft type and mounted `airstrike` weapons. Each method resolves against the site's DLC-defined softness, armor, terrain cover, and damage multiplier rather than subtracting personnel from a fake unit.

### Run bombardment or an airstrike

The selected unit shows a support mission card only when its DLC unit type, battalions, or explicit capabilities provide the required capability.

1. Select a capable artillery or air unit.
2. Read the support card. It shows range, effect radius, duration/cost, and whether the unit is ready.
3. Click **Bombard Area** or **Launch Airstrike**.
4. The map shows the maximum range. Click an impact coordinate.
5. Check the distance and effect circle. **AUTHORIZE** is disabled for an out-of-range target.
6. Click **AUTHORIZE**.

Bombardment cancels the unit's previous movement route, lasts for the DLC-defined duration, and consumes supply over time. Airstrike supply and fatigue are charged at launch even if it misses; the aircraft is exposed to air defense, impacts the selected area, then returns to its recorded base. Both missions can affect unobserved hostile units in the area at reduced DLC-defined accuracy. A unit cannot start a second support mission while one is active; use **Hold** to halt an active mission if necessary.

Airstrike losses use an area-exposure model. The engine estimates how much of the target formation lies inside the aircraft type's effect radius, resolves the wing's mounted `airstrike` weapon bands against target softness and armor, and then applies aircraft readiness, aim quality, payload, and target cover. `strike_power_reference` calibrates weapon power, `casualty_coefficient` sets lethality among exposed personnel, and `maximum_casualty_fraction` limits the loss one sortie can inflict on each formation. The Heavy Bomber, Close Air Support, Strike Fighter, and Stealth Strike profiles produce materially different results. Pilot and ground-crew headcount is never multiplied into ordnance power. Impact reports separate personnel losses, persistent morale shock, and temporary suppression. Armies, artillery, and air wings parked at their bases are valid ground-strike targets; an air wing currently outbound or returning is airborne and therefore excluded. An aircraft on a sortie is resolved through airstrike and air-defense rules rather than ground direct combat. Artillery can Relocate when its DLC unit-type speed is above zero; use zero only for an intentionally fixed emplacement.

All offensive fire now has one source of truth: `weapons.json`. A unit aggregates `battalion count × weapon groups per battalion`; total personnel is not multiplied into that firepower a second time. Current manning and terrain-limited frontage can only reduce the share of mounted groups able to fire. At the actual engagement distance, each eligible weapon selects its matching range band; out-of-range weapons contribute nothing. Soft and hard attack are matched to target softness, and armor-piercing failure reduces only that weapon's hard-target component. Bombardment uses only indirect weapons with the `bombard` role. Weapon generation is stored on each weapon; armor protection and armor generation are stored separately on battalions. Generation labels are descriptive technology data, while the explicit attack, penetration, and armor values control the calculation.

Every airstrike-capable unit has an `aircraft_type` from its DLC. The profile changes flight speed, range, effect radius, soft/hard target specialization, accuracy, payload, morale shock, suppression, supply/fatigue cost, and air-defense vulnerability. The control panel and targeting overlay always show the selected wing's effective values.

| Test DLC wing | Aircraft type | Character |
| --- | --- | --- |
| Red | Strike Fighter | Fast precision interdiction; favors harder targets |
| Blue | Heavy Bomber | Long-range, large-area payload; costly and more exposed to AA |
| Green | Close Air Support | Short-range ground support; strong suppression and high AA exposure |
| Gold | Stealth Strike Aircraft | Fast, precise, low AA exposure; smaller strike footprint |

The unit panel's **Personnel Alive** figure is the formation's current living personnel after combat and mission casualties. It is the same authoritative value used for neutralization, map visibility, committee totals, manual saves, airdrop responses, and Zeus personnel edits. Readiness remains separate: supply, fatigue, suppression, morale, terrain, frontage, stance, and cover affect performance without silently rewriting the living-personnel count.

Morale changes effectiveness but never invents an automatic retreat destination. Every retreat or reposition must be issued explicitly as Relocate, Planned Route, or Assault.

## Deploying a new unit with Airdrop

1. Pause the simulation unless an immediate live deployment is intentional.
2. Click **Airdrop**.
3. Enter a clear, human-readable **Unit Callsign**.
4. Enter the **Faction Designation** exactly. Spelling and capitalization matter for diplomacy, reporting, and politics.
5. Select a DLC-defined **Unit Type** and read its capability help.
6. For an airstrike-capable unit, select its **Aircraft Type** and read the resulting mission profile.
7. In **Order of Battle**, set at least one battalion count to `1` or more. The base complement and derived weapon-group summary update automatically.
8. Confirm that the derived loadout includes the role the unit needs: `direct_fire`, `bombard`, or `airstrike`. Changing Unit Type selects a compatible starter battalion when one exists.
9. Leave **Deployed Personnel** at the calculated complement, or reduce it for an understrength formation. It must be greater than zero.
10. Click **Select Drop Zone on Map**.
11. Click the desired map coordinate once. A successful deployment closes the panel, centers the map, selects the new unit, and shows a confirmation.

If nothing happens, confirm that the callsign and faction are not blank, at least one battalion is selected, personnel is positive, and the browser is not waiting for you to click the map.

## Chair controls in Zeus

Zeus changes live state immediately and never saves automatically.

1. **Temporary unit effect:** first select a map unit, choose Combat/Speed/Morale, enter a multiplier (`1.0` unchanged, `1.2` +20%, `0.8` −20%) and positive simulation-hour duration, then apply it. Combat multiplies combat effectiveness, Speed multiplies movement speed, and Morale multiplies idle/defending morale recovery rate. The Morale option does not immediately add morale points.
2. **Set unit personnel now:** first select a unit, enter a whole number of `0` or greater, then click **Set personnel**. This does not change its composition, equipment, supply, or morale.
3. **City influence areas:** select an existing city or click **New**. Supply a safe ID, name, longitude, latitude, non-negative area in km², and influence from `0` to `1`; then save. Delete removes the live area after confirmation.
4. **Province politics:** select a record or click **New**. Enter the exact province-map name and faction, civilian sentiment from `-1` to `+1`, and occupation from `0` to `1`; then save. Military presence updates occupation as time advances. Hostile qualifying factions can make a province contested; allies do not contest one another.
5. **Diplomacy:** enter two different, exact faction names. **Mark as allied** creates a two-way alliance. **Mark as hostile** removes it; it does not order either side to attack.

## Recording a crisis ruling in MUN

1. Pause if the ruling should take effect at a controlled moment.
2. Click **MUN** and review the committee brief, rules of engagement, delegate roles, and faction readiness.
3. Enter a short title and a clear body explaining what happened.
4. Enter an exact faction name to affect only that faction, or use the DLC's global selector—normally `GLOBAL`—to affect every unit.
5. Choose an effect:
   - `none`: record only; no unit statistic changes.
   - `morale`, `supply`, or `fatigue`: add the entered value immediately. Use a negative value to reduce it.
   - `combat_modifier` or `speed_modifier`: apply the entered non-negative multiplier for the entered number of simulation hours. `1.0` is unchanged, `1.2` is +20%, and `0.8` is −20%.
6. Enter a positive duration. It matters for temporary modifiers; the record stores it for every ruling.
7. Keep **Publish to delegate-facing crisis feed** checked for public updates. Uncheck it for staff-only records.
8. Click **Apply Adjudication** once. Check **Public Crisis Updates** and the live intel feed for confirmation.
9. Click **Export SITREP** to download a Markdown report containing faction status and public updates.

An adjudication does not create a checkpoint. Save manually after any important ruling.

### What a SITREP is and what it indicates

**SITREP** means **Situation Report**. It is a text snapshot of the simulation at the instant it is exported. It is meant for briefing chairs, crisis staff, delegates, or the next session.

The exported report contains:

- the committee/scenario name and current simulation time;
- each faction's total living personnel;
- its number of unit records;
- simple average morale and supply across those unit records;
- counts of operational, under-construction, and destroyed military installations;
- crisis updates recorded through the MUN panel.

Read a line such as `FACTION_A: 8500 living personnel, 6 units, morale 72%, supply 64%; military sites 2 operational, 1 under construction, 0 destroyed` as: this faction currently has 8,500 living personnel distributed across six formation records, those records have an unweighted average morale of 72 and supply of 64, and the faction owns the listed site states. The averages are per unit record, not weighted by unit personnel; a 100-person unit and a 10,000-person unit each contribute one value to the average.

The normal **Export SITREP** button includes only records marked public. To include public and staff-only records, open `/api/committee/sitrep?private=1` while the DLC is mounted and save the returned Markdown text securely.

A SITREP does **not**:

- save or restore the simulation;
- declare a winner or determine whether a victory condition was met;
- include a map image, every unit's orders, or a complete casualty history;
- make private information safe to share merely because it appears in a report.

Use **Saves** for recovery. Use SITREP for communication. Exporting one does not create or update a checkpoint.

## Saves, restore, reset, and changing DLCs

- Only three UI save slots exist: Checkpoint 1, 2, and 3.
- **Save here** writes the current state. Saving to a non-empty slot asks for overwrite confirmation.
- **Restore** asks for confirmation, replaces the active state, and always leaves the simulation paused.
- **Reset scenario** discards current live progress and reloads the DLC-authored starting state. It does not make a backup.
- Mounting any DLC loads its authored start, not a previous checkpoint. Save first, mount, then explicitly restore a compatible checkpoint.
- Checkpoints are tied to both DLC ID and rules schema. An incompatible card cannot be restored.
- Saves are files named `save_slot_1.json`, `save_slot_2.json`, and `save_slot_3.json` in the project root. Battle logs are written beside them.
- Orders, routes, prepared defenses, aircraft profiles and mission state, military installations and construction progress, cities, province politics, diplomacy, unit/site detection, modifiers, committee records, and logs are included in a compatible save.

**There is no autosave.** Commands, deployment, Zeus edits, MUN rulings, diplomacy changes, reset, closing the browser, and stopping the server do not save progress.

### A complete safe practice run

Do this once before running a real committee:

1. Start the server and confirm `/status` reports ready.
2. Open the dashboard, mount a valid practice DLC, and confirm **PAUSED**.
3. Open **Saves** and save the untouched start to Checkpoint 1.
4. Select one living unit and read every telemetry value using the table above.
5. Change its stance, then click **Set Stance**.
6. Choose **Relocate**, click a nearby destination, inspect the route, and click **AUTHORIZE**.
7. Click **RUN** for a few real seconds, then click **PAUSE**. Confirm the game clock and unit coordinates changed.
8. If the unit has support or construction controls, open them and read the READY/blocked explanation; do not authorize an action you do not intend.
9. Open **MUN**, enter a harmless test update, choose effect `none`, keep it public, and apply it once.
10. Export a SITREP and open the downloaded `.md` file in a text editor. Confirm the time, faction totals, sites, and test update are present.
11. Save the changed state to Checkpoint 2.
12. Restore Checkpoint 1 and confirm the simulation pauses and the test movement/ruling disappears from live state.
13. Restore Checkpoint 2 and confirm the changed state returns.
14. When comfortable, reset the practice scenario. Never perform this experiment on the only copy of a live committee state.

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

### DLC requirements in plain language

A DLC is playable only when all of the following are true:

- It is a normal folder directly under `dlc`, for example `dlc/my_crisis`.
- The folder name uses only letters, numbers, `_`, `-`, or `.`. A playable folder must not start with `_`.
- The folder contains five readable JSON object files: `scenario.json`, `rules.json`, `units.json`, `battalions.json`, and `weapons.json`.
- A legacy folder may stop at those five documents. A versioned pack also contains `package.json`, `objectives.json`, and `events.json`; the manifest declares the exact seven payload files plus its compatibility requirements.
- `scenario.json` names the scenario, supplies a committee object and diplomacy list, contains a complete map configuration, and points to the units and rules files.
- `rules.json` uses `schema_version: 1` and retains every scenario-rule section from `_template`. It must **not** contain `orders` or `stances`; those belong to the core.
- At least one weapon and one battalion type exist. The authoring editor also requires at least one initial unit.
- Every ID is safe and unique; every unit references an existing unit type, core stance, and battalion. Any optional display `primary_weapon` must be mounted by that composition.
- All required numbers are finite and inside their documented ranges. `NaN`, infinity, numeric strings, negative personnel, zero battalion size, and out-of-range coordinates are rejected.
- Any configured path is relative and stays inside the DLC folder. Absolute paths and `..` path traversal are rejected.

The `maps` folder and all GIS files are optional. A missing optional map package does **not** make the DLC invalid. It only activates the safe defaults described below.

To install a DLC received as a ZIP:

1. Pause and save the current committee.
2. Stop the server with `Ctrl+C`.
3. Scan the ZIP if it came from someone else, then extract it.
4. Find the folder that directly contains `scenario.json`. Avoid an accidental extra level such as `dlc/my_crisis/my_crisis/scenario.json`.
5. Move that folder into the project's `dlc` folder.
6. Give it a safe, descriptive ID such as `security_council_1986`. Do not begin it with `_`.
7. Start the server, open `/status`, and fix every validation error before committee.
8. Open the dashboard and mount it. The server constructs and validates the replacement completely before it stops the old simulation heartbeat.

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

Safe GIS fallbacks are:

- no elevation: flat terrain at `fallback_elevation_m`, without elevation line-of-sight obstruction;
- no roads: normal terrain movement cost everywhere;
- no rivers: no river-crossing penalty;
- no provinces: locations are Unknown/Unmapped and no province political shading is drawn.

### scenario.json

This file owns committee identity, map placement, map file paths, diplomacy, and the names of the initial-units and rules files.

Loader-required top-level data:

- **scenario_name**, a non-empty string
- **map_config**, a complete object
- **simulation_rules_file**, a safe relative path to the rules file
- **committee**, an object
- **diplomacy_blocs**, a list
- **military_installations**, a list of optional starting forts, radar sites, or incomplete construction projects

The editor also writes **description**, **initial_units_file**, **map_center**, and **map_zoom**. `initial_units_file` defaults to `units.json` if omitted. Map center and zoom can be derived from valid bounds, but writing them explicitly is clearer and is required by the editor's package check.

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
  "diplomacy_blocs": [],
  "military_installations": [
    {
      "id": "faction_a_radar",
      "type_id": "RADAR_SITE",
      "name": "Faction A Early-Warning Radar",
      "faction": "FACTION_A",
      "lon": 1.0,
      "lat": 2.0,
      "integrity": 500,
      "construction_progress": 1.0,
      "builder_unit_id": null
    }
  ],
  "cities": [],
  "province_politics": [
    {
      "province": "Example Province",
      "faction": "FACTION_A",
      "civilian_sentiment": 0,
      "occupation": 0
    }
  ]
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
| **unit_types** | Movement/defense stat source, icons, capabilities, terrain behavior, combat eligibility, frontage, and detection profile |
| **readiness** | Supply, fatigue, suppression, and morale effects |
| **recovery** | Idle recovery, suppression decay, and entrenchment |
| **movement** | Arrival tolerance, route limit, fatigue, and supply consumption |
| **defense** | Scenario digging rates, fortification costs, supply thresholds, and suppression penalties |
| **detection** | Visibility, distance probability, contact memory, and status visibility |
| **tactical_support** | Capability-based allied support aura |
| **political_influence** | Per-faction presence, occupation gain/decay, control, contested-state thresholds, and faction weights |
| **combat** | Cover, weapon-based direct-fire equations, frontage, penetration, and elevation |
| **missions** | Bombardment, aircraft-type airstrike profiles, and air-defense behavior |
| **military_installations** | Construction work rules, integrity-damage coefficients, and DLC-defined site types/effects |
| **geography** | Line-of-sight and capability names used by pathfinding |
| **directives** | Allowed chair-adjudication effects and defaults |
| **modifiers** | Allowed modifier types, values, and durations |

Unit types remain DLC-defined because they represent battle data. Combat stances and tactical orders are core doctrine because their meaning is consistent across battles. A DLC chooses a unit's starting stance by referencing a core stance ID but cannot change the stance definitions.

Morale changes combat effectiveness but never generates an automatic retreat destination. Repositioning requires an explicit Relocate, Planned Route, or Assault order. Province tooltips synchronize live military presence even while paused; occupation and political control still change over simulation time.

Bombardment and airstrikes are coordinate-area missions rather than immunity checks against the contact list. Unobserved hostile formations inside the effect radius can still be affected at the DLC-defined reduced accuracy. Bombardment cancels an old movement route and consumes supply over its configured duration. An airstrike must stay inside the selected aircraft type's effective sortie range, commits that type's supply and fatigue costs at launch even when it misses, remains exposed to air defense according to its vulnerability factor while airborne, and returns to its recorded base after impact.

`rules.json → military_installations` has three parts. `construction` controls work radius, supply thresholds, fatigue, suppression slowdown, spacing, and the per-builder project limit. `damage` converts direct fire, bombardment, and airstrike weapon power into integrity damage and applies terrain protection. `types` defines each site's label/icon, build time and supply cost, maximum integrity, armor, softness, visibility, method-specific vulnerability, fort cover, effect radius, and radar performance. The core owns the universal construction/detection/damage lifecycle; these DLC values provide only battle data and special site behavior.

Aircraft type data lives in `rules.json → missions.airstrike.aircraft_types`. `sortie_range_km`, `blast_radius_km`, `supply_cost`, and `fatigue_cost` are the campaign baselines. Each aircraft profile applies these factors:

- flight: `cruise_speed_multiplier` and `sortie_range_multiplier`;
- weapon footprint and delivery: `blast_radius_multiplier`, `accuracy_multiplier`, `unobserved_targeting_multiplier`, and `payload_multiplier`;
- target specialization: `soft_target_multiplier` and `hard_target_multiplier`;
- secondary effects: `morale_shock_multiplier` and `suppression_multiplier`;
- operations and survivability: `supply_cost_multiplier`, `fatigue_cost_multiplier`, and `aa_vulnerability_multiplier`.

`default_aircraft_type` is used for a dynamically deployed wing and for an older save that predates aircraft profiles. Every initial airstrike-capable unit in `units.json` must explicitly reference a valid `aircraft_type`; this prevents two supposedly different air forces from silently sharing one generic performance model.

A unit-type profile chooses either source for movement, defense, breakthrough, organization, armor, softness, and terrain data:

- **stats_source: composition** — those non-offensive statistics come from battalions; or
- **stats_source: fixed** — those non-offensive statistics come from the profile’s **fixed_stats** object.

Neither mode owns attack. Soft attack, hard attack, penetration, range, weapon generation, and mission eligibility always come from mounted weapons.

Capabilities connect data to generic engine behavior. The starter rules use:

- **bombard**
- **airstrike**
- **air_defense**
- **tactical_support**
- **river_engineer**
- **heavy_river_crossing**

These names can be changed in **rules.json** as long as unit or battalion capability lists use the matching value.

Province politics is faction-specific. Every province can hold separate records for each faction: civilian sentiment (`-1` maximum opposition, `0` neutral/indifferent, `+1` maximum support), military presence, occupation (`0` to `1`), and resulting influence. Military presence gradually raises or erodes occupation. Hostile factions above the configured threshold create contested control; allied factions do not contest one another. Scenario defaults belong in `scenario.json` under `province_politics`, while timing and control thresholds belong in `rules.json` under `political_influence`.

### battalions.json

Battalions provide composition-derived defensive, movement, organization, and logistics statistics, plus weapon-group allocations.

Required numerical fields:

- **size**, a positive whole-number personnel complement used for deployment estimates
- **speed**
- **armor**
- **armor_generation**, a non-negative whole number stored separately from armor protection
- **defense**
- **breakthrough**
- **org**
- **softness** from 0 to 1
- **terrain**
- **recon_power**, which may be negative
- **movement_supply_cost**, which must be non-negative
- **weapons**, an object mapping weapon IDs to positive abstract weapon-group quantities per battalion

**capabilities** is a list of behavior names defined by the DLC’s rules. A missing or zero **size** is rejected because it would create a zero-personnel deployment that cannot appear as an active map unit.

Example:

```json
{
  "light_infantry": {
    "name": "Light Infantry Battalion",
    "size": 600,
    "speed": 8.0,
    "weapons": {"service_rifle": 5.0, "field_mortar": 0.2},
    "armor": 0.0,
    "armor_generation": 0,
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

Every weapon requires a display name, non-negative whole-number generation, explicit indirect-fire flag, one or more mission roles, and ordered range bands. Allowed roles are `direct_fire`, `bombard`, and `airstrike`. A bombard weapon must be indirect.

```json
{
  "field_mortar": {
    "name": "Field Mortar",
    "generation": 2,
    "indirect_fire": true,
    "roles": ["direct_fire", "bombard"],
    "range_bands": [
      {"max_range_km": 2.0, "soft_attack": 30, "hard_attack": 5, "armor_piercing": 100},
      {"max_range_km": 5.0, "soft_attack": 18, "hard_attack": 2, "armor_piercing": 70}
    ]
  }
}
```

Bands must have strictly increasing `max_range_km`. The first matching band supplies the attack and penetration values; beyond the final band the weapon cannot contribute. **indirect_fire: true** allows fire without direct terrain line of sight. Range alone does not grant that behavior.

### units.json

Each unit specifies its scenario identity and starting state.

Important fields:

- **name**, **faction**, and optional **icon**
- **personnel** and **equipment_level**
- **lon** and **lat**
- **unit_type**, referencing **rules.json → unit_types**
- required **aircraft_type** for an airstrike-capable unit, referencing **rules.json → missions.airstrike.aircraft_types**
- **stance**, referencing a core stance ID from **doctrine.py**
- **composition**, referencing battalion IDs
- optional **primary_weapon**, used only as a display preference and required to be mounted by the composition; omit it to let the engine choose the dominant weapon
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
| **Relocate** | Moves to one destination and automatically recalculates around detected hostile threat envelopes that cross the remaining route. It does not initiate ranged combat while moving, but it defends itself at close contact. |
| **Planned Route** | Follows the chair's explicit waypoints without automatically replacing them. It has the same holding-fire behavior as Relocate. Keep clicking to add waypoints, then authorize once. |
| **Assault** | Advances at the core assault-speed multiplier, fights while closing through ranged contact, and halts only when a detected hostile blocks it at close ground contact. |
| **Defend Here** | Stops, recovers, and builds fieldworks at the normal prepared-defense rate while retaining the current stance. |
| **Fortify** | Builds fieldworks faster while consuming supply and adding fatigue. Low supply suspends construction; completed works automatically transition to Defend Here. |

| Stance | Main tradeoff |
| --- | --- |
| **Aggressive** | Full combat power with little concealment |
| **Defensive** | Lower visibility and extra base cover |
| **Stealth** | Strong concealment and cover, but slower and weaker; it never creates an automatic retreat |
| **Recon** | Faster movement and much better detection, but reduced combat power |
| **Reserve** | Faster recovery, but slower movement and reduced combat power |
| **Hold Fire** | Withholds ranged fire while preserving close-contact self-defense |

The panel shows the effective result of the current combination. Relocate and Planned Route withhold ranged fire regardless of stance; Hold Fire also suppresses ranged fire during otherwise combat-capable tasks; close-contact self-defense remains available. Defend and Fortify create fieldworks in any stance, while Defensive stance supplies its own cover bonus.

Prepared Defense is shown as a percentage. Suppression slows construction, movement abandons fieldworks, and a stationary unit can continue using an existing position. Universal task/stance behavior, labels, and Relocate contact-avoidance settings come from **doctrine.py**; scenario digging rates, resource costs, detection tuning, and combat coefficients remain in **rules.json**.

To deploy a new unit:

1. Open the deployment panel.
2. Select at least one battalion. Its DLC-defined **size** produces the base personnel estimate.
3. Enter a unit name and faction, and adjust deployed personnel if the formation is understrength.
4. Select the drop zone.

The API rejects zero-personnel deployments. After acceptance, the dashboard refreshes immediately, centers the map on the drop zone, and selects the new symbol.

## Creating a scenario pack

Open [http://127.0.0.1:5000/editor](http://127.0.0.1:5000/editor) for the no-code builder. It edits maps, politics, forces, weapons, rules, metadata, chair-assessed objectives, and reusable event cards. **Check Package** runs local checks plus authoritative backend validation. Invalid content cannot be exported.

The editor keeps work only in the current browser page, so export intermediate ZIP drafts. A draft contains eight JSON documents and attached map files. It does not contain engine source and it does not include release checksums.

For the complete package contract, field limits, authoring workflow, release build commands, versioning, and current commercial limitations, use the [scenario pack authoring guide](docs/scenarios/scenario-pack-format.md). The short release workflow is:

1. Create a new source folder with `python scenario_pack.py init <folder> --id <package-id> --name "<name>" --publisher "<publisher>"`, or extract your own editor draft.
2. Edit and retain that folder as the source for the pack.
3. Validate it with `python scenario_pack.py validate <folder>`.
4. Build an immutable archive with `python scenario_pack.py build <folder> --output <package-id>-<version>.zip`.
5. Install the validated release under `dlc/` using a distinct folder for each version, verify GIS status, run a committee smoke test, then save a clean starting checkpoint.

Do not modify `_template` to create a scenario. Do not put Python or JavaScript in a pack. A new reusable simulation mechanic requires a reviewed engine capability; scenario content requests the capability through data.

## Chair operating workflow

Before committee:

1. Run the readiness check.
2. Mount the correct DLC.
3. Verify the scenario name, map center, units, factions, and provinces.
4. Keep the simulation paused.
5. Open **Saves** and store the clean starting state in **Checkpoint 1**.
6. Review rules, political-axis meaning, diplomacy, and delegate visibility.

During committee:

1. Resume only when simulation time should advance.
2. Translate written directives into explicit Relocate, Planned Route, Assault, Defend, Fortify, mission, diplomacy, modifier, or adjudication actions.
3. Publish only information delegates are permitted to know.
4. Save before major adjudications.
5. Export public SITREPs from the MUN button. For a chair/staff report that includes private records, open `/api/committee/sitrep?private=1` while the DLC is mounted.

After committee:

1. Pause the simulation.
2. Create a final save.
3. Export the final SITREP and retain the structured log.

## Persistence and remounting

- Saving is fully manual. Commands, deployments, committee rulings, chair edits, diplomacy changes, and resets never create or update a save automatically.
- Mounting a DLC always opens its authored starting state; it never silently resumes an old save.
- Open **Saves** to view three manual checkpoints. Each card shows whether it is empty, when it was saved, its simulation time, unit count, and any DLC/rules compatibility problem.
- **Save here** writes the current state into an empty checkpoint. **Overwrite** asks for confirmation before replacing an existing checkpoint. Saves are written atomically.
- **Restore** asks for confirmation, replaces the active state, and always leaves the simulation paused.
- **Reset scenario** is separate from restoring a checkpoint. It returns to the DLC-authored starting state and does not create a backup.
- Closing the program or changing DLCs discards changes made after the most recent manual save.
- Save files are tied to their DLC and rules schema.
- Active waypoints, explicit order modes, prepared defenses, airstrike bases, targets, modifiers, diplomacy, detection, committee records, and logs are restored.
- Mounting a different DLC builds the replacement completely before stopping the old heartbeat.

## Security and deployment

The packaged private beta listens only on `127.0.0.1`, so the same computer is the only supported client. Configuration, diagnostics, backups, and scenario content stay local unless the tester deliberately sends an exported file to the beta team. The beta has no automatic telemetry.

The local application is still a chair-level tool. It does not yet provide named accounts, committee roles, HTTPS, or a security boundary between people who can use that Windows account. Do not expose the beta port to a public network or the internet.

A source developer can explicitly set both `CDC_ALLOW_REMOTE=true` and a non-loopback `CDC_HOST` for controlled testing. That mode remains unauthenticated and is not the external-beta deployment. Future organization hosting requires the identity, authorization, tenant isolation, TLS, audit, and managed-backup controls in the [licensing-ready architecture](docs/architecture/licensing-ready-architecture.md).

## Manual install and startup

This section is for source developers. Private-beta testers should use the signed Windows installer and the [beta tester guide](docs/beta/beta-tester-guide.md). Use these commands only if the source batch files cannot run. Open PowerShell in the project folder:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe server.py
```

Do not activate the environment unless you want to; calling `.venv\Scripts\python.exe` directly guarantees that the correct interpreter is used.

To repair dependencies, run `INSTALL_OR_REPAIR.bat` again. To rebuild only the environment, first preserve DLCs and saves, stop the server, delete only the project's `.venv` folder, and rerun the installer. Never delete the whole project folder as a repair step.

To remove a source checkout, stop the server and delete the project folder after preserving custom scenarios and external backups. The packaged beta has a normal Windows uninstaller and retains customer data under `%LOCALAPPDATA%\CDC Sim` for recovery.

Leaflet and JSZip are bundled locally with their required permissive-license notices. The generated local map works offline. A future scenario pack may add separately licensed map data only after its commercial-use and redistribution rights are recorded.

## Tests

Run the complete regression suite:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The suite covers the core-doctrine/DLC boundary, independent task and stance changes, deployment strength, assault contact, holding fire while relocating, stance-independent fortification, manual-only persistence, checkpoint metadata and overwrite protection, save integrity, remount shutdown, malformed commands, admin-edit conflicts, editor data, GIS boundaries, live political presence, and combat readiness.

For a package-level check, open **/status**. Invalid DLC cards show their validation errors and cannot be mounted.

## Troubleshooting

### Double-clicking the source setup script immediately fails

Open Command Prompt and run `py -0p`. Python 3.12 must appear. If it does not, install 64-bit Python 3.12, enable the launcher/PATH options, reopen the project folder, and run the installer again. Python 3.14 being installed does not satisfy the pinned Python 3.12 environment.

### `No matching distribution found`, NumPy, Pillow, or Rasterio installation error

The usual cause is the wrong Python version or architecture. Confirm `.venv\Scripts\python.exe --version` reports Python 3.12.x. A 32-bit interpreter or Python 3.13/3.14 may not have wheels compatible with the pinned requirements. Delete only the incomplete `.venv` folder, install the correct 64-bit Python 3.12, then run `INSTALL_OR_REPAIR.bat` again.

### The system Python reports missing NumPy or Rasterio

Use **.venv\Scripts\python.exe**, not a machine-wide Python installation. Run **INSTALL_OR_REPAIR.bat** if the local environment is missing or damaged.

### The browser says “This site can't be reached”

- Confirm the black `START_CDC_SIM.bat` window is still open.
- Wait for the server startup text before opening the URL.
- Use `http://127.0.0.1:5000`, not `https://`, unless you deliberately configured something else.
- If the server says the address/port is already in use, close the other process using port 5000 or set a different `CDC_PORT` and include it in the browser URL.
- Security software may block Python. Allow only the trusted local/private-network access you need.

### The dashboard opens but the map is blank

Reload the readiness page first. The application shell, Leaflet, and local grid map are packaged with the application. Review **LOCAL GIS FEATURES** for scenario-data warnings, then copy diagnostics from the readiness page if the local map or controls still fail.

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
- **generation**, **roles**, **indirect_fire**, and ordered **range_bands** with attack/penetration values on every weapon
- positive whole-number **size**, separate **armor_generation**, a **weapons** allocation object, finite **recon_power** (negative is allowed), and non-negative **movement_supply_cost** on every battalion
- no legacy battalion **soft**, **hard**, or **ap** fields; move those values into weapon range bands
- unit types that exist in **rules.json** and starting stances that exist in core doctrine
- a complete **defense** section
- no embedded **orders** or **stances** sections; remove them from legacy **rules.json** files

Start from **dlc/_template** and copy scenario-specific data into the new format.

### Terrain falls back to plains

Elevation, roads, rivers, and province boundaries are optional local GIS packages. A configured package that has not been downloaded no longer prevents the DLC from mounting. The top-left **LOCAL GIS FEATURES** panel reports every feature as **ON** or **OFF · DEFAULT**.

When a feature is off, the simulation uses these defaults:

- Elevation: flat terrain at `fallback_elevation_m` with no elevation obstruction to line of sight.
- Roads: normal terrain movement costs everywhere.
- Rivers: no river-crossing penalty.
- Provinces: `Unknown`/`Unmapped` locations with no boundary-based political shading.

Check that:

- Rasterio is installed in the local environment.
- DEM paths are relative to the DLC.
- Files exist and use a geographic longitude/latitude coordinate system.
- DEM coverage overlaps the configured bounds.

Configured-but-unreadable packages are marked in red in the top-left GIS panel. Missing optional packages remain safe to omit.

### An airdropped unit does not appear

- Confirm the selected battalions have positive **size** values in **battalions.json**.
- Confirm Deployed Personnel is greater than zero.
- Read the rejection message instead of dismissing it; the server will not accept an invisible zero-strength unit.
- If the request succeeds but the map does not refresh, reload the dashboard and open **/status** to check the mounted package.

### The map or scenario ZIP export is unavailable

Reload the page and open **/status**. Leaflet and JSZip are bundled locally, so this indicates a damaged installation, a blocked local browser resource, or an application error rather than a missing CDN. Use **Copy diagnostics** on the readiness page and repair or reinstall the signed beta.

### A command button appears to do nothing

- Relocate, Planned Route, Assault, Bombard, Airstrike, and Airdrop enter targeting mode; the next required step is clicking the map.
- After choosing a tactical destination, you must click **AUTHORIZE**. Changing a stance also requires **Set Stance**.
- Scroll the right-side unit panel; support controls may be below the visible area.
- Read any alert and the LIVE THEATER INTEL feed. Range, supply, capability, personnel, unit type, and active-mission rules can reject an order.

### Progress disappeared after restart or after mounting another DLC

This is expected when no manual checkpoint was written. Mount the correct DLC, open **Saves**, and restore the intended compatible checkpoint. There is no autosave and mounting does not auto-restore.

## Project layout

| Path | Responsibility |
| --- | --- |
| **server.py** | Flask routes, validation boundary, mount lifecycle |
| **engine.py** | Clock, detection, politics, combat, missions, persistence |
| **app.py** | Rule-driven unit model and movement |
| **installations.py** | Persistent military-site model, lifecycle state, integrity, and serialization |
| **doctrine.py** | Universal tactical orders, combat stances, and interaction policy |
| **gis.py** | DEM, terrain, roads, rivers, pathfinding, provinces |
| **dlc_loader.py** | Safe paths and complete package/rules validation |
| **scenario_package.py** | Versioned data-only manifest, objectives/events, file inventory, and checksums |
| **scenario_pack.py** | Create, validate, inspect, and build commands for distributable scenario packs |
| **beta_runtime.py** | Validated configuration, version data, rotating logs, and privacy-bounded diagnostics |
| **beta_backup.py** | Validated external checkpoint backup and transactional recovery |
| **templates/** | Dashboard, editor, readiness page, chair guides |
| **static/** | Browser logic, styling, and locally bundled browser dependencies/notices |
| **dlc/_template/** | Neutral versioned scenario starter |
| **deployment/windows/** | Private-beta executable/installer workflow and release policy checks |
| **docs/** | Migration, architecture, IP risk, scenario authoring, and beta operations |
| **tests/** | Engine, package, runtime, recovery, server, and browser-authoring regression suite |

## Design rules for contributors

- Keep universal task/stance doctrine in **doctrine.py** and cover every change with regression tests.
- Do not add scenario names, faction names, battalion IDs, weapon IDs, unit-type names, map coordinates, or battle-specific coefficients to core Python.
- Add scenario tuning and exceptional mechanics to **rules.json** and validate them before use.
- Add unit-specific characteristics to unit, battalion, or weapon data.
- Keep path and numeric safety checks in the core.
- Reject incomplete packages rather than silently inventing values.
- Preserve transactional mounts and atomic saves.
- Add a regression test whenever a rule or state transition changes.
