# CDC Sim private beta tester guide

This guide is for invited MUN chairs and crisis staff using a packaged Windows beta that has passed the release gates in the product-quality report. The repository now contains the packaging workflow, but that workflow is not itself a released installer. Distribute only the signed, validated installer and its recorded SHA-256 value; never give testers the source checkout or an unsigned QA bundle. With that artifact, testers do not need Python, a command prompt, or knowledge of the source code.

## Before the event

Use a 64-bit Windows 10 22H2 or Windows 11 computer with a current version of Edge, Chrome, or Firefox. Keep enough free disk space for the application and scenario maps. CDC Sim bundles its core browser libraries and local grid map, so normal chair controls start without a map-service account or internet tile provider.

Obtain the installer and any scenario pack only from the private beta channel named by the beta coordinator. Record the installer SHA-256 value supplied with the release. Do not use an installer whose value differs.

## Download → Install → Launch → Play

### 1. Download

Download the `CDC-Sim-Setup-<version>-win-x64.exe` file supplied by the beta coordinator. You do not need the project repository, Python, or separate dependency installers.

### 2. Install

1. Close any older CDC Sim beta that is running.
2. Double-click the setup file.
3. Follow the installer prompts. It installs for the current Windows user and does not require you to configure Python.
4. The private-beta installer is expected to have a valid Windows publisher signature. If Windows reports an unknown publisher, an invalid signature, or an unexpected filename, stop and report it to the beta coordinator even when the hash appears correct.
5. Finish the installer and use the **CDC Sim** shortcut it creates.

The application files and your committee data are separate. Reinstalling or upgrading the application should leave your data under `%LOCALAPPDATA%\CDC Sim` intact, but export a backup before every upgrade.

The supported beta keeps configuration in `config.json`, checkpoints under `sessions`, rotating runtime logs under `logs`, and safe support data under `support` within that folder. Scenario content stays with the installed application. Testers normally should not edit or copy these files directly; use the dashboard's backup controls for recovery and change configuration only when the beta coordinator provides a reviewed file.

### 3. Launch

1. Open **CDC Sim** from the Start menu or its shortcut.
2. Keep the CDC Sim control window open. It starts the local simulator, checks health, and opens the readiness page in your browser when the server is ready.
3. Confirm that the expected product version and release channel appear, customer data storage is ready, and at least one supplied scenario is ready. An invalid unused scenario appears as a warning and does not block a usable scenario.
4. Choose **Open CDC Sim**. If the browser does not open automatically, use the local address shown in the control window. Do not use an `https://` address.

Opening the shortcut a second time does not start a second simulation. It opens the already-running dashboard and exits the duplicate launcher. You can return to the readiness page at any time with the dashboard's **Readiness** button.

### 4. Play

1. On the scenario screen, select the scenario supplied for the committee. Invalid scenarios remain unavailable and show a reason.
2. Wait for the tactical dashboard and units to appear.
3. Confirm that the timeline says **PAUSED**. Review any GIS warnings. **OFF · DEFAULT** means the scenario is using the stated safe fallback; a red configured-but-unavailable warning should be resolved before the event.
4. Open **Saves** and save **Checkpoint 1** before issuing an order. This is your clean starting point.
5. Use **Run** only when committee time should advance. Pause before a major ruling, restore, backup import, or explanation to delegates.
6. Save another checkpoint after important crisis turns. CDC Sim uses manual checkpoints; closing the application does not save unsaved changes.

The dashboard's scenario editor and chair controls are administrative tools. Do not share the chair browser session with delegates.

## Save, back up, and recover

### Manual checkpoints

CDC Sim provides three checkpoint slots. A checkpoint stores the running simulation state, including units, military sites, politics, diplomacy, committee records, and the live event history. Saving over an occupied slot requires confirmation. Restoring also requires confirmation and always leaves the timeline paused.

Use the slots deliberately:

- **Checkpoint 1:** clean committee start.
- **Checkpoint 2:** latest stable turn.
- **Checkpoint 3:** before a major adjudication or experimental branch.

These labels are a recommended chair practice; the application does not enforce them.

### Download an external backup

1. Pause the simulation.
2. Save at least one checkpoint.
3. In **Saves**, choose **Download backup**.
4. Keep the resulting `cdc-sim-…zip` file somewhere outside the computer, such as an organization-controlled drive.

The archive contains validated checkpoint files, a small backup manifest, and the operational battle log when size permits. It does not contain the simulation engine, an installed scenario pack, configuration secrets, or executable files. The log is included as reference material; backup import restores checkpoints only.

### Restore an external backup

1. Launch CDC Sim and mount the same scenario used to create the backup. Use the same scenario-pack version whenever possible.
2. Open **Saves** and choose **Import backup**.
3. Select the CDC Sim backup ZIP and approve the overwrite warning.
4. Wait for the success message. Import replaces matching checkpoint files but does not change the running simulation.
5. Select the intended checkpoint and choose **Restore**. Confirm that the timeline remains paused and inspect the time and unit state before resuming.

CDC Sim checks the archive layout, hashes, checkpoint format, and scenario ID before replacing files. A damaged, altered, oversized, or wrong-scenario backup is rejected. If import fails, the current checkpoint files are left unchanged.

### Recover after a crash or forced restart

1. Launch the same installed build.
2. Mount the same scenario.
3. Open **Saves** and inspect the saved time and scenario shown for each checkpoint.
4. Restore the newest known-good checkpoint.
5. If local checkpoints are unavailable, import the latest external backup and then restore a checkpoint.

Actions after the last successful manual save cannot be reconstructed. Do not use **Reset scenario** as a recovery action; reset returns to authored starting conditions and does not create a backup.

## Finish a session safely

1. Pause the timeline.
2. Save the intended final checkpoint and wait for the success message.
3. Download an external backup.
4. Export a final SITREP if the committee needs one.
5. Close the browser tab.
6. Focus the CDC Sim control window and press **Ctrl+C** once. Wait for it to report that the server stopped, then close the window if necessary.

Closing only the browser leaves the local simulator running. No command needs to be typed into the control window. A later desktop shell should replace this interim beta shutdown step with an **Exit CDC Sim** control.

## Updates and rollback

Before installing an update:

1. Record the current version and build ID from the readiness page.
2. Mount each scenario whose work must be retained, save a checkpoint, and download its backup.
3. Stop CDC Sim completely.
4. Keep the previous installer until the new build has passed your event rehearsal.
5. Run the replacement installer, launch the application, and verify the new version/build.
6. Mount the same scenario version and confirm its checkpoints. Import the external backup only if recovery is needed.

The private beta does not silently update itself. A downgrade should use the previous installer and a backup created by that build. Ask the beta coordinator before restoring a newer save into an older build.

## When something goes wrong

### The dashboard reports a lost connection

Stop issuing actions because the latest request may not have reached the simulator. Keep the browser open, confirm the CDC Sim control window is still running, and choose **Retry** in the connection banner. If the connection does not return, stop and relaunch CDC Sim, mount the same scenario, and restore the last checkpoint.

### A scenario will not open

Read the reason on its scenario card or readiness page. Confirm that you selected the pack supplied for this product build. Do not rename folders or edit the scenario package during an event. An invalid unrelated pack should be reported to the coordinator and kept separate from the event scenario.

### Save or backup fails

Leave the simulation paused. Do not overwrite other slots while investigating. Check that Windows has free disk space and that security software has not blocked the application. Try another checkpoint slot. If a support reference appears, record it exactly.

### The map is blank

The application shell and local grid map are bundled. Review **LOCAL GIS FEATURES** for scenario-data warnings; the simulation can use authored safe defaults for absent optional GIS layers. If the local map fails, record the build ID, reopen the dashboard once, and report the problem before the event.

## Report a beta issue

Open **Readiness**, choose **Copy diagnostics**, and paste the privacy-safe result into the private support channel supplied with your invitation. Add the following:

- Product version, build ID, scenario API version, and scenario name/version.
- Support reference such as `ERR-…`, if one appeared.
- The action you took, what you expected, and what happened.
- Whether the timeline was paused or running.
- Whether retry, restart, or checkpoint restore succeeded.
- A screenshot that excludes delegate or customer-confidential content where possible.
- The safe diagnostics text from the readiness page, when available.

Do not send a complete customer scenario, backup, battle log, or configuration file unless the support contact explicitly requests it and your organization authorizes sharing it. Runtime logs are stored under `%LOCALAPPDATA%\CDC Sim\logs`; they are structured and redact common secrets and paths, but they may still describe operational actions. CDC Sim does not upload logs, diagnostics, crashes, or telemetry automatically in this beta.

## Current private-beta limits

- Normal use is limited to the same Windows computer. The local server listens on loopback by default. Do not change it to a LAN or public address.
- There is no supported shared-network, internet-hosted, delegate-login, entitlement-enforcement, or role-based deployment in this beta. The local API is not protected by production authentication.
- Saves are manual; there is no autosave.
- Use the exact scenario-pack version that created a backup whenever possible. Current save compatibility does not yet bind every save to a full scenario content digest.
- The application shell and local grid map work without an external map or elevation service.
- Updates are delivered manually through the private beta channel.
- The visible control window and **Ctrl+C** shutdown are interim beta behavior.

