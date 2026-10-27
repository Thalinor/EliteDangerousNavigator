Ship Computer 0.6.11 — TEST BUILD — 26 OCTOBER 2026
Labels are only rewritten when their text changes, so journal updates and
the 30-second refresh no longer repaint unchanged lines.

Earlier:
Required companion: Navigator Interface 1.2.10 or newer.
Includes the per-plugin High Contrast Background preference, default off,
and all previously tested plugin-specific fixes.

Previous release notes are retained below.

Ship Computer 0.6.9 — 24 OCTOBER 2026
Required companion: Navigator Interface 1.2.9 or newer. Install it alongside
this plugin for shared EDMC layout fixes, popup styling and window memory.
This increment documents the suite dependency; plugin behavior is unchanged.

Release notes / current AI handoff: shared workspace AI_HANDOFF.md.
The older release history below is retained for reference.

TEST BUILD 0.6.8 - 2026-10-22
New in this build:
- Fixes the 0.6.7 release ZIP omitting recipes.json. The required synthesis
  database is now explicitly packaged, so the plugin can import on a clean install.
- Validated by extracting the release into an empty folder and running panel,
  settings, recipe-data and recovery tests against those extracted files.
- No feature changes from 0.6.7; saved data remains compatible.

Previous 0.6.7 improvements:
- Settings now offer one-time archived-journal import, portable Dashboard backup
  export/restore, and an optional one-time EDSM flight-log import.
- All online history recovery is explicitly requested. No startup downloads,
  periodic provider checks, automatic retries or new graphics timers.
- Journal imports merge matching commander history by event, including renamed
  ships without duplicating their jumps. Existing local records take precedence
  over imported copies. Normal non-recovery journal caching remains available.

Previous 0.6.6 improvements:
- Visible header is Dashboard / Dashboard (Hidden). The project, plugin folder,
  EDMC settings entry and saved data remain Ship Computer / Ship_Computer.

Previous 0.6.5 improvements:
- Reset Trip uses EDMC Normal Text colour as a deliberate visual exception.
  It remains clickable and keyboard accessible, with reset confirmation.

Previous 0.6.4 improvements:
- Trip now shows Jump Rate (Jumps/hr  |  Ly/hr), Trip, Trip Time, Systems,
  Distance, Times Landed, and a centered Reset Trip text link (Normal Text colour).
  Undo is removed. Reset still asks for confirmation and clears landings too.
- Times Landed counts your ship docking at stations, ports and fleet carriers,
  and player-controlled surface touchdowns. SRVs, taxis, recalled/autonomous
  ship touchdowns, logged-in-already-landed locations and replay duplicates
  are excluded. The saved counter starts when this build is first installed;
  earlier landings are not reconstructed. Manual/automatic trip resets clear it.
- All five tabs share the new seven-row height and keep their own scrolling.
- Recipe popups use EDMC colours for the native Windows 11 title bar and a
  slim scrollbar, with extra room between quantities and the scrollbar.
  Native caption colour support depends on Windows; other systems retain
  their native title bars. Theme changes are event driven, with no new timer.
- Recipe popup position and size are saved on close (including plugin exit),
  shared across recipes and restored next time. Windows monitor bounds keep
  a moved or disconnected monitor from stranding the popup off screen.

Previous 0.6.3 improvements:
- Recipe details open in a separate themed, resizable window with internal
  scrolling. Close and Escape dismiss it; the Ship panel never expands.
- Click any highlighted resource name to copy it to the clipboard. Each row
  shows inventory and the amount required per synthesis, with limiting
  ingredients marked. Unknown inventory remains Unknown.
- Only one recipe window is open at a time. It follows actual EDMC theme
  events, stays above its parent, and closes when the plugin stops.

Previous 0.6.2 improvements:
- Aligns the I / II / III header and synthesis counts to the right consistently
  in Exploration, Mining and Combat, including the narrow-window layout.

Previous 0.6.1 improvements:
- Synthesis has one I / II / III header and shared, aligned count columns.
  Counts have no parentheses; a dash means that grade does not apply.
  Unknown inventory is still ?, and known missing ingredients still show 0.
- Click a highlighted recipe name for ingredients for each grade in a popup,
  with inventory / required per synthesis and limiting ingredients.

Previous 0.6.0 improvements:
- Ship Time excludes time on foot and in taxis; On Foot remains a global total.
  The history cache rebuilds once in its background worker to correct old totals.
- ShipID is the identity; rename aliases are retained without creating a new ship.
  Different ShipIDs remain different ships. Sold ships retain their lifetime totals.
- History totals are scoped to the current/latest recorded commander. Switching
  commanders starts a background rebuild rather than combining their ShipIDs.
- Undo beside Trip Reset restores the previous trip and includes progress since
  that reset. Only the most recent reset can be undone; the snapshot is persisted.
- Click a highlighted synthesis recipe name for ingredient counts and its limiting
  material(s) in a separate popup; use Close or Escape to dismiss. Unknown inventory never implies zero stock.
- Cargo uses the suite separator: two spaces, vertical bar, two spaces.
- Odometer heading still rotates Ship / Type / All and remembers your choice.

==============================================================================
  Ship Computer
  EDMC plugin - version 0.6.11 - by Commander Thalinor
  Part of the Navigator plugin suite
==============================================================================


HISTORY RECOVERY AND BACKUP (0.6.7)
File > Settings > Ship Computer > History Recovery And Backup.
These actions take effect when clicked, independently of Settings Apply/Cancel.
All file reading and online downloads run in workers; EDMC remains usable.

Import Archived Journals
  Select the folder containing Journal*.log files (direct children). Only the
  current commander's records are imported. Originals are never moved or edited.
  Imported records are saved outside the plugin folder. The odometer is rebuilt
  from archived plus current journals; matching jumps are not added twice.
  Trip and Stopwatch are not changed. Distance, jumps, ship time, on-foot time,
  visited systems and rename aliases can be rebuilt only where journals record
  them. Missing sessions/events cannot be invented. LoadGame/Shutdown boundaries
  prevent known offline gaps being counted. Stale restored sessions start idle.
  Imported raw records are retained for future rebuilds; unchanged local files
  reuse their extracted-record cache. No online requests are involved.

Export Dashboard Backup / Restore Dashboard Backup
  Save the exported JSON somewhere that survives a PC rebuild. It includes the
  available journal history (current and previously imported), recovered EDSM
  visits, Trip, Stopwatch/laps and the Odometer scope choice. It contains personal
  travel history, but no API keys. Other appearance preferences and other plugins
  are not included. History missing before export cannot be recovered by a backup.
  Restoring merges history and replaces Trip/Stopwatch with the saved counters.
  The restored Stopwatch is paused, so time spent away from the PC is not added.
  A confirmation appears first. Current counters are saved in before_restore.json
  in EDMC application data / Ship_Computer, also readable by Restore Backup.
  A backup for another commander is refused while a different commander is active.
  Backup restore works even when no local journal folder exists yet.

Import EDSM History Once
  Enter the current commander's EDSM API key and an inclusive UTC date range.
  The default range is the current year; change From to include older history.
  The key is masked, used only for that download, and never written into backups,
  settings, recovery records or log messages. EDMC's separately configured keys
  are not accessed through unsupported plugin internals.
  Requests use EDSM's documented flight-log endpoint in weekly batches, spaced
  at least 10.1 seconds apart. Large histories can take a long time, but no work
  is done on the UI thread. Cancel saves completed batches; request failures
  leave existing history untouched and do not automatically retry.
  Repeating an import reconciles duplicate date/system/ship records.
  EDSM visits can extend the Odometer Systems count ONLY when overlapping local
  FSD jumps establish an unambiguous mapping to that ship. Unmapped visits remain
  saved for later reconciliation. We do not infer jumps, distance or session time
  from visit records: logins, missing uploads and carrier/taxi travel make that
  unsafe. This is partial recovery, not a reconstruction of missing raw journals.
  There is no Inara history downloader: Inara's documented API accepts travel
  uploads but does not expose a full travel-history read endpoint.

Data remains under EDMC application data / Ship_Computer. Updating the plugin
does not erase it. Cancel Current History Job stops an explicit recovery job;
the existing journal scanner retains its normal startup/event behavior.

Validation: real Windows/Tk settings/dialog and threaded recovery tests; raw
journal reconciliation, rename identity, commander filtering, duplicate imports,
unchanged-file cache reuse, portable backup roundtrip and paused Stopwatch;
mocked EDSM batching, rate spacing, cancellation and credential-safe errors.
No live account download was performed. Please test the provider import with
your own EDSM history; it is optional and never runs without clicking Import.

VISIBLE HEADER
Dashboard when expanded; Dashboard (Hidden) when collapsed. Settings still use the
project name Ship Computer, and the plugin folder stays Ship_Computer.
Version 0.6.0: click the highlighted Odometer heading to rotate through:
  1. This vessel: its name and ship model.
  2. All Your <Ship Type>s, for example All Your Mandalays.
  3. All Your Ships Combined.
Click again to return to the first view. Enter and Space also work while the
heading has keyboard focus. The choice is saved in EDMC config (StatsScope)
and survives restarts. The old same-type checkbox is removed; existing users
start in their previous ship/type view when upgrading.
Combined totals add ship distance, jumps and time; Systems is the union of
visited systems so a system visited in multiple ships is counted once.
On Foot remains the same commander-wide total in every view. Fleet carriers
are separate vessels and are excluded from All Your Ships Combined. Their
existing per-vessel and per-type views remain available while aboard.

An odometer, a stopwatch, a ship cargo list and lifetime stats for the ship
you are flying, in one small panel with five tabs.

0.5.2: An empty cargo hold leaves the list blank below its summary; the
redundant "Cargo hold empty" row is removed.

0.5.1: Odometer lists Systems after Time, with the commander-wide On Foot
figure last. Combined ship-type headings now say "All Your", for example
"All Your Caspian Explorers".

0.5.0: Adds unique Systems to Trip, between Trip and Distance. Each ship
FSD destination counts once until Reset (or the existing reset-on-undock
option); returning to a previously visited destination does not add one.
The counter survives EDMC restarts. Existing trips are reconstructed from
their saved jump count and last jump using the journals still available.
The starting system is not a Trip destination until you jump back to it.

Odometer removes the blank line below the centered ship heading, and adds
On Foot and Systems below Time. Systems includes logged locations and jump
destinations for that vessel. The same-type setting takes the union of its
ships' systems, so overlapping visits are not counted twice.

On Foot is a separate commander-wide total from Disembark, Embark and
on-foot login/location events, stopped by death, the main menu or shutdown.
It includes time outside both ships and SRVs; it excludes logged-out time.
As with the other lifetime totals, only available journals can be counted.
Ship Time now excludes on-foot and taxi segments. On Foot is tracked separately.
Suits are not treated as ships; totals are limited to the journals available.

All five tabs are one text line taller; Reset moves down with the new
Trip row. Cargo, Synthesis and Stopwatch retain internal scrolling.
The journal cache rebuilds automatically once for the new statistics.

0.4.3: Synthesis group selectors use the same horizontal gaps as the main
Trip / Odometer / Cargo / Synthesis / Stopwatch tabs, and remain centered.

0.4.2: Centers the Exploration / Mining / Combat selector strip. Every
synthesis now appears in exactly one group, with no duplicate entries:
 Exploration: FSD Injection, Limpets, Heatsinks, AFM Refill, Life Support.
 Mining: Mining Rig, SRV Refuel, SRV Repair, SRV Ammo Restock, Seismic Charge
         Munitions and Sub-surface Displacement Munitions.
 Combat: the remaining weapon ammunition, Chaff and Caustic Sinks.
All 30 recipes remain available; only their grouping has changed.

0.4.1: Odometer centers the ship name, followed by one blank text line.
Distance, Jumps and Time remain left-aligned. This uses the extra line
already available in every tab, without increasing the panel height.
The blank line is removed when there are no ship totals to display.

0.4.0: Synthesis now has Exploration (initial default), Mining and Combat
selectors inside the tab. The selected group is remembered. Exploration
lists FSD Injection first, followed by SRV Refuel, SRV Repair, SRV Ammo Restock,
Mining Rig, Limpets, Heatsinks, AFM Refill and Life Support. "SRV Restock" was
interpreted as SRV Repair because ammo restocking is listed separately.
Mining includes limpets, rigs, seismic/sub-surface ammunition and support
refills. Combat includes all weapon ammunition, including AX and Guardian,
plus defensive and support refills. There are 30 recipes / 74 grade variants.
Recipe names and available-use counts use EDMC's highlighted text colour.
Click recipe names for ingredients; counts are not links. Grade headings and
separators use normal text. Single-grade recipes show dashes in unused columns.
Long recipe names wrap within the scrolling list. Group selectors stay at
the top while the list scrolls, without changing the panel's height.

Trip now places Ly/hr immediately below Jumps/hr in the same value column.
All five tabs gain that extra line of height. Trip's content fills the whole
page, placing Reset against the bottom-right edge with no unused right margin.
Only the Cargo/Limpets summary is centered, with three spaces around its |
separator. Cargo item names and the empty-hold message remain left-aligned.

0.3.1: More space between tab names. Synthesis starts with FSD Injection,
showing independently available Basic (I), Standard (II) and Premium (III)
uses, e.g. "FSD Injection: 50 / 20 / 5". A question mark means the
material inventory has not arrived yet; zero means ingredients are missing.
The counts share ingredients, so they are not a combined spending plan.
The three recipes were verified against actual Synthesis journal entries.
Synthesis keeps the common tab height and scrolls internally on overflow.

0.3.0: Cargo total and limpet count now share one left-aligned label,
separated by " | ". Adds a Synthesis tab beside Cargo. No recipes are selected
in this build; material snapshots and independent recipe-use calculations are
ready for the next step. Material counts come from EDMC's journal state.
The five tab names fit inside the existing panel width.

0.2.1: Adds a right-aligned Limpets count opposite the cargo total.

0.2.0: Adds Cargo between Odometer and Stopwatch, with commodity names,
quantities and used/total cargo capacity. The list updates from EDMC journal
callbacks; there are no market-price lookups or network requests. It uses
the game's localized names when available. SRV cargo does not overwrite
the ship's manifest. Cargo Manifest was a behavioral reference only; its
code and commodity data are not included.

All five tabs share Trip's height. Cargo, Synthesis, Stopwatch and Odometer scroll
when their content exceeds it. The stopwatch digits use their own larger
font fitted to roughly 90 percent of the clock box's inner height, with
width checked too. The panel does not grow to accommodate the larger digits.

0.1.6: Stopwatch laps now follow EDMC's normal text colour, background and
font, including dark/transparent mode and theme changes. Embedded lap rows
are explicitly registered with EDMC's theme system. Theme repairs run on
layout/theme events rather than delayed startup refreshes.


INSTALL
-------
1. Close EDMC.
2. Extract this zip into EDMC's plugins folder:
       %LOCALAPPDATA%\EDMarketConnector\plugins
   You should end up with ...\plugins\Ship_Computer\load.py
3. Start EDMC.


THE PANEL
---------
              Ship Computer                          🔼
             Trip   Odometer   Cargo   Synthesis   Stopwatch
             ‾‾‾‾

Tap a tab name to switch. The underline shows the open tab, and the panel
remembers it. The 🔼 / 🔽 button folds the panel down to its title, like
other plugins' collapse buttons.


TRIP
----
 Jump Rate   Trip averages: jumps per hour | light years per hour.
 Trip Time   How long the trip has been running. It only counts while you
             are logged into the game - not at the main menu or while the
             game or EDMC is closed.
 Trip        Jumps since the trip was last reset.
 Systems     Unique ship-jump destinations since Reset.
 Distance    Light years since the trip was last reset.
 Reset       Starts a new trip (you are asked first). It sits in the
             bottom-right corner. Your lifetime totals are on the Odometer
             tab.

Jump Rate is the trip's jumps divided by its Trip Time, like a car's trip
computer, so it shows "–" until the trip has a jump and a minute of time.
In Settings you can have the trip reset itself every time you undock.
Only your ship's own jumps count: fleet carrier jumps and Apex taxi jumps
do not. A jump is never counted twice, even if EDMC restarts and replays
the journal.


STOPWATCH
---------
 Start / Stop   Starts or pauses the clock.
 Lap            Records a lap while running.
 Reset          Clears the clock and all laps (you are asked first).

The newest laps are listed under the buttons. Each shows the lap time, the
total time at that lap, and the jumps and distance flown during the lap.
The time is shown on the left, in a box the same size as the buttons,
and laps appear underneath as you record them, newest first. The tab
keeps the same height as Trip and Odometer; when the laps fill it, scroll
them with the mouse wheel or a finger drag.


CARGO
-----
Lists the current ship's cargo and quantities, with a used/capacity total.
An empty hold leaves the list blank below the summary. Before EDMC provides a snapshot,
the tab says it is waiting for ship cargo data. Scroll with the mouse wheel
or drag the list when it extends beyond the fixed tab height. Long item
names wrap inside the list rather than making EDMC wider.
The stopwatch keeps running if you close and reopen EDMC.


ODOMETER
--------
Lifetime figures for the vessel you are in, read from your game journals:
 Distance   Total jump distance.
 Jumps      Number of jumps.
 Time       Time spent in it while logged in (main-menu time is not
            counted).
 On Foot    Commander-wide time on foot, independent of ship/type selection.
 Systems    Unique systems visited in the vessel, or across its ship type.

The first time, Ship Computer reads all your journal files in the background
- EDMC keeps working, and the Odometer tab shows progress. After that it
only reads new or changed files, and adds your jumps live as you fly.

Ships are told apart by the game's own ship ID. Click the Odometer heading
to choose this vessel, all your ships of its type, or all your ships combined.
Grouped headings do not display a vessel count.

Fleet carriers count as their own vessel: while you are docked aboard one,
its jumps and the time spent aboard are added to the carrier, not to your
ship, and the Odometer tab shows the carrier.


SETTINGS
--------
Settings > Ship Computer:
 Trip tab: reset the trip automatically every time you undock
              Off by default. Each undock starts a new trip, without
              asking.
 Re-read all journals
              Reads every journal again from scratch.


DATA
----
Kept in %LOCALAPPDATA%\EDMarketConnector\Ship_Computer:
 odometer.json     The trip (time, jumps, unique systems, distance).
 stopwatch.json    The stopwatch and its laps.
 stats_cache.json  What was read from each journal file, so it isn't read
                   again. Safe to delete; it is rebuilt.


ABOUT AND LICENSE
-----------------
Ship Computer is part of the Navigator plugin suite, coded collaboratively
with Claude, ChatGPT and Gemini by Commander Thalinor.

Elite Dangerous Commander Name: Thalinor
eMail: thalinor @ gmail.com

You can use this plugin freely for your own personal, non-commercial use.
You can distribute it freely as long as the code has not been modified and
you do not claim it's your own work. You may NOT sell this plugin, use this
plugin for commercial use, or use its code in your projects without prior
authorization.

Synthesis requirement data was checked against game journal events and:
 https://inara.cz/elite/synthesis/
Material identifiers/categories were verified using EDCD's FDevIDs registry:
 https://github.com/EDCD/FDevIDs/blob/master/material.csv
New Titan material identifiers are documented at:
 https://github.com/Elite-Dangerous-Almanac/Almanac-Core/blob/main/data/materials/SOURCES.md
No reference plugin code or visuals are included. Counts are independent
possible synthesis uses, sharing the same material inventory, not additive
budgets. Limpet synthesis counts uses (up to four limpets per use), rather
than individual limpets. No network requests are made by this plugin.

The odometer's jump rate and speed are inspired by the EDMCJumpSpeed
plugin by inorton.

Human + AI = Future


High Contrast Backgrounds (25 October 2026)
High Contrast Background is available on this plugin's EDMC settings page
and defaults off. Navigator Interface applies it and can force it on for all
main plugin panels. Turning off the force option restores individual choices.
