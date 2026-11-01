Not fully ready for public release, but here for those who want to try them out.

***I recommend and personally use the plugins Bioscan and Pioneer, which are NOT my work.  My plugins have options to add styling enhancements to those two plugins as well.  You can locate/Install them via EDMC's internal Plugin Browser.  Some of the styling changes should also work with all EDMC plugins, but this is untested***

# Navigator Suite for EDMC - test release, 1 November 2026

These are plugins for [EDMarketConnector](https://github.com/EDCD/EDMarketConnector)
(EDMC), the companion app for Elite Dangerous. They are built by Commander Thalinor
with Claude, ChatGPT and Gemini.

**Humans + AI = Future.** This project was made in open collaboration with AI, and we say so proudly.

## Quick install (recommended)

1. Close EDMC.
2. Download the suite ZIP (everything in one), or just the plugins you plan on using.
   (N) Interface is required by all the others.
3. In EDMC, go to File > Settings > Plugins > Open, which opens your plugins folder.
   Extract the ZIP(s) directly into that folder. Each plugin is its own folder
   (for example `plugins\Navigator_Interface\load.py`). There is no extra outer folder.
4. Start EDMC.  New installs require a restart to take effect, but dont worry if you copy
   plugins into the folder while EDMC is running, it wont break anything EDMC just needs to
   be restarted to take effect with the new updates.

Your settings and routes are kept: they are stored in EDMC's data folder, not in the plugin folders.

*Note on the galaxy map: (N) Interface can optionally paste a system name into the galaxy map for you (the A button
in (N) Navigation), like the auto copy/paste feature EDCopilot has had for years. It only ever drives the galaxy map
MENU: open the map, click the search box, paste the name, press enter. It never targets, honks, starts the frame shift
drive or controls the ship, because that could cross the line into the "no macro ship flight" part of the Elite
Dangerous terms. Leave the A button off and (N) Navigation only copies names to your clipboard, so you paste them yourself.

The suite ZIP contains:

| Plugin | Version | Panel |
| --- | --- | --- |
| (N) Interface (required) | 1.2.59 | Styles the whole window, Commander Profile |
| (N) Navigation | 0.43.6 | Navigation (routes, missions, expedition, rescue, shortcut bar) |
| (N) Dashboard | 0.6.19 | Dashboard |
| (N) Cartography | 0.3.23 | Cartography |
| (N) Docking | 0.4.8 | Docking (appears automatically) |
| (N) Radio | 0.1.15 | Radio |
| (N) Tools | 0.2.1 | Tools (notes and calculator) |
| (N) Voice | 0.2.8 | Voice |

All suite plugins start with **(N)** in EDMC, so their settings tabs and panels sit side by side.
Their folders start with `Navigator_` to match. (N) Navigation replaces the old Neutron Highway Navigator and its Auto edition.

## Upgrading from an earlier build

The plugin folders were renamed (for example `Systems_Navigator` is now `Navigator_Cartography`, and the Neutron Highway
plugins are now `Navigator_Navigation`). After extracting the new ZIPs, close EDMC and run the cleanup tool once: open
`_Navigator_Cleanup` in your plugins folder and double-click `Navigator_Cleanup.bat`. It is included in the suite ZIP and
attached to every plugin release. It moves the old folders into `plugins\_Navigator_old_backup`, which EDMC ignores, and
copies anything they kept (such as Voice backups) into the new folders. It deletes nothing. If you skip it, EDMC loads both
the old and the new copies. Your settings, routes, odometer, panel order and other choices are kept.

## Downloads

Each plugin has its own page (full README) and its own release (the ZIP to download).
All releases are listed on the [Releases page](https://github.com/Thalinor/EliteDangerousNavigator/releases).

| Plugin | Page | Download |
| --- | --- | --- |
| **Navigator Suite (all plugins)** | this page | [Suite 2026-10-31](https://github.com/Thalinor/EliteDangerousNavigator/releases/tag/navigator-suite-2026-10-31) |
| (N) Interface (required) | [README](Navigator_Interface) | [1.2.59](https://github.com/Thalinor/EliteDangerousNavigator/releases/tag/navigator-interface-v1.2.59) |
| (N) Navigation | [README](Navigator_Navigation) | [0.43.6](https://github.com/Thalinor/EliteDangerousNavigator/releases/tag/navigator-navigation-v0.43.6) |
| (N) Dashboard | [README](Navigator_Dashboard) | [0.6.19](https://github.com/Thalinor/EliteDangerousNavigator/releases/tag/navigator-dashboard-v0.6.19) |
| (N) Cartography | [README](Navigator_Cartography) | [0.3.23](https://github.com/Thalinor/EliteDangerousNavigator/releases/tag/navigator-cartography-v0.3.23) |
| (N) Docking | [README](Navigator_Docking) | [0.4.8](https://github.com/Thalinor/EliteDangerousNavigator/releases/tag/navigator-docking-v0.4.8) |
| (N) Radio | [README](Navigator_Radio) | [0.1.15](https://github.com/Thalinor/EliteDangerousNavigator/releases/tag/navigator-radio-v0.1.15) |
| (N) Tools | [README](Navigator_Tools) | [0.2.1](https://github.com/Thalinor/EliteDangerousNavigator/releases/tag/navigator-tools-v0.2.1) |
| (N) Voice | [README](Navigator_Voice) | [0.2.8](https://github.com/Thalinor/EliteDangerousNavigator/releases/tag/navigator-voice-v0.2.8) |
| Folder cleanup tool (upgrading) | [README](_Navigator_Cleanup) | included in every release above |

Each release lists the SHA-256 checksum of its ZIP so you can verify your download.

## Individual plugins

Everything should be working correctly together with (N) Interface.  Let me know if you find bugs!

Note: (N) Voice is a work in progress.  It does *NOT* require Voice Attack, HCS Voice Packs,
or anything else as it was designed to be a REPLACEMENT for those software packages.

Unfortunately, I don't have the resources to hire celebrities for voiceovers like HCS,
but feel free to use your own voice packs or windows defaults.  The assistant chatbot built into
(N) Voice is very much still a work in progress and mostly untested at the time of this post,
however the voice to key press and TTS responses are working great on my end.

## Safety

- Every ZIP contains readable Python source and text files only. No compiled
  programs (.exe or .dll) are included. The folder cleanup tool is a short, readable
  PowerShell script (Navigator_Cleanup.ps1) started by a one-line .bat file.
- (N) Radio uses Windows' own media player and voice through a hidden PowerShell
  helper. Nothing is installed.
- (N) Voice builds its small speech helper on your PC from the included
  source file (VoiceHost.cs), using the .NET compiler that comes with Windows.
  Some antivirus programs are cautious about newly built helpers; the source is
  included so anyone can read it.
- Nothing personal is shipped: no settings, playlists, API keys or journals.
- Microphone listening and online AI features are off until you turn them on.
- No account with any third-party site is needed.

## License

Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). Licensed under the
[GNU General Public License v3.0 or later](LICENSE) (GPL-3.0-or-later). The source in this repository is exactly what
the release ZIPs contain. You are free to use, study, change and share it under that license; please keep the copyright
and credit notices. See [CREDITS.txt](CREDITS.txt) and each plugin's `NOTICE.txt` / `CREDITS.txt` for acknowledgements.

## Development Acknowledgments

**Humans + AI = Future.** This suite was built by Commander Thalinor in collaboration with Claude (Anthropic),
ChatGPT (OpenAI), and Gemini (Google) for AI-assisted code creation and debugging. The AI systems are credited here
proudly and on purpose; the copyright is held by the human author.

Tested in EDMC 6.1.2 with a real journal replay: no plugin errors. Live in-game
testing is the next step. Please report bugs with your EDMC log.
