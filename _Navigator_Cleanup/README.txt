Navigator folder cleanup - 30 October 2026

The Navigator suite's plugin folders were renamed so they match their names in EDMC:

  Systems_Navigator                  -> Navigator_Cartography
  Ship_Computer                      -> Navigator_Dashboard
  Docking_Navigator                  -> Navigator_Docking
  Ship_Radio                         -> Navigator_Radio
  Voice_Navigator                    -> Navigator_Voice
  Neutron_Highway_Navigator          -> Navigator_Neutron_Highway
  Neutron_Highway_Navigator_Auto     -> Navigator_Neutron_Highway_Auto
  Navigator_Interface                (unchanged)

After installing the new plugins, the old folders are still in your plugins folder, and EDMC
would load both copies. Run this cleanup once:

1. Close EDMC.
2. Extract the new suite ZIP into the EDMC plugins folder (File > Settings > Plugins > Open).
3. Open the _Navigator_Cleanup folder there and double-click Navigator_Cleanup.bat.
4. Start EDMC.

What it does:
- Moves each old folder into plugins\_Navigator_old_backup. EDMC ignores folders that start
  with an underscore. Nothing is deleted; to undo, move a folder back out.
- First copies anything an old folder kept that the new version does not ship, such as Voice
  backups, into the new folder, without overwriting.
- Leaves an old folder alone if its new version is not installed, so no plugin disappears.
- Refuses to run while EDMC is open.

Your settings, panel order, High Contrast choices, odometer, routes and other data are kept.
They are stored outside these folders, and (N) Interface carries the folder-based choices over.

When you are happy, you may delete _Navigator_old_backup and _Navigator_Cleanup yourself.
