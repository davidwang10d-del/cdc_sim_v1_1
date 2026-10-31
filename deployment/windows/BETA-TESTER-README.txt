CDC SIM PRIVATE BETA
====================

INSTALL
1. Run the signed CDC-Sim-Setup-<version>-win-x64.exe supplied by the beta operator.
2. Keep the default per-user installation folder and select Install.
3. Leave Launch CDC Sim selected on the final screen.

LAUNCH AND PLAY
Use the CDC Sim shortcut in the Start menu or on the desktop. A small control
window stays open, CDC Sim checks its installation, and your browser opens the
readiness page automatically. When all checks are green, click Open dashboard,
then choose the supplied scenario and wait for its map and
units to appear. Python, a command prompt, and dependency installation are not
required.

SAVE AND STOP
Pause the simulation and save a manual checkpoint before stopping. Then return
to the CDC Sim control window and press Ctrl+C. Closing only the browser does
not stop the simulator. Starting CDC Sim a second time opens the already-running
dashboard instead of starting a second simulation process.

DATA AND RECOVERY
Checkpoints, logs, and support files live under:
  %LOCALAPPDATA%\CDC Sim

They are separate from the installed application and are retained by uninstall.
Use the dashboard backup action when available, and keep the downloaded backup
with the exact scenario-pack version used by the committee. Restore through the
product workflow; do not copy individual save files into the installation.

TROUBLESHOOTING
- If the browser does not open, wait for the control window to finish starting,
  then open http://127.0.0.1:5000/ in a browser.
- If CDC Sim reports a Support ID, send that ID and the product version to the
  beta operator. Logs stay on this computer and are never uploaded automatically.
- The packaged local grid map and approved scenario data work without an
  internet connection. Use only maps supplied with an approved scenario pack.
- Use only signed installers supplied by the beta operator.

This beta may contain unfinished features. Do not use it for real military,
emergency, or operational decisions.
