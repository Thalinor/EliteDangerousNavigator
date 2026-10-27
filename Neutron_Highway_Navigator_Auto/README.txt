Neutron Highway Navigator Auto 0.20.4 — TEST BUILD — 26 OCTOBER 2026
Smoother panel: the panel and its status file now update only when your
location, ship or route actually changes, and the progress bar and icons
are only repainted when they look different. Less disk writing and redrawing.

Earlier:
Required companion: Navigator Interface 1.2.10 or newer.
Includes the per-plugin High Contrast Background preference, default off,
and all previously tested plugin-specific fixes.

Previous release notes are retained below.

Neutron Highway Navigator Auto 0.20.2 — 24 OCTOBER 2026
Required companion: Navigator Interface 1.2.9 or newer. Install it alongside
this plugin for shared EDMC layout fixes, popup styling and window memory.
This increment documents the suite dependency; plugin behavior is unchanged.

Release notes / current AI handoff: shared workspace AI_HANDOFF.md.
The older release history below is retained for reference.

NEUTRON HIGHWAY NAVIGATOR AUTO 0.20.1 - TEST BUILD - 2026-10-23
Part of the Neutron Highway Navigator family - by Commander Thalinor

CHOOSE ONE EDITION
There are two editions. Install ONE of them, not both:
- Neutron Highway Navigator: route planning, progress and clipboard copying.
  It never touches the game's controls.
- Neutron Highway Navigator Auto (this one): everything above, plus galaxy-map
  helpers that enter the system name and plot the course for you.
Both show the same panel header, Neutron Highway Navigator. Running both at
once gives two route panels with separate progress, which is confusing.

UPDATING FROM COCKPIT COMPANION
This edition replaces the earlier Cockpit Companion test builds. Close EDMC,
delete the old plugins\EDMC_Cockpit_Companion folder, then install this one.
On its first start it copies your route, settings and calibration from the
old CockpitCompanion data folder (that folder is left unchanged).

EXOMASTERY, FSD INJECTIONS AND REALISTIC JUMP RANGE (0.20.0)
- Route Type "Exomastery": Spansh's biology route. It uses the same four settings
  as Road to Riches (the value is now called Min Value), avoids Thargoid systems,
  and widens its own search in sparse space. The Scan line shows the nearest
  body and its species, most valuable first:
    Next scan: A 2 b: Frutexa Flammasis 10.3M, Concha Aureolas 7.8M, +1 more
  Values are base values, before any first-footfall bonus.
- Galaxy Plotter: a tick box "Use FSD injections when needed (premium)". It is
  OFF every time the window opens, because injections are for the far reaches.
  Under it, the plugin says how many premium injections your materials make and
  which material runs out first. The route summary counts the injections and
  warns if you can't make enough. The panel says "Inject here: synthesise a
  premium FSD injection before your next jump" at the right stops. Please check
  in game that the stop it marks is the right one.
  If Spansh can't finish a galaxy route in time, the plugin now says so instead
  of loading a route that stops short.
- Realistic jump range: routes are now planned with your range on a FULL tank
  plus the cargo and limpets aboard now, worked out from your FSD. The game's own
  figure is the best case, with an almost empty tank. Legs planned with it could
  be a few ly too long once you'd scooped, and Elite then added an extra jump.
  The plot window shows both, for example:
    84.11 ly (full tank; best case 91.47)
  If your FSD isn't in the plugin's table, it uses the game's figure as before.
- Plot New Route fills in the End System from Elite (version 0.20.1): the end of the route
  you have plotted in the game, or else the system you have targeted (whole systems only,
  never a station, body or carrier). It's never the system you are in or a system on the
  route already loaded. With nothing targeted, the last End System is kept. You can still
  type any End System.

PROGRESS BAR AND SETTINGS PAGE (0.19.0; 0.19.1 fixes the Settings tab not appearing)
- A thin progress bar sits under the Jumps line and fills as you travel.
  It also shows your route state: green while On Route; red, with "Off Route"
  written in the middle, when you are off it; and full with "Arrived" at the
  end. While the bar is shown, the lamp on the Jumps line hides; any time
  estimate stays on that line.
- The plugin now has its own page in EDMC's Settings window
  (File > Settings > this plugin's tab). It holds:
    Show progress bar (default on). Untick it to get the lamp back.
    Force EDMC theme colors for plugin icons (default off). On Route then
      uses your Highlighted Text colour and Off Route your Normal Text colour,
      for the lamp and the bar, instead of green and red, and the bar's empty
      part is outlined in Normal Text instead of filled black. The plugin
      then uses only your two EDMC theme colours.
    Auto-Route Delay, Load Keybindings, Open Data Folder and About (moved here from the gear menu).
  The gear menu keeps what you use in flight: plotting, loading and
  cancelling routes, Fuel Warnings, the jet-cone toggle and calibration.
- The Off Route lamp is now red (it was amber).
- Time estimate: until the plugin has learned your pace, it assumes a set number of
  minutes per jump (Settings page, default 2). Gaps between waypoints longer than three
  times that (at least 6 minutes) count as a break, so idle time doesn't slow the
  estimate down.
- Fix (0.19.2): when the game routed a leg through an extra neutron and you supercharged
  there, AUTO-ROUTE plotted Next again. Next was already the plotted destination, and
  plotting it again makes Elite REMOVE the route. Now it sees the route already ends there
  and says "Route still set: 1 jump to <system>. Just jump." (0.19.3: clearer wording, and it
  only skips when your current system is on the game's route.) The extra neutron is
  Elite's own stopover, not a route waypoint, so Neutron/Next don't move on there.

GALAXY PLOTTER (0.18.0)
A third Route Type: Spansh's Galaxy Plotter, an exact jump-by-jump route that
plans your fuel. You only enter the End System. Everything else is read from
the game:
- your FSD (engineered values included) and any Guardian FSD Booster, checked
  against the game's own jump range before plotting;
- your fuel tank, cargo and fuel scoop;
- whether your FSD is already supercharged right now.
Secondary stars are always avoided, and supercharges are always used. The fuel
it keeps back follows Gear > Fuel Warnings (Normal keeps one jump of fuel,
Cautious two). One optional choice, Routing, defaults to Optimistic (fastest).
The other choices are Pessimistic, Guided, Fewest refuels, and Fewest refuels
and jumps.
The panel keeps the jumps that matter as waypoints (neutron boosts, refuel
stops and the destination); the game plots the plain jumps in between. The
first line reads "Waypoint:", and the line below warns you:
  Refuel stop next: scoop at <system>.
  Refuel here: scoop before your next jump.
The uncharted space bridge works here too. FSD injections are not used yet.
FSD stats come from coriolis-data (EDCD); the game data is (c) Frontier
Developments plc.

ROAD TO RICHES AND FUEL WARNINGS (0.17.0, dropdown tidied in 0.17.1)
Plot New Route now has a Route Type dropdown at the top:
- Neutron Highway: the fast neutron route, as before.
- Road to Riches: Spansh's list of systems with valuable bodies to scan
  (Earth-like, water and ammonia worlds, terraformable planets and more).
  Leave End System blank for riches near you, or enter a destination for
  riches along the way there. Its four settings have sensible defaults:
  Search Radius 25 ly, Max Systems 25, Min Body Value 500,000 cr and
  Max Distance 50,000 ls (no long supercruise trips). Out in the black,
  where few systems are charted, the plugin widens the search by itself,
  up to 200 ly, until it finds enough systems.
  Body values include mapping when your ship has a Detailed Surface
  Scanner, which the plugin checks for you.
  On a Road to Riches the first line reads "Stop:", and a Scan line lists
  the bodies to scan, nearest to the arrival star first:
    Next scan: A 1 ELW 3.2M, 2 WW (T) 950k
  It changes to "Scan here:" when you arrive. (T) means terraformable.
  The uncharted space bridge works for Road to Riches too.
  AUTO-ROUTE only plots after a neutron supercharge, so on a Road to
  Riches press the compass beside Next when you finish scanning.

Fuel warnings watch your fuel after every jump. The game records your fuel,
your ship's fuel scoop and the star class of every jump in a plotted route,
so the plugin warns you before fuel runs short, for example:
  Fuel check: about 3 jumps of fuel. Top up at <star> (2 jumps ahead).
  Fuel check: top up here (K star). ...
It tells you if no scoopable (KGBFOAM) star is left on the plotted leg, or
if no fuel scoop is fitted. Choose how early it warns in Gear > Fuel
Warnings: Off, Relaxed, Normal (default) or Cautious. It needs one jump of
fuel use first to learn your ship's consumption.

UNCHARTED SPACE BRIDGE (0.16.0)
Spansh can only plot from systems someone has reported to it. Far out in the
black, Plot New Route used to stop with "Could not find starting system".
Now, if your Start System is the system you are in, the plugin reads your exact
coordinates from the game journal (the game writes them even in unexplored
systems) and asks Spansh for known neutron stars near you. It keeps only
neutrons that are the system's main star, so you are never sent to a companion
neutron thousands of light seconds from the arrival point. Out of the nearest
dozen, it picks the one that best gets you on your way, not simply the closest.
The route then starts: your system -> that neutron -> the Neutron Highway.
The window says "Uncharted space, Commander..." and names the bridge system.
If no known neutron is in reach, it starts from the nearest system Spansh knows.
Fly the first leg with the game's own route plotter, which reaches any system.

WHY I MADE IT
Neutron Highway Navigator is the regular route-planning and clipboard plugin.
Neutron Highway Navigator Auto adds accessibility helpers for pasting system
names and reducing repeated navigation-menu input.

I made these helpers to make Elite Dangerous more playable when a physical
keyboard is difficult to use or not available:
- Handheld PCs such as the ROG Ally, or a Steam Deck running Windows, often have
  no physical keyboard attached. An on-screen keyboard can cover more than half
  of the small display, obscure the search field and make long system names
  awkward to enter while holding the device and operating its controls.
- VR users cannot readily see their physical keyboard with a headset on, and
  taking the headset off to type every waypoint interrupts play.
- People with disabilities, limited dexterity or difficulty reaching a keyboard
  may find repeated text entry and precise menu clicks unnecessarily demanding.

The purpose is to reduce those input barriers, not to play the game for you or
bypass its gameplay. You remain the pilot and stay in control of your ship.

NOT AN AUTOPILOT - IT WILL NOT FLY YOUR SHIP
This program does not steer, align with a star, control throttle, fly through a
neutron cone, scoop fuel, avoid collisions, fight, dock or land. It is not an
autopilot or an unattended flying program. You must fly your ship, monitor heat
and fuel, choose when it is appropriate to travel, and handle all hazards.

WHAT THE ACCESSIBILITY OPTIONS ACTUALLY DO
The system-name helper can focus the game, open the Galaxy Map, put the chosen
name in its search box, use the Plot Route control and close the map. This saves
repeated keyboard/menu input; setting a course is not the same as flying it.
The post-supercharge helper can perform that same system-name entry for the
next retained waypoint after the game's supercharge event.

An explicit Jet-Cone Routing control changes that option in the Galaxy Map;
it does not fly the ship into a cone or perform the supercharge for you.

LIMITS AND COMPATIBILITY
The accessibility helpers use Windows input and calibrated screen positions.
The ROG Ally is a Windows example; the Steam Deck example requires Windows.
SteamOS/Linux input-helper support is not included in this version. VR users
still need a way to access EDMC's desktop panel; this is not a native VR overlay.
Changing resolution, display scaling, menu layout or bindings can require
recalibration. Window focus, timing and the game's own input behavior can make
an action fail. Keep the game in windowed/borderless mode, check the destination
and remain at the controls. Nothing here promises unattended travel.

A FAMILIAR TYPE OF ACCESSIBILITY HELP
EDCoPilot documents Galaxy Map course plotting, clipboard copying, and a VR
origin focused on reducing the need to remove a headset. Neutron Highway Navigator Auto
addresses the same keyboard-access problem with its own EDMC accessibility
helpers. It is separate software, with no affiliation or endorsement implied.
Official feature references:
https://www.razzafrag.com/featurelist
https://www.razzafrag.com/
https://www.razzafrag.com/blank-page-1

ROUTE LAMP (On Route / Off Route)
The Jumps line ends with a small lamp (when the progress bar is off):
  Jumps Complete: 5  |  Left: 5  |  (green) On Route  |  ~12 min
- Green On Route: you are at a route system, or the game's plotted route ends
  at a route system still ahead. Neutron routes list only the neutron stops,
  so the ordinary in-between jumps of a plotted leg stay On Route.
- Red Off Route: you are away from the route and not plotted back onto it,
  for example at a fuel star. Plot back to Neutron or Next and it turns green
  before you jump.
- Green Arrived: the last route system has been reached.
- Nothing is shown until EDMC reports where your ship is.
- The time after On Route is an estimate from your recent waypoint-to-waypoint
  pace. It appears after a couple of waypoints and resets on skips or rewinds.

==============================================================================
  Neutron Highway Navigator Auto
  EDMC plugin - version 0.20.4 - by Commander Thalinor
==============================================================================

HEADER
The panel header reads Neutron Highway Navigator, with (Hidden) when collapsed -
the same header as every Neutron Highway Navigator edition. The settings gear
uses EDMC Normal Text; copy, compass and ON/OFF controls use Highlighted Text.

A lightweight route companion for Elite Dangerous Market Connector (EDMC),
built for handheld PCs and other setups without a keyboard. It follows your
neutron route, copies waypoints for you, and can plot your next jump through
the galaxy map automatically after each supercharge - no typing needed.
It never starts a jump: you press the FSD key yourself.
It can also plot a whole new neutron route for you, using Spansh.

CONTENTS
  1. Requirements
  2. Install and update
  3. The panel at a glance (everything you can click)
  4. First-time setup (step by step)
  5. Using a route
  6. The gear menu
  7. Status messages
  8. Accessibility helper settings (automation.json)
  9. Troubleshooting
 10. About and license


------------------------------------------------------------------------------
 1. REQUIREMENTS
------------------------------------------------------------------------------
- Windows (the accessibility helpers use Windows input).
- EDMC with a current release.
- Elite Dangerous running in BORDERLESS or WINDOWED mode. Fullscreen can
  ignore the plugin's clicks.
- A route: either plot one inside the plugin (Gear > Plot New Route, needs
  an internet connection) or load a CSV file, for example from the Spansh
  neutron plotter. A CSV needs one of these columns: System Name, System,
  StarSystem or Waypoint.


------------------------------------------------------------------------------
 2. INSTALL AND UPDATE
------------------------------------------------------------------------------
INSTALL
 1. Close EDMC.
 2. Extract this zip into EDMC's plugins folder:
        %LOCALAPPDATA%\EDMarketConnector\plugins
    (Paste that into the File Explorer address bar to open it.)
    You should end up with:
        ...\plugins\Neutron_Highway_Navigator_Auto\load.py
 3. Start EDMC. The panel header reads Neutron Highway Navigator.
 4. Do the first-time setup in section 4.

UPDATE
 Replace load.py with the new one and restart EDMC. Your route, settings
 and calibration are stored separately (section 8) and carry over.


------------------------------------------------------------------------------
 3. THE PANEL AT A GLANCE (everything you can click)
------------------------------------------------------------------------------
          Neutron Highway Navigator  [gear]          🔼
     Jumps Complete: 3  |  Left: 48  |  (lamp) On Route
        Neutron: <system>  [copy] [compass]
        Next:    <system>  [copy] [compass]
        End:     <system>  [copy] [compass]
                    AUTO-ROUTE (ON)

With no route loaded, only the title and gear show. The other lines appear
when you load a route.

WHAT EACH LINE MEANS
- Neutron  The last route system you reached. During a fuel stop or other
           detour it stays on your last route system, so you can find your
           way back.
- Next     The next system on the route.
- End      The final system of the route (your destination).
- Jumps Complete / Left
           How many route jumps you have made and how many remain.
           The line ends with the route lamp (see ROUTE LAMP near the top).

CLICKABLE AREAS
- [gear] (after the title)
      Opens the gear menu (section 6): routes, calibration, settings, About.

- 🔼 / 🔽 collapse button (right end of the title line, only while a route
  is loaded)
      Folds away everything except the title line. It is EDMC's standard
      button, the same as in BioScan and Pioneer, so it follows your theme
      and any plugin that restyles those buttons. Tap it again to unfold.
      The plugin keeps tracking your route while folded, and remembers
      the choice when EDMC restarts.

- [copy] icon (two overlapping squares), on Neutron, Next and End
      Copies that system name to the clipboard. The status line confirms
      "Copied: <system>". Paste it anywhere, such as the galaxy map search.

- [compass] icon, on Neutron, Next and End
      Copies that system AND plots a route to it through the galaxy map:
      opens the map, searches, selects the system, clicks Plot Route and
      closes the map. Useful for systems that need no supercharge, getting
      back on route, or plotting straight to End.

  Icons turn grey and do nothing when their line is empty (for example
  Next at the end of the route).

- "Complete" (the word, in the Jumps line)
      Opens a list of the systems you have jumped to on this route.

- "Left" (the word, in the Jumps line)
      Opens a list of the systems still ahead, ending with End.

  In both lists:
    - TAP a system to copy it to the clipboard ("Copied: <system>" appears
      above the OK button).
    - PRESS AND DRAG up or down to scroll. Dragging never copies.
    - The mouse wheel and the wide scrollbar also scroll.
    - Close with the big OK button, Enter or Esc.

- AUTO-ROUTE (ON) / AUTO-ROUTE (OFF)  (centered under the route lines)
      Tap or click it to switch auto-route on or off. It always shows
      its current state:
        AUTO-ROUTE (ON)   (armed) - armed: after each supercharge the
                          plugin plots a route to the Next system.
        AUTO-ROUTE (OFF)  (off) - off: nothing happens after a
                          supercharge.
      See section 5 for how it works.



------------------------------------------------------------------------------
 4. FIRST-TIME SETUP (step by step)
------------------------------------------------------------------------------
Do this ON THE DEVICE YOU WILL PLAY ON, at the resolution you play at.
Click positions are saved for that screen. Elite's menus can shift slightly
at a different screen shape, so a setup done on a monitor may miss on a
handheld. A mouse makes setup much easier; after setup everything is a tap
or click.

HOW CALIBRATION WORKS
 The plugin opens the galaxy map for you, then guides you through a few
 steps in its status line. Each step gets a 15-second countdown:

     1/3: Hover over the SEARCH BOX (15s)

 Use the countdown to do what the step asks, then rest the pointer on the
 target. The plugin records where the pointer is THE MOMENT THE COUNT
 REACHES ZERO, so be on the target and hold still before it runs out.
 There is no rush - 15 seconds is plenty. When all steps are done it saves,
 says "Calibration saved." and closes the map.

 Before you start:
  - Be in the cockpit view, not in a menu or panel. (If the map is already
    open, the plugin uses it as is.)
  - Do not press keys or click other windows during calibration.

STEP A - Galaxy map key (automatic)
 The plugin reads your Galaxy Map key from your Elite keybindings each
 time EDMC starts, including keys used with Shift, Ctrl or Alt. Nothing to
 do, unless the map fails to open - then use Settings > Load Keybindings and
 pick your .binds file (section 6).

STEP B - Gear > Calibrate Routing Clicks (required)
 1/3  "Hover over the SEARCH BOX"
      Rest the pointer on the map's search box.
 2/3  "Search a system, then hover over the first RESULT"
      Click the search box, type any system name, press Enter, then rest
      the pointer on the first search result.
 3/3  "Click that result, then hover over PLOT ROUTE"
      Click the result, WAIT for the map to finish moving to it, then rest
      the pointer on the Plot Route button. Do not click Plot Route.
 The plugin saves and closes the map.

STEP C - Gear > Calibrate Jet-Cone Clicks (optional)
 Only needed if you want the Toggle Jet-Cone Routing shortcut.
 1/2  "Hover over the ROUTE SETTINGS panel tab"
      Rest the pointer on the Route Settings tab in the side panel.
 2/2  "Click that tab, then hover over the JET-CONE BOOST toggle
       (don't click it)"
      Click the tab to open it, then rest the pointer on the jet-cone
      boost toggle.

      >>> DO NOT CLICK THE JET-CONE TOGGLE DURING CALIBRATION. <<<
      Clicking it flips your in-game setting. If you clicked it by
      accident, click it once more in the game to set it back.
 The plugin saves and backs out of the map.

STEP D - Gear > Plot New Route (or Gear > Load Route)
 Plot a new route inside the plugin (section 5), or load a route CSV. If
 you are already in one of the route's systems, progress starts there;
 otherwise it starts at the first system.

STEP E - Switch on auto-route (optional)
 Tap AUTO-ROUTE (OFF) so it changes to AUTO-ROUTE (ON) (ON).

If calibration reports "Saved, but missed: ..." the pointer was outside the
game window when the count hit zero. Run that calibration again.


------------------------------------------------------------------------------
 5. USING A ROUTE
------------------------------------------------------------------------------
PLOTTING A NEW ROUTE (Gear > Plot New Route…)
 A small window asks for three things:
  - Start System: filled in with the system you are in. You can change it.
  - End System: start typing; after 3 letters, matching system names
    appear in a list. Tap one to pick it, or type the full name.
  - Efficiency (%): how far the route may stray from the straight line to
    use neutron stars. Default 70. Higher = straighter route, fewer neutron
    stars; lower = more neutron stars, more detours.

 There is no jump range or x4/x6 box to fill in. The plugin reads the ship
 you are flying from your game journal every time you plot:
  - Jump range: the maximum jump range the game records for your current
    ship build. Supercharging does not change this number.
  - Boost: x6 if your ship has an SCO Mk II frame shift drive, x4 for any
    other drive.
 The window shows what it found, for example
     Discovery (Caspian Explorer) · 91.47 ly · x6 boost
 so you can check it at a glance. If no ship data is found, or the number
 looks wrong, a Jump Range field appears for you to fill in instead.
 If your ship is carrying cargo, the window also notes that your real jump
 range is lower than shown, so the route may need extra jumps.

 Press Plot Route. The plugin asks Spansh (spansh.co.uk) to calculate the
 route, then shows a summary such as "52 waypoints, about 180 jumps".
 Press Load Route to use it. If a route is already loaded, you are asked
 before it is replaced. Change any field to plot again; Cancel closes the
 window.

 Notes:
  - Each plotted route is also saved as a CSV in the data folder
    (plotted_routes), so you can reload it with Gear > Load Route after a
    Cancel Route, or share it.
  - Your last End System and Efficiency are remembered.
  - What is sent to Spansh: the start and end systems, jump range,
    efficiency and boost (and the letters you type, for name suggestions).
    Only when a bridge is needed (see UNCHARTED SPACE BRIDGE): your
    current galactic coordinates. For Road to Riches: its four search
    settings and whether mapping values count. For Galaxy Plotter: your FSD
    and fuel-tank numbers, cargo, supercharge state and routing choice.
    Nothing else.
  - Galaxy Plotter FSD stats: coriolis-data (EDCD); game data (c)
    Frontier Developments plc.
  - Spansh is a free community service run by CMDR Spansh; the plugin
    asks it once per route plotted.
  - Spansh's neutron plotter is built around neutron star supercharges.

AUTOMATIC COPY
 Every time you jump to a route system, the plugin moves your progress on
 and copies the new Next system to the clipboard, ready to paste.

AUTO-ROUTE AFTER SUPERCHARGE (when it shows AUTO-ROUTE (ON) (ON))
 1. Arrive at a neutron star on the route.
 2. Supercharge your FSD as usual.
 3. When the game reports the supercharge, the plugin waits the Auto-Route
    Delay (5 seconds by default) before it starts.
 4. It then opens the galaxy map, searches the Next system, selects it,
    clicks Plot Route, and presses Esc until you are back in the cockpit
    view. This takes roughly 10-15 seconds.
 5. The route to Next is plotted. Line up and start the jump yourself.

 Plotting after the supercharge matters: the game only plots the long jump
 once your FSD is supercharged.

 While the map sequence runs:
  - Do not touch the mouse, keyboard or screen; your input could land in
    the wrong place.
  - The galaxy map covers the screen for those 10-15 seconds. If you want
    more time before the map opens, raise the Auto-Route Delay
    (Settings > Auto-Route Delay).

 Auto-route only starts from the cockpit view. If the map or a panel is
 open at that moment, it skips that time.

 White dwarf supercharges trigger it too. Waypoints that need no
 supercharge do not - use the [compass] on Next for those.

GOING OFF ROUTE (fuel stops, detours)
 - Neutron keeps your last route system while you are away.
 - Jumping into any system on the route - even an earlier one - moves your
   progress to it.
 - To head back, use [compass] on Neutron (back to your last route system)
   or on Next.
 - Tip: for an in-game route back to the highway, jet-cone routing in the
   game's Route Settings can make the plot come out wrong. Switch it off
   with Gear > Toggle Jet-Cone Routing (or in the panel), plot, and switch
   it back on later.

LISTS
 Click "Complete" or "Left" in the Jumps line to see the systems. Tap a
 system to copy it; drag to scroll (section 3).


------------------------------------------------------------------------------
 6. THE GEAR MENU
------------------------------------------------------------------------------
 Plot New Route…           Plot a Neutron Highway, Road to Riches,
                           Exomastery or Galaxy Plotter route with
                           Spansh, using
                           your current ship's jump range and boost
                           (section 5).
 ------
 Load Route                Pick a route CSV.
 Cancel Route              Clears the route (asks you to confirm first).
                           Greyed out when no route is loaded. Lost a route
                           by mistake? Load the same CSV again - progress
                           picks up from the route system you are in.
 Fuel Warnings             Off / Relaxed / Normal (default) / Cautious:
                           how early the fuel check warns you.
 ------
 Toggle Jet-Cone Routing   Opens the map, opens the Route Settings panel,
                           clicks the jet-cone boost toggle once, and backs
                           out. Needs Calibrate Jet-Cone Clicks first.
                           NOTE: the plugin cannot see whether jet-cone
                           routing is on or off, so this simply FLIPS it.
                           Check the Route Settings panel if unsure.
 ------
 Calibrate Routing Clicks  Setup for plotting (section 4, step B).
 Calibrate Jet-Cone Clicks Setup for the jet-cone shortcut (step C).
 ------
 Moved to the settings page (File > Settings > this plugin's tab):
                           Auto-Route Delay, Load
                           Keybindings, Open Data Folder and About.


------------------------------------------------------------------------------
 7. STATUS MESSAGES
------------------------------------------------------------------------------
Shown under the panel for a few seconds, then hidden again.

 Copied: <system>          The system is on your clipboard.
 Plotting… / Route plotted. The map sequence is running / finished.
 Plot not confirmed - the game shows no route to <system>.
                           The map sequence ran, but the game's route does
                           not end there. A click probably missed: check
                           the map, and see section 9.
 Busy - try again in a moment.
                           Another map action is still running.
 Elite window not found.   Is the game running?
 Could not focus Elite.    Windows would not bring the game to the front.
                           Click the game once and try again.
 No waypoint to plot.      No route loaded, or nothing on that line.
 Return to the cockpit view first.
                           Close any open menu or panel, then retry.
 The map did not open - check the map key.
                           See Settings > Load Keybindings.
 Run Calibrate Jet-Cone Clicks first.
 Jet-cone routing toggled. Check the panel if unsure.
 Plot Failed - Click To Retry (See Log)
                           The map sequence failed. Click the message to
                           try again; your route is unchanged. Section 9.
 Jet-cone toggle error - see log.
                           See section 9 for the log.


------------------------------------------------------------------------------
 8. ACCESSIBILITY HELPER SETTINGS (automation.json)
------------------------------------------------------------------------------
Your data lives in:
    %LOCALAPPDATA%\EDMarketConnector\NeutronHighwayNavigatorAuto
(Settings > Open Data Folder)

 automation.json      Settings, delays and calibrated click positions.
 active_route.json    Your loaded route and progress.
 plotted_routes       A CSV copy of every route made with Plot New Route.
 cockpit_state.json   A snapshot of your location, ship and route (written when they change).

To change a value, close EDMC, edit automation.json in Notepad, save, and
start EDMC again. All times are in seconds.

 supercharge_delay    5.0   Wait after a supercharge before the map opens
                            (also set from Settings > Auto-Route Delay).
 map_open_delay       2.0   Wait for the galaxy map to open.
 step_delay           0.8   Basic pause between map steps.
 click_extra_delay    0.5   Extra pause after every click.
 map_scroll_delay     2.0   Extra wait while the map pans to the selected
                            system, before Plot Route is clicked.
 plot_route_delay     1.0   Extra wait after Plot Route, for long plots.
 esc_presses          3     Most Esc presses used to leave the map. It
                            stops as soon as you are back in the cockpit.
 esc_gap              0.8   Pause between Esc presses.
 calibrate_countdown  15    Seconds per calibration step.
 plot_efficiency      70    Plot New Route: default Efficiency (%). Also
                            remembered from the last route you plotted.
 plot_type       "neutron"  Last Route Type: "neutron" or "riches".
 riches_radius        25    Road to Riches: Search Radius (ly).
 riches_max_systems   25    Road to Riches: Max Systems.
 riches_min_value 500000    Road to Riches: Min Body Value (credits).
 riches_max_ls     50000    Road to Riches: Max Distance (ls).
 galaxy_algorithm "optimistic" Galaxy Plotter Routing: "optimistic",
                            "pessimistic", "guided", "fuel" or "fuel_jumps".
 show_progress_bar true     Settings page: Show progress bar.
 eta_minutes_per_jump 2.0   Settings page: minutes per jump for the time estimate.
 force_theme_icons false    Settings page: Force EDMC theme colors.
 fuel_safety     "normal"   Fuel Warnings: "off", "relaxed", "normal"
                            or "cautious".
 input_method       "paste" How the system name is entered: "paste"
                            (Ctrl+V) or "type" (key by key).
 type_delay           0.05  Seconds per key when input_method is "type".

The click positions (search_box, first_result, plot_button, jetcone_tab,
jetcone_toggle) are best set with the calibration tools, not by hand.


------------------------------------------------------------------------------
 9. TROUBLESHOOTING
------------------------------------------------------------------------------
 Clicks land in the wrong place
     Recalibrate on this device, at the resolution you play at.
 Plot Route is clicked before the map has finished moving
     Raise map_scroll_delay (try 2.5 or 3.0).
 Long routes get cut off / the map closes too soon
     Raise plot_route_delay.
 The map opens late or a step is skipped
     Raise map_open_delay or step_delay.
 The system name is not entered in the search box
     Set input_method to "type".
 The map stays open at the end
     Raise esc_gap, or esc_presses.
 The map does not open at all
     Check the map key: Settings > Load Keybindings.
 Clicks do nothing at all
     Use borderless or windowed mode, not fullscreen.
 "Plot not confirmed"
     A map click missed. Recalibrate on this screen, or raise
     map_scroll_delay or plot_route_delay so the map has time to finish.
 Plot New Route says it could not reach Spansh
     The message ends with the kind of error, and the EDMC log has the
     details (lines starting "Spansh request"). Check your internet
     connection, and that a VPN or firewall is not blocking EDMC. If
     Spansh itself is down, plot on spansh.co.uk later or load a CSV with
     Gear > Load Route.
 Plot New Route says "A bridge route needs your current system"
     Spansh doesn't know the Start System, and it isn't the system you
     are in, so its coordinates are unknown. Use your current system as
     the Start System (the plugin fills it in), or pick a known system.
 Plot New Route cannot find a system
     Pick the name from the suggestion list, or check the spelling.
 Plot New Route shows the wrong ship or jump range
     Board the ship you want (the game records it when you do), then open
     Plot New Route again. Or type the jump range if the field is shown.
 The plugin does not appear in EDMC
     Check the folder: ...\plugins\Neutron_Highway_Navigator_Auto\load.py
     (load.py must be directly inside that folder), then restart EDMC.
     EDMC's Settings > Plugins tab lists loaded and failed plugins.

 EDMC's log: Help > Open Log Folder > EDMarketConnector-debug.log
 (or %TEMP%\EDMarketConnector). Include it when reporting a problem.


------------------------------------------------------------------------------
 10. ABOUT AND LICENSE
------------------------------------------------------------------------------
Plugin coded collaboratively with Claude, ChatGPT and Gemini by
Commander Thalinor.

Elite Dangerous Commander Name: Thalinor
eMail: thalinor @ gmail.com

You can use this plugin freely for your own personal, non-commercial use.
You can distribute it freely as long as the code has not been modified and
you do not claim it's your own work. You may NOT sell this plugin, use this
plugin for commercial use, or use its code in your projects without prior
authorization.

Plot New Route uses Spansh's neutron plotter (spansh.co.uk) - thank you,
CMDR Spansh.

Human + AI = Future


High Contrast Backgrounds (25 October 2026)
High Contrast Background is available on this plugin's EDMC settings page
and defaults off. Navigator Interface applies it and can force it on for all
main plugin panels. Turning off the force option restores individual choices.
