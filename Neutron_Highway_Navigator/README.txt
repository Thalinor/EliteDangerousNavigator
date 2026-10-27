Neutron Highway Navigator 1.4.4 — TEST BUILD — 26 OCTOBER 2026
Smoother panel: the panel and its status file now update only when your
location, ship or route actually changes, and the progress bar and icons
are only repainted when they look different. Less disk writing and redrawing.

Earlier:
Required companion: Navigator Interface 1.2.10 or newer.
Includes the per-plugin High Contrast Background preference, default off,
and all previously tested plugin-specific fixes.

Previous release notes are retained below.

Neutron Highway Navigator 1.4.2 — 24 OCTOBER 2026
Required companion: Navigator Interface 1.2.9 or newer. Install it alongside
this plugin for shared EDMC layout fixes, popup styling and window memory.
This increment documents the suite dependency; plugin behavior is unchanged.

Release notes / current AI handoff: shared workspace AI_HANDOFF.md.
The older release history below is retained for reference.

NEUTRON HIGHWAY NAVIGATOR 1.4.1 - TEST BUILD
By Commander Thalinor and collaborators

CHOOSE ONE EDITION
There are two editions. Install ONE of them, not both:
- Neutron Highway Navigator (this one): route planning, progress and clipboard
  copying. It never touches the game's controls.
- Neutron Highway Navigator Auto: everything above, plus galaxy-map helpers that
  enter the system name and plot the course for you.
Both show the same panel header, Neutron Highway Navigator. Running both at
once gives two route panels with separate progress, which is confusing.

1.4.1: End System defaults to the system you have targeted in Elite.

1.4.0: Exomastery, FSD injections and realistic jump range - see below.

1.3.2: Time estimate - a default minutes-per-jump setting and idle gaps ignored.

1.3.1: Fix - the plugin's tab now appears in EDMC's Settings window.

1.3.0: Route progress bar and a settings page - see PROGRESS BAR AND
SETTINGS PAGE below.

1.2.0: Galaxy Plotter route type - see GALAXY PLOTTER below.

1.1.1: Route Type uses the standard Windows dropdown, like the rest of the suite.

1.1.0: Road to Riches routes and fuel warnings - see ROAD TO RICHES AND
FUEL WARNINGS below.

1.0.5: Uncharted space bridge - see UNCHARTED SPACE BRIDGE below.

1.0.4: Documentation only - the two editions are now named as above.

1.0.3: The settings gear uses EDMC Normal Text, matching the header beside it.

1.0.2: The separate bottom status line ("Route Loaded" / "Detour" / ETA) is
replaced by a small lamp at the end of the Jumps line. See ROUTE LAMP below.

1.0.1: Startup hardening shared with the Auto edition. The colour lookup
cannot fail during EDMC startup, and if the panel ever cannot be built it shows
a one-line notice pointing to the EDMC debug log instead of disappearing.

An independent EDMC plugin for neutron-route planning, clipboard names and
route progress. The visible header is Neutron Highway Navigator, with (Hidden)
when collapsed. Installation folder: Neutron_Highway_Navigator.

INSTALL
Close EDMC. Extract Neutron_Highway_Navigator into:
  %LOCALAPPDATA%\EDMarketConnector\plugins
The resulting file is plugins\Neutron_Highway_Navigator\load.py.
Keep that folder name, then restart EDMC.

ROUTES AND CLIPBOARD
- Gear > Plot New Route calculates a route using Spansh. It reads the ship's
  recorded jump range, offers a range field if missing, and remembers efficiency
  and destination. This plans the waypoint list inside EDMC.
- Gear > Load Route accepts a CSV with System Name, System, StarSystem or Waypoint
  as a column header. Generated routes are also saved as CSVs.
- Neutron is your retained place on the route, not your actual current system.
  A fuel detour leaves that line and the route position intact.
- Arriving at a later listed waypoint completes intervening entries. Revisiting
  an earlier listed waypoint rewinds the route and restores the remaining list.
- Next and End have copy buttons. Neutron has a copy button too. Arrival at a
  listed waypoint copies Next to the clipboard. Use the copied name in the game
  yourself. Nothing else is required from the plugin to follow the route.
- Complete and Left open scrollable lists. Click a listed name to copy it.
- The route lamp at the end of the Jumps line shows On Route / Off Route /
  Arrived. See ROUTE LAMP below.
- Cancel Route clears this plugin's active route after confirmation. Generated
  CSV copies remain available to load again.

APPEARANCE
Clickable names and copy controls follow EDMC Highlighted Text. The settings
gear and static labels follow Normal Text. The stock collapse button adds (Hidden) to the header.
Theme application is event-driven; there is no recurring graphics repair timer.

ROUTE LAMP (On Route / Off Route)
With the progress bar off (Settings), the Jumps line ends with a small lamp:
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

SEPARATE SAVED DATA
This plugin stores its own settings, active route, progress and route CSVs under:
  %LOCALAPPDATA%\EDMarketConnector\NeutronHighwayNavigator
Settings > this plugin's tab > Open Data Folder opens that location.
On the first run only, if no route exists here, the plugin takes a read-only copy
of an existing route from an earlier test build (CockpitCompanion data folder).
After that, progress and settings are independent. It never changes those files.

Settings include the progress bar and theme-colour options, collapsed state, route efficiency, last destination, route type,
the Road to Riches settings, the Galaxy Plotter routing choice and the Fuel Warnings choice.
Install only one edition (see CHOOSE ONE EDITION). If both were installed, each
would keep its own progress and clipboard actions.

EXOMASTERY, FSD INJECTIONS AND REALISTIC JUMP RANGE (1.4.0)
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
- Plot New Route fills in the End System from Elite (version 1.4.1): the end of the route
  you have plotted in the game, or else the system you have targeted (whole systems only,
  never a station, body or carrier). It's never the system you are in or a system on the
  route already loaded. With nothing targeted, the last End System is kept. You can still
  type any End System.

PROGRESS BAR AND SETTINGS PAGE (1.3.0)
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
    Open Data Folder and About (moved here from the gear menu).
  The gear menu keeps what you use in flight: plotting, loading and
  cancelling routes, Fuel Warnings.
- The Off Route lamp is now red (it was amber).
- Time estimate: until the plugin has learned your pace, it assumes a set number of
  minutes per jump (Settings page, default 2). Gaps between waypoints longer than three
  times that (at least 6 minutes) count as a break, so idle time doesn't slow the
  estimate down.

GALAXY PLOTTER (1.2.0)
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

ROAD TO RICHES AND FUEL WARNINGS (1.1.0)
Plot New Route now has a Route Type at the top:
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

Fuel warnings watch your fuel after every jump. The game records your fuel,
your ship's fuel scoop and the star class of every jump in a plotted route,
so the plugin warns you before fuel runs short, for example:
  Fuel check: about 3 jumps of fuel. Top up at <star> (2 jumps ahead).
  Fuel check: top up here (K star). ...
It tells you if no scoopable (KGBFOAM) star is left on the plotted leg, or
if no fuel scoop is fitted. Choose how early it warns in Gear > Fuel
Warnings: Off, Relaxed, Normal (default) or Cautious. It needs one jump of
fuel use first to learn your ship's consumption.

UNCHARTED SPACE BRIDGE (1.0.5)
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

DATA AND REQUIREMENTS
Requires EDMC and Tk. Existing CSV routes work offline. Spansh route calculation
and name suggestions require an internet connection. Spansh receives the requested
start/end systems and route parameters, not a private journal upload. When
a bridge is needed, it also receives your current galactic coordinates. Road to
Riches sends its four search settings and whether mapping values count. Galaxy
Plotter sends your FSD and fuel-tank numbers, cargo, supercharge state and routing choice. Calculation
runs in a worker; Tk receives queued results while a request is active. Closing
the dialog cancels further result collection. A failed request keeps the loaded
route intact and offers Retry Plot.

TESTING
Full plugin startup and EDMC theme updates, independent data, clipboard actions,
CSV progress, detours/skips/rewinds, hidden headers, requested route planning,
result loading and shutdown are covered by automated Windows/Tk checks.
Live game and community-service behavior should also be checked in your setup.

ABOUT AND TERMS
Plugin coded collaboratively with Claude, ChatGPT and Gemini by
Commander Thalinor. Human + AI = Future.

You can use this plugin freely for your own personal, non-commercial use.
You can distribute it freely as long as the code has not been modified and
you do not claim it's your own work. You may NOT sell this plugin, use this
plugin for commercial use, or use its code in your projects without prior
authorization.

Plot New Route uses Spansh's plotters (spansh.co.uk) - thank you,
CMDR Spansh. Galaxy Plotter FSD stats: coriolis-data (EDCD); game data
(c) Frontier Developments plc.

Human + AI = Future


High Contrast Backgrounds (25 October 2026)
High Contrast Background is available on this plugin's EDMC settings page
and defaults off. Navigator Interface applies it and can force it on for all
main plugin panels. Turning off the force option restores individual choices.
