Docking Navigator 0.4.3 — TEST BUILD — 25 OCTOBER 2026
Required companion: Navigator Interface 1.2.10 or newer.
Includes the per-plugin High Contrast Background preference, default off,
and all previously tested plugin-specific fixes.

Previous release notes are retained below.

Docking Navigator 0.4.2 — 24 OCTOBER 2026
Required companion: Navigator Interface 1.2.9 or newer. Install it alongside
this plugin for shared EDMC layout fixes, popup styling and window memory.
This increment documents the suite dependency; plugin behavior is unchanged.

Release notes / current AI handoff: shared workspace AI_HANDOFF.md.
The older release history below is retained for reference.

TEST BUILD 0.4.1 - 2026-10-24
New in 0.4.1:
- Independent Settings: Hide Docking when not docking (show near stations),
  and Minimize other panels while docking. Choose either, both or neither.
- Existing combined choice supplies both defaults until saved. Turning off
  minimization restores only panels Docking collapsed.

Earlier in 0.4.0:
- Auto-hiding removes Docking's EDMC wrapper and separator as well as its content.
- Camera rotation and zoom are remembered separately for each supported layout.
  Drag release and mouse-wheel actions save; Reset View resets that layout.
- Station name is prominent and uses Normal Text. Existing automatic panel
  collapse/restore and 2D/3D theme behavior are preserved.

The game journal does not supply a remaining docking-clearance countdown or your
live orientation relative to the mailslot. This build does not invent either:
use the game's clearance timer, and treat the drawing as a reference diagram.

DOCKING NAVIGATOR 0.4.1
=======================
Navigator suite plugin by Commander Thalinor, created with ChatGPT (Tachikoma).
This is a separate project from Navigator Interface.

0.4.0: The visible title is now Docking. Automatic show/hide is retained;
there is no manual collapse button or (Hidden) suffix. Settings and folder
retain the Docking Navigator / Docking_Navigator project identity.

0.3.0: STATION MODE (on by default). The panel is hidden until you enter a
station's no-fire zone. It then appears and collapses the other plugins'
expanded panels by pressing their own collapse buttons (the standard 🔼/🔽
button used by BioScan, Pioneer, Neutron Highway Navigator and others),
remembering exactly which ones it collapsed. When you dock it re-opens only
those panels and hides itself again. Panels you were already keeping
collapsed stay collapsed, and any panel you re-open yourself during docking
is left alone. The same restore happens if you leave the no-fire zone
without docking, enter supercruise, jump, die, log out or close EDMC, so
panels are never left collapsed. A cancelled or timed-out request inside
the zone keeps the panel up so you can request again. A docking request is
also a backup trigger, in case EDMC was started inside the zone. Old events
replayed while EDMC catches up are ignored. In Settings > Docking Navigator,
disable Hide Docking when not docking for an always-visible panel. Minimize
other panels while docking is now an independent option; choose either,
both or neither. Leaving docking restores only panels Docking minimized.

0.2.1: The Docking Navigator title uses EDMC's Normal text colour. Selected
2D/3D and stage controls use Highlighted text; other controls use Normal text.
Dark and transparent themes follow the user's dark_text/dark_highlight
settings. The default theme follows EDMC's system palette. Theme colour
changes are part of the render signature, including correcting EDMC's
generic clickable-label styling when it is reapplied.

INSTALL
-------
Close EDMC. Extract Docking_Navigator into EDMC's plugins folder, then restart.
Disable the old LandingPad and docking_denied_reason folders by adding
.disabled to their folder names while EDMC is closed to avoid duplicate
panels. Keep them as backups. If you tried our earlier unreleased
Navigator_Docking folder, disable that too; the correct folder is now
Docking_Navigator. This plugin does not import any of those old plugins.

Its panel header is Docking; its Settings tab is Docking Navigator.
Navigator Interface is required for shared EDMC layout and popup services.
EDMC supplies tkinter; the renderer uses Python's standard library. No pip
installs, network services, Qt, Pillow or external overlay are required.

ORIGINAL GRAPHICS AND PANEL CONTROLS
-----------------------------------
The transparent wireframe renderer and station meshes are newly drawn for
this project. No visual assets, sprites, screenshots, canvas renderer or
overlay renderer from LandingPad are used. Only credited pad-index reference
data and carrier pad coordinates remain as layout facts.

2D / 3D: always available beside the main Docking header. Your
choice saves immediately and also appears in settings. 3D is the default.

Entrance: orange mailslot marker and red/green navigation lights on original
Coriolis, Orbis and Ocellus/Bernal schematic wireframes. Other supported
starport types use an explicitly generic station schematic. Carriers show
an open landing deck, not a made-up mailslot.

Pad: after clearance, select Pad to see the assigned bay highlighted in
orange. Starports use a 3D cutaway reference or a 2D depth-ring reference;
carriers use deck references with the assigned pad shaded. The prominent
pad number remains visible above the diagram. Ring/depth placement is
schematic, not measured in metres and not an exact game mesh.

Drag the 3D graphic to orbit. Use the mouse wheel to zoom. Reset view restores
the reference camera. The 2D/3D and Entrance/Pad controls are also keyboard
focusable and activate with Enter or Space.

The PNG renderer uses continuous alpha coverage to smooth edges. There is
no dithering, animation loop, opaque image background or pixel-art sprite.
EDMC's Windows transparent mode still uses its native colour-key window
compositing; the operating system determines the final edge appearance
against the game. Transparent graphics do not add a separate overlay window.

IMPORTANT: REFERENCE VIEW, NOT LIVE SHIP-RELATIVE GUIDANCE
--------------------------------------------------------
The journal supplies station type, docking result, denial reason and pad
number. The documented journal/Status interface does not supply the station
rotation and ship-to-station 3D pose needed to calculate the mailslot's live
bearing. Planetary latitude/longitude/heading and system StarPos do not
provide that missing pose. There is no reliable journal crossing-the-mailslot
event to switch views on entry.

Therefore the camera is user controlled and every diagram is labelled as a
reference. No guessed ship position or rotating-station telemetry is shown.
Entrance appears when a request identifies a supported station. Select Pad
when you want the interior reference. An optional setting can switch to Pad
when DockingGranted arrives; this means clearance, NOT detection of entering
the station. That option is OFF by default.

Primary telemetry reference:
https://hosting.zaonce.net/community/journal/v32/Journal_Manual-v32.pdf
Sections DockingRequested / DockingGranted / Status File.

DOCKING MESSAGES AND SETTINGS
-----------------------------
Denied requests explain occupied pads, ship size, hostility, offences, range,
active fighter, access restrictions and imminent carrier jumps, with useful
next steps. Unknown reasons retain the game's code/text. The display defaults
to 15 seconds (5-60 in settings); docking-complete/cancelled messages last
5 seconds. A pending request clears after 60 seconds without a result.
New clearance cancels an older denial's timer. Docking, cancellation, timeout,
jumps, supercruise, logout and reset events remove stale guidance. Between
stations the panel is hidden (station mode, see 0.3.0 above).

Settings > Docking Navigator includes diagram visibility, next-step text,
green-side / 180-degree carrier orientation, initial 2D/3D mode, optional
clearance-based pad switching, diagram size (180-480 px) and message duration.
Press OK to apply. The settings Preview demonstrates all four layout types
without changing live docking state or saved settings; it also works before
you fly. Preview controls are independent of the live panel.

Supported pad references: 45-pad starports; 16-pad fleet carriers and known
colonisation ships; 32-pad squadron carriers identified by the upstream
four-character station-name convention. Unknown layouts still display the
assigned pad number. Invalid pad indices never wrap to a different pad.
Outposts and surface settlements do not get invented pad maps.

TESTING / FIRST LIVE BUILD
--------------------------
Windows/Tk integration tests cover the real controls, persistent 2D/3D choice,
Entrance/Pad switching, camera drag, optional clearance transition, all four
layout variants, invalid/unknown data, message timers, theme reapplication,
exact transparent background key, resizing, preferences, independent preview
and clean shutdown. PNG tests verify transparent backgrounds and many levels
of antialiased edge coverage. The rendered models were visually inspected.

Replay of the supplied October journals exercised 11 actual request/grant/
docked sequences. Those files contained no denials; denial reasons and
carrier layouts were tested with explicit fixtures. This new plugin still
needs its first live EDMC/in-game check.

There is no periodic refresh or watchdog timer. Only transient messages use
single-use expiry timers. The plugin does not move/resize EDMC, send docking
requests, inject keys, automate flight, read game memory or upload journal data.

CREDITS / LICENSE
-----------------
Original renderer, wireframe models, UI and integration: Commander Thalinor
and contributors, developed collaboratively with ChatGPT (Tachikoma).
Pad-index data / carrier coordinate reference: Bernd Gollesch, LandingPad,
https://github.com/bgol/LandingPad (GPL-2.0-or-later).
Denial-code reference and feature inspiration: Inutt and contributors,
https://gitlab.com/inutt/edmc-docking-denied-reason (GPL-3.0-or-later).
Combined source is GPL-3.0-or-later. See NOTICE.txt and LICENSE.

Human + AI = Future


High Contrast Backgrounds (25 October 2026)
High Contrast Background is available on this plugin's EDMC settings page
and defaults off. Navigator Interface applies it and can force it on for all
main plugin panels. Turning off the force option restores individual choices.
