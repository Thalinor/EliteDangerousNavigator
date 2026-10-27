Not fully ready for public release, but here for those who want to try them out.

***I recommend and personally use the plugins Bioscan and Pioneer, which are NOT my work.  My plugins have options to add styling enhancements to those two plugins as well.  You can locate/Install them via EDMC's internal Plugin Browser.  Some of the styling changes should also work with all EDMC plugins, but this is untested***

# Navigator Suite for EDMC - test release, 26 October 2026

These are plugins for [EDMarketConnector](https://github.com/EDCD/EDMarketConnector)
(EDMC), the companion app for Elite Dangerous. They are built by Commander Thalinor
with Claude, ChatGPT and Gemini.

## Quick install (recommended)

1. Close EDMC.
2. Download **one** of the two suite ZIPs:
   - **Navigator_Suite_2026-10-26_Standard_TEST.zip** includes the standard
     Neutron Highway Navigator, which copies route systems to your clipboard.
   - **Navigator_Suite_2026-10-26_Auto_TEST.zip** includes Neutron Highway
     Navigator Auto, which can also plot the route in the galaxy map for you.
3. In EDMC, go to File > Settings > Plugins > Open, which opens your plugins folder.
   Extract the ZIP directly into that folder. Each plugin is its own folder
   (for example `plugins\Navigator_Interface\load.py`). There is no extra outer folder.
4. Start EDMC.

Install only one Neutron edition. If you switch editions, delete the other
edition's folder first. Your settings and routes are kept: they are stored in
EDMC's data folder, not in the plugin folders.

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

## Individual plugins

Each plugin is also available as its own ZIP, which you extract the same way.
Navigator Interface is required by all of them.

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
