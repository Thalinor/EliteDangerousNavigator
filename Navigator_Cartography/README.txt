(N) Cartography 0.3.11 - TEST BUILD - 30 October 2026
Folder renamed: this plugin now installs as plugins\Navigator_Cartography (was Systems_Navigator).
All suite folders now start with Navigator_, matching the (N) names in EDMC.
UPGRADING: close EDMC, extract the new ZIP, then run the Navigator folder cleanup tool
(Navigator_Cleanup.bat, from the suite release) once. It moves the old-named folders into
plugins\_Navigator_old_backup, which EDMC ignores, and copies anything they kept (such as
Voice backups) into the new folders. Nothing is deleted. If you skip it, EDMC loads both the
old and the new copy. Your settings, panel order, contrast choices and data are kept.
Required companion: (N) Interface 1.2.14 or newer (folder Navigator_Interface, unchanged).

Earlier notes:
(N) Cartography 0.3.10 - TEST BUILD - 30 October 2026
Suite cleanup (phase 2): (N) Interface is the required base, so its shared popup, wrap and
contrast services replace this plugin's leftover copies. Buttons, menus and Settings pages
follow one suite standard: clickable text uses EDMC Highlighted Text, plain text Normal Text,
the selected tab or menu choice is underlined, and accessibility options sit near the bottom of
Settings, just above the credit line.
- Subcategory choices are all Highlighted Text (clickable); the selected one is underlined.
  Main tabs are Highlighted with the selected tab underlined, as before.
- The station-data offer uses the standard popup buttons.
Required companion: (N) Interface 1.2.13 or newer.

(N) Cartography 0.3.9 - 30 October 2026
Now listed in EDMC as "(N) Cartography" (was "Systems Navigator"). All Navigator suite plugins now
start with (N), so EDMC shows their settings tabs and panels side by side.
Your settings, data and saved files are unchanged; nothing needs to be redone.
Required companion: (N) Interface 1.2.12 or newer (formerly Navigator Interface).
Objects lists now mark engineers, material traders and technology brokers:
  ⚙(E)  engineer workshop (38 bases, built in and verified against Spansh)
  ⇄(M-R) / (M-M) / (M-E)  Raw / Manufactured / Encoded material trader
  ◈(T-G) / (T-H)  Guardian / Human technology broker; (T) when the type is unknown
Names are highlighted (engineers blue, traders/brokers green; darker shades on
light themes). Clicking a name still copies only the station name.
Settings (all on by default): show the codes, highlight engineers, highlight
trader/broker stations.
Station data: on first start Cartography asks whether to download the known
trader/broker stations once (about 300 KB, ~7,000 stations, from the Navigator
GitHub releases) or build the list as you visit. Either way the list grows from
your journals and EDSM visits with no extra requests. The download is offered
again only from settings and happens at most once.
Note: the journal's "engineer" station service is the remote Workshop found at
most stations, so it is deliberately not treated as an engineer base.

Earlier in 0.3.8 (26 October 2026):
Cleanup: removed a duplicate lookup in the Exploration overview.

Earlier in 0.3.7 (25 October 2026):
Required companion: Navigator Interface 1.2.10 or newer.
Powerplay now shows the explicit controller and system state.
Acquisition contenders are ranked by journal progress with percentages;
Show only the top two acquisition contenders defaults on.
One background local-history rebuild upgrades old cached observations.
No new online requests, polling or theme/layout passes.

Previous notes retained below.

Systems Navigator 0.3.6 — TEST BUILD — 25 OCTOBER 2026
Required companion: Navigator Interface 1.2.10 or newer.
Includes the per-plugin High Contrast Background preference, default off,
and all previously tested plugin-specific fixes.

Previous release notes are retained below.

Systems Navigator 0.3.5 — 24 OCTOBER 2026
Required companion: Navigator Interface 1.2.9 or newer. Install it alongside
this plugin for shared EDMC layout fixes, popup styling and window memory.
This increment documents the suite dependency; plugin behavior is unchanged.

Release notes / current AI handoff: shared workspace AI_HANDOFF.md.
The older release history below is retained for reference.

SYSTEMS NAVIGATOR 0.3.4 - TEST BUILD - 2026-10-24
New in 0.3.4:
- Cartography owns its column wrapping, preventing Navigator Interface's
  whole-window wrapping from repeatedly changing the same text layout.
- New rows start in the current palette/font, avoiding a default-color flash.
- Staged arrival display and settled discovery updates reduce repeated redraws.
- Settings: Simplify uninhabited systems (enabled by default). Confirmed numeric
  population zero shows an Uninhabited system label and omits empty/default
  System details. Reported factions, powers, reputation and legal status remain.
  Disable to restore the full System tab. Other tabs are unaffected.
  Zero population does not prove every faction/legal/power field is absent;
  reported values remain visible. Missing population is never treated as zero.

0.3.3: Enlarges Cartography only from six to nine visible text lines, so the
System and Exploration Overview fields fit without scrolling in the tested
300/420px layouts and EDMC themes. All Cartography tabs retain the same height;
long Bodies, Objects, Mining and Combat lists keep internal scrolling.
No polling, data lookups, or other plugins change.

0.3.2 fix: EDSM answers an empty list for a system it does not know. That used
to stop Cartography's journal handling ("'list' object has no attribute 'get'").
Unknown systems are now treated as not yet in EDSM, and older cached answers
in that format are read safely. No settings or caches need to be cleared.

Visible header: Cartography / Cartography (Hidden)
Part of the Navigator suite by Commander Thalinor.

INSTALL
Close EDMC. Extract Systems_Navigator into EDMC's plugins folder, replacing the
same folder rather than creating a second copy. Restart EDMC. Data caches and
preferences are stored separately under EDMC's application data/configuration.

FIVE TABS
System (the first/default tab):
  Current System (click to copy; Unknown has no action)
  Allegiance  |  Powerplay
  Controlling Faction
  Economy  |  Population  |  State
  Security  |  Legal  |  Bounty
  Your Reputation (with the controlling minor faction)

Exploration: Overview and Bodies.
  Overview retains the established star/neutron/scoopable-star/discovery facts,
  adds body identifications this visit and mapped bodies from your available journals.
  Fuel distance is from arrival, not continuously from your moving ship.
  Fully Scanned refers to known/FSS-identified bodies, not full surface mapping.
  Bodies lists known stars, planets and moons, distance, landability and known
  surface sites. Click names to copy. Unknown does not mean an absent body/site.

Mining: Rings, Hotspots, Prospector, Traders.
  Rings includes type, reserves and arrival distance when reported.
  Hotspots lists reported ring signals/counts; counts do not prove an overlap.
  Prospector is the most recent asteroid report, including proportions, core,
  content and Remaining snapshot. It is not a continuous depletion measurement.
  Traders looks up Raw, Manufactured and Encoded material traders using Spansh.
  Station and system names copy separately; distances are Ly and arrival Ls.
  Results are nearest known database entries, not guaranteed accessible stations.
  Cached per reference system for 24 hours, with a manual Refresh Traders action.
  Queries run when the Traders view is first selected in a system, not per field.

Combat: Conflicts, Zones, Signals, Wanted.
  Conflicts shows reported faction conflicts, participants and scores.
  Zones and Signals show detected locations/threats where the journal supplies
  them. Conflict metadata alone does not reveal every zone's location.
  Wanted lists sufficiently scanned wanted contacts observed this visit: pilot,
  ship, bounty, faction, rank and last-seen time. It is not a system-wide roster
  or live position tracker. Contacts clear when you leave the system.

Objects: Stations, Ports, Carriers, Other.
  Carriers have their own list. Ports contains landable surface destinations.
  Lists sort by arrival distance, unknown distances last. Names copy in full;
  narrow rows may abbreviate names and clip details to preserve one row per entry.
  Pad means the largest known pad (S/M/L). Unknown pads remain visible.
  Optional compatibility filtering hides entries known to be too small.
  Explicit delivery/courier/passenger-transport mission turn-in destinations are
  pinned first with a document marker and Turn-In text. Unknown/intermediate
  mission objectives are not advertised as confirmed turn-in locations.
  A hostile/restricted destination can also remain mission-priority. Distinct
  symbols and text identify confirmed hostility, restrictions or possible faction
  hostility; missing warnings never promise that a destination is safe.

Only the System tab shows Current System; the other four tabs use that space
for their own information. Click or press Enter/Space on the known system name
to copy it. Subcategory selectors have no boxes: the selected choice uses
Highlighted Text and the other choices use Normal Text. All tabs have the same
nine-line viewport with internal scrolling;
long lists do not enlarge the EDMC window. Main and subtab choices are remembered.
Use the standard collapse arrow; the collapsed header appends (Hidden).

LOCAL FIRST, THEN ONLINE
Local journal observations appear before asynchronous EDSM work. Newer live
observations are merged into background history. Online data fills gaps and may
replace a local observation only with a strictly newer observation timestamp.
Download time does not qualify as a newer observation. Online failure preserves
known local facts. No recurring graphical refresh or theme-repair timer is used.
Workers never touch Tk; the result queue is polled only while jobs are outstanding.

Sources: EDMC journal/state callbacks, local journals, EDSM system/bodies/stations,
and on-demand Spansh station searches. EDMC does not expose a universal query API
for Inara/EDSM/Spansh; this plugin makes its own cached, read-only lookups where
necessary. Public services receive system names, not commander identities,
mission details, private cargo or scanned-contact records. No uploads are added.
Disable the online option in plugin preferences to use local data only.

LIMITS TO TEST
- Exact personal bounty balance remains Unknown: target bounty is not your bounty.
- Legal state comes from EDMC's current dashboard when supplied.
- Provider data can be old or incomplete, particularly mobile fleet carriers.
- No inference of undiscovered objects, every NPC, guaranteed access or hotspots
  without a reported signal. Missing values stay Unknown; N/A means inapplicable.
- Discovery/star history and the new journal model rebuild once in a background
  worker on upgrade. Initial incomplete fields fill as replay/queries finish.

PRIMARY REFERENCES
https://github.com/EDCD/EDMarketConnector/blob/main/PLUGINS.md
https://www.edsm.net/en/api-v1
https://www.edsm.net/en/api-system-v1
https://spansh.co.uk/stations
https://elite-journal.readthedocs.io/


High Contrast Backgrounds (25 October 2026)
High Contrast Background is available on this plugin's EDMC settings page
and defaults off. Navigator Interface applies it and can force it on for all
main plugin panels. Turning off the force option restores individual choices.
