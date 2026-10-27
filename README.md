Not fully ready for public release, but here for those who want to try them out.

***I recommend and personally use the plugins Bioscan and Pioneer, which are NOT my work.  My plugins have options to add styling enhancements to those two plugins as well.  You can locate/Install them via EDMC's internal Plugin Browser.  Some of the styling changes should also work with all EDMC plugins, but this is untested***

# Navigator Suite for EDMC - test release, 26 October 2026

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
| Navigator Interface (required) | 1.2.11 | Styles the whole window, Commander Profile |
| Ship Computer | 0.6.11 | Dashboard |
| Systems Navigator | 0.3.8 | Cartography |
| Docking Navigator | 0.4.3 | Docking (appears automatically) |
| Ship Radio | 0.1.10 | Radio |
| Voice Navigator | 0.2.2 | Voice Navigator |
| Neutron Highway Navigator (Standard ZIP) | 1.4.4 | Neutron Highway Navigator |
| Neutron Highway Navigator Auto (Auto ZIP) | 0.20.4 | Neutron Highway Navigator |

## Downloads

Each plugin has its own page (full README) and its own release (the ZIP to download).
All releases are listed on the [Releases page](https://github.com/Thalinor/EliteDangerousNavigator/releases).

| Plugin | Page | Download |
| --- | --- | --- |
| **Navigator Suite (all plugins)** | this page | [Suite 2026-10-26](https://github.com/Thalinor/EliteDangerousNavigator/releases/tag/navigator-suite-2026-10-26) (Standard or Auto bundle) |
| Navigator Interface (required) | [README](Navigator_Interface) | [1.2.11](https://github.com/Thalinor/EliteDangerousNavigator/releases/tag/navigator-interface-v1.2.11) |
| Ship Computer | [README](Ship_Computer) | [0.6.11](https://github.com/Thalinor/EliteDangerousNavigator/releases/tag/ship-computer-v0.6.11) |
| Systems Navigator | [README](Systems_Navigator) | [0.3.8](https://github.com/Thalinor/EliteDangerousNavigator/releases/tag/systems-navigator-v0.3.8) |
| Docking Navigator | [README](Docking_Navigator) | [0.4.3](https://github.com/Thalinor/EliteDangerousNavigator/releases/tag/docking-navigator-v0.4.3) |
| Ship Radio | [README](Ship_Radio) | [0.1.10](https://github.com/Thalinor/EliteDangerousNavigator/releases/tag/ship-radio-v0.1.10) |
| Voice Navigator | [README](Voice_Navigator) | [0.2.2](https://github.com/Thalinor/EliteDangerousNavigator/releases/tag/voice-navigator-v0.2.2) |
| Neutron Highway Navigator | [README](Neutron_Highway_Navigator) | [1.4.4](https://github.com/Thalinor/EliteDangerousNavigator/releases/tag/neutron-highway-navigator-v1.4.4) |
| Neutron Highway Navigator Auto | [README](Neutron_Highway_Navigator_Auto) | [0.20.4](https://github.com/Thalinor/EliteDangerousNavigator/releases/tag/neutron-highway-navigator-auto-v0.20.4) |

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
  programs (.exe or .dll) are included.
- Ship Radio uses Windows' own media player and voice through a hidden PowerShell
  helper. Nothing is installed.
- Voice Navigator builds its small speech helper on your PC from the included
  source file (VoiceHost.cs), using the .NET compiler that comes with Windows.
  Some antivirus programs are cautious about newly built helpers; the source is
  included so anyone can read it.
- Nothing personal is shipped: no settings, playlists, API keys or journals.
- Microphone listening and online AI features are off until you turn them on.

Tested in EDMC 6.1.2 with a real journal replay: no plugin errors. Live in-game
testing is the next step. Please report bugs with your EDMC log.
