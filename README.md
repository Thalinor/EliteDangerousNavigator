Not fully ready for public release, but here for those who want to try them out.

***I recommend and personally use the plugins Bioscan and Pioneer, which are NOT my work.  My plugins have options to add styling enhancements to those two plugins as well.  You can locate/Install them via EDMC's internal Plugin Browser.  Some of the styling changes should also work with all EDMC plugins, but this is untested***

# Navigator Suite for EDMC - test release, 30 October 2026

These are plugins for [EDMarketConnector](https://github.com/EDCD/EDMarketConnector)
(EDMC), the companion app for Elite Dangerous. They are built by Commander Thalinor
with Claude, ChatGPT and Gemini.

## Quick install (recommended)

1. Close EDMC.
2. Download all the plugins you plan on using, but only use **one** of the two Neutron Highway Navigator ZIPs:
3. In EDMC, go to File > Settings > Plugins > Open, which opens your plugins folder.
   Extract the ZIP(s) directly into that folder. Each plugin is its own folder
   (for example `plugins\Navigator_Interface\load.py`). There is no extra outer folder.
4. Start EDMC.  New installs require a restart to take effect, but dont worry if you copy
   plugins into the folder while EDMC is running, it wont break anything EDMC just needs to
   be restarted to take effect with the new updates.

Again, Install only one Neutron edition. If you switch editions, delete the other
edition's folder first. Your settings and routes are kept: they are stored in
EDMC's data folder, not in the plugin folders.  One has the same auto copy/paste feature 
EDCopilot* has had for years, and the other only has copy (you have to manually paste yourself).

*Note: FDev doesn't seem to care about the auto paste feature in EdCopilot, and I made sure mine didn't include 
anything that controls the ship itself (sorry no "start the frameshift drive after map paste,
as I was worried that may cross the line and fall under the "No macro ship flight ED TOS".)  The 
package without the AUTO tag has NO paste macro, so it's not even debatable with that build.

Anyway, both are basically the same, one just has less features than the other; make a decision pick one or none, 
and move on with your life.

Each suite ZIP contains:

| Plugin | Version | Panel |
| --- | --- | --- |
| (N) Interface (required) | 1.2.14 | Styles the whole window, Commander Profile |
| (N) Dashboard | 0.6.15 | Dashboard |
| (N) Cartography | 0.3.11 | Cartography |
| (N) Docking | 0.4.7 | Docking (appears automatically) |
| (N) Radio | 0.1.13 | Radio |
| (N) Voice | 0.2.5 | Voice |
| (N) Neutron Highway (Standard ZIP) | 1.4.7 | Neutron Highway |
| (N) Neutron Highway Auto (Auto ZIP) | 0.20.7 | Neutron Highway |

All suite plugins now start with **(N)** in EDMC, so their settings tabs and panels sit side by side.
Their folders start with `Navigator_` to match.

## Upgrading from a build before 30 October 2026

The plugin folders were renamed (for example `Systems_Navigator` is now `Navigator_Cartography`).
After extracting the new ZIPs, close EDMC and run the cleanup tool once: open `_Navigator_Cleanup`
in your plugins folder and double-click `Navigator_Cleanup.bat`. It is included in the suite ZIPs and
attached to every plugin release. It moves the old folders into `plugins\_Navigator_old_backup`,
which EDMC ignores, and copies anything they kept (such as Voice backups) into the new folders.
It deletes nothing. If you skip it, EDMC loads both the old and the new copies.
Your settings, routes, odometer, panel order and other choices are kept.

## Downloads

Each plugin has its own page (full README) and its own release (the ZIP to download).
All releases are listed on the [Releases page](https://github.com/Thalinor/EliteDangerousNavigator/releases).

| Plugin | Page | Download |
| --- | --- | --- |
| **Navigator Suite (all plugins)** | this page | [Suite 2026-10-30](https://github.com/Thalinor/EliteDangerousNavigator/releases/tag/navigator-suite-2026-10-30) (Standard or Auto bundle) |
| (N) Interface (required) | [README](Navigator_Interface) | [1.2.14](https://github.com/Thalinor/EliteDangerousNavigator/releases/tag/navigator-interface-v1.2.14) |
| (N) Dashboard | [README](Navigator_Dashboard) | [0.6.15](https://github.com/Thalinor/EliteDangerousNavigator/releases/tag/navigator-dashboard-v0.6.15) |
| (N) Cartography | [README](Navigator_Cartography) | [0.3.11](https://github.com/Thalinor/EliteDangerousNavigator/releases/tag/navigator-cartography-v0.3.11) |
| (N) Docking | [README](Navigator_Docking) | [0.4.7](https://github.com/Thalinor/EliteDangerousNavigator/releases/tag/navigator-docking-v0.4.7) |
| (N) Radio | [README](Navigator_Radio) | [0.1.13](https://github.com/Thalinor/EliteDangerousNavigator/releases/tag/navigator-radio-v0.1.13) |
| (N) Voice | [README](Navigator_Voice) | [0.2.5](https://github.com/Thalinor/EliteDangerousNavigator/releases/tag/navigator-voice-v0.2.5) |
| (N) Neutron Highway | [README](Navigator_Neutron_Highway) | [1.4.7](https://github.com/Thalinor/EliteDangerousNavigator/releases/tag/navigator-neutron-highway-v1.4.7) |
| (N) Neutron Highway Auto | [README](Navigator_Neutron_Highway_Auto) | [0.20.7](https://github.com/Thalinor/EliteDangerousNavigator/releases/tag/navigator-neutron-highway-auto-v0.20.7) |
| Folder cleanup tool (upgrading) | [README](_Navigator_Cleanup) | included in every release above |

Each release lists the SHA-256 checksum of its ZIP so you can verify your download.

## Individual plugins

Everything should be working correctly with Navigator Interface, Ship Computer, Docking Navigator,
Ship Radio, and Neutron Highway Navigator.  Let me know if you find bugs!

Note: Voice Navigator is a work in progress.  It does *NOT* require Voice Attack, HCS Voice Packs,
or anything else as it was designed to be a REPLACEMENT for those software packages.

Unfortunately, I don't have the resources to hire celebrities for voiceovers like HCS,
but feel free to use your own voice packs or windows defaults.  The assistant chatbot built into
voice navigator is very much still a work in progress and mostly untested at the time of this post,
however the voice to key press and TTS responses are working great on my end.  (11/27/26)

## Safety

- Every ZIP contains readable Python source and text files only. No compiled
  programs (.exe or .dll) are included. The folder cleanup tool is a short, readable
  PowerShell script (Navigator_Cleanup.ps1) started by a one-line .bat file.
- Ship Radio uses Windows' own media player and voice through a hidden PowerShell
  helper. Nothing is installed.
- Voice Navigator builds its small speech helper on your PC from the included
  source file (VoiceHost.cs), using the .NET compiler that comes with Windows.
  Some antivirus programs are cautious about newly built helpers; the source is
  included so anyone can read it.
- Nothing personal is shipped: no settings, playlists, API keys or journals.
- Microphone listening and online AI features are off until you turn them on.

## Development Acknowledgments
This suite was built by Commander Thalinor in collaboration with Claude (Anthropic), ChatGPT (OpenAI), and Gemini (Google) for AI-assisted code creation and debugging.


 
Tested in EDMC 6.1.2 with a real journal replay: no plugin errors. Live in-game
testing is the next step. Please report bugs with your EDMC log.



