(N) Interface 1.2.14 - TEST BUILD - 30 October 2026
Interface keeps its folder. It now carries saved panel order, layout profiles, custom
headers, collapse memory and High Contrast choices over to the renamed folders.
All suite folders now start with Navigator_, matching the (N) names in EDMC.
UPGRADING: close EDMC, extract the new ZIP, then run the Navigator folder cleanup tool
(Navigator_Cleanup.bat, from the suite release) once. It moves the old-named folders into
plugins\_Navigator_old_backup, which EDMC ignores, and copies anything they kept (such as
Voice backups) into the new folders. Nothing is deleted. If you skip it, EDMC loads both the
old and the new copy. Your settings, panel order, contrast choices and data are kept.
This is the required base plugin for every (N) plugin.

Earlier notes:
(N) Interface 1.2.13 - TEST BUILD - 30 October 2026
Suite cleanup (phase 2): (N) Interface is the required base, so its shared popup, wrap and
contrast services replace this plugin's leftover copies. Buttons, menus and Settings pages
follow one suite standard: clickable text uses EDMC Highlighted Text, plain text Normal Text,
the selected tab or menu choice is underlined, and accessibility options sit near the bottom of
Settings, just above the credit line.
navigator_attach_window is tidied (no behaviour change). Button labels use the suite ellipsis.
Required companion: (N) Interface 1.2.13 or newer.

(N) Interface 1.2.12 - TEST BUILD - 30 October 2026
Now listed in EDMC as "(N) Interface" (was "Navigator Interface"). All Navigator suite plugins now
start with (N), so EDMC shows their settings tabs and panels side by side.
Your settings, data and saved files are unchanged; nothing needs to be redone.
This is the required base plugin for every (N) plugin. Other suite plugins find it by its new
name and still accept the old one.

Earlier notes:
Navigator Interface 1.2.11 — TEST BUILD — 26 OCTOBER 2026
Cleanup: the list of suite plugins no longer names any unreleased edition.
No behaviour change.

Earlier in 1.2.10 (25 October 2026):
Shared high-contrast backgrounds default off; force-all option, unchanged-paint guards,
and stable collapsed Commander Profile during journal updates.

Previous release notes are retained below.

Navigator Interface 1.2.9 — 24 OCTOBER 2026
Shared foundation for every Navigator suite plugin. Public popup hook now
reports whether styling/window-memory services are ready.

Release notes / current AI handoff: shared workspace AI_HANDOFF.md.
The older release history below is retained for reference.

TEST BUILD 1.2.8 - 2026-10-23
New in 1.2.8:
- First-open popup size follows the controls' requested size after Tk has mapped
  and styled them, capped to the connected screen work area. This avoids small
  pixel defaults hiding basic buttons with larger fonts/DPI.
- Saved user sizes and positions remain respected; Reset All Popup Windows to
  Defaults uses the fitted first-open size. No recurring sizing checks.

Earlier in 1.2.7:
New in 1.2.7:
- Remembers position and size of ordinary EDMC/plugin popup windows across
  reopening and EDMC restarts, including third-party Tk popups.
- Restores windows inside a connected monitor's work area, including monitors
  with negative desktop coordinates. Hidden native tooltips/file dialogs are
  excluded. The main EDMC window is not repositioned by this feature.
- Settings > Navigator Interface > Reset All Popup Windows to Defaults clears
  saved popup locations and brings supported open windows back to defaults.
- Uses Map/Configure/Destroy events with a one-shot save debounce; no polling.
- Public navigator_attach_window(window) hook shares popup styling and geometry
  memory. Plugins can give windows a stable navigator_window_id, or set
  navigator_window_memory=False if they already own geometry restoration.
- Voice Navigator is now recognized as a suite plugin for collapse memory.

Earlier in 1.2.6:
New in this build:
- New option (off by default): Remove "(Hidden)" from collapsed headers.
  Collapsed panels then show just their name; the collapse button still shows
  the state. Turning it off puts "(Hidden)" back.

Earlier in 1.2.5:
- Justify headers has a third choice, Left (Hidden) / Center (Open): a
  collapsed panel's header sits on the left, an open panel's header is
  centred, and it switches as you collapse or open each panel.

Earlier in 1.2.4:
- The scrollbar Handle colour preview square shows its colour again in the
  Dark and Transparent Settings pages (it was painted black).

Earlier in 1.2.3:
- Colour schemes: pick Elite Dangerous (Normal #b36804, Highlighted #efa201),
  EDMC Default or one of your own, then press Apply and OK. Save Current As...
  keeps the colours you have now under a name; Delete removes your own ones.
  Nothing is forced: change colours in Appearance at any time.
- Justify Headers: Left now moves every header, including Radio (with its
  collapsed controls), Dashboard and Commander Profile. Center keeps each
  plugin's own centred layout.
- Settings that only work in the Dark or Transparent themes are greyed out
  while Default is chosen in Appearance. Their values are kept for when you
  switch back. A note at the top of the page explains this.

Earlier in 1.2.2:
- Justify Headers (Settings > Navigator Interface, under Purpose labels):
  Center (default) or Left. Applies to every plugin panel header, including
  collapsed (Hidden) ones and the Commander Profile placeholder.
- Other plugins now remember whether they were collapsed or open. BioScan,
  Pioneer and any plugin with the standard collapse button reopen the way you
  left them. Suite plugins already remember their own state and are untouched.
- BioScan and Pioneer headers now centre on the same line as the suite headers.
- Settings tables (Plugin panel order, Custom Plugin Headers) fill their boxes
  instead of stopping short.
- Section divider lines in Settings follow the dark palette instead of showing
  as bright white lines. The Windows File-menu border is drawn by Windows and
  cannot be recoloured.

Earlier in 1.2.1:
- Corrects explicit Windows light colors on EDMC myNotebook labels and adds
  Settings OptionMenu styling, including dropdown menus.
- Gives checkboxes/radio buttons readable, font-sized indicators without
  painting selected options as highlighted blocks.
- Leaves both Appearance color-picker buttons completely untouched: preview
  colors, fonts, states, commands and newly picked draft colors remain EDMC's.
- Tested with EDMC's published myNotebook classes on Windows, including
  Default restoration and idle-settling checks. No periodic styling checks.

Earlier in 1.2.0:
- EDMC's Settings dialog now follows its selected dark/transparent palette,
  including built-in and plugin pages. Settings stays opaque in Transparent mode.
- A readable system font and measured table row heights prevent crowded rows.
  Measured columns and horizontal scrollbars make long table content accessible.
- Navigator Interface's own long Settings page now scrolls internally.
- Custom Plugin Headers lists installed plugins beside the existing purpose
  labels. Set a name or Reset To Default; Apply/OK commits it.
- All work is event driven. No theme watchdog, stream probe or repeating timer.

Earlier in 1.1.1:
- Labels a plugin marks as one-line (navigator_no_wrap) are no longer wrapped
  to the window width. This fixes Ship Radio song titles splitting onto two
  lines. Other labels wrap as before.
- The resize grip's cursor name is now valid on every platform, not only
  Windows.

Earlier in 1.1.0:
- Resize grip is 11x11 px, with matching bottom clearance and Normal Text color.
- Manual Bubble / Exploration / Mining layout profiles in Preferences save the
  current plugin order and collapsed states. Save and Apply are explicit actions;
  profiles never switch automatically. Missing panels are ignored.
- Theme notification uses a single event after settings apply. No graphics timer
  or theme watchdog was added. Existing Alt/menu, scrollbar and layout fixes stay.

NAVIGATOR INTERFACE 1.2.6
Part of the Navigator suite by Commander Thalinor.

INSTALL OR UPDATE
Close EDMC. Extract this archive into its plugins folder:
  %LOCALAPPDATA%\EDMarketConnector\plugins
The result must be Navigator_Interface\load.py directly inside that folder.
Replace program files in the existing matching folder; keep one active copy.
Restart EDMC. Open Settings > Navigator Interface to configure it.
No additional Python packages are needed. Tested with Windows/Tk fixtures
matching the supplied EDMC 6.1.2 UI. Live use remains the final verification.


SETTINGS COMPATIBILITY
The main window retains its existing EDMC theme, fonts and behavior. Only the
Settings dialog and its child input dialogs get the new compatibility styling.
Dark and Transparent use EDMC's Normal Text / Highlighted Text colors on a dark
opaque background; Default returns to the original light controls. Appearance's
two live color-picker buttons are excluded from all compatibility styling,
including their colors, fonts, states and commands. Draft choices stay intact. Windows caption coloring
is requested where supported; the operating system may retain native details.

Settings uses a readable system font instead of imposing the main window's
display font on dense tables. Treeview row heights are measured from that font.
Columns expand to fit bounded samples and get horizontal scrolling when needed;
manual column widths are preserved after the initial adjustment. Tables populated
asynchronously are handled by insert events, not polling. Existing filters,
selection, sorting, scrolling and data callbacks remain attached.
The ttk theme engine is not switched globally; main-window widgets are untouched.
All styling hooks are removed/restored when the plugin stops. Unknown/custom
widget layouts can retain their native details. Live EDMC validation is still
needed beyond the Windows/Tk fixtures used for this test build.

CUSTOM PLUGIN HEADERS
Settings > Navigator Interface > Custom Plugin Headers (beside Purpose labels).
Select an installed plugin, click Custom Header, enter a name, then Apply/OK.
Blank input or Reset To Default clears that override. Settings Cancel discards
unapplied edits. Names are limited to 80 characters and stored by plugin identity
in EDMC config. Plugin folders, settings-tab names and data files are not renamed.

An expanded custom header shows only your name. When collapsed, it shows your
name followed by (Hidden). This custom behavior also takes precedence for Radio
when it is explicitly given a custom name; Radio's default compact-header behavior
is unchanged when there is no override. Existing collapse controls still work.
Custom names take precedence over Exobiology/Geology purpose options. Resetting
returns to the selected purpose label, or the owner's latest native label.
The original purpose-only options still retain the owner's live status details.

The list includes installed plugins. A panel must expose a compatible text header;
background-only plugins or unrecognized/textvariable-driven headers show No Visible
Header and cannot be edited. This prevents a data field being renamed by mistake.
Nothing edits or starts another plugin. Saved overrides survive EDMC restarts.

VALIDATION FOR 1.2.0
Windows/Tk fixtures cover dark/default/transparent Settings, table rows/columns,
visible table stacking, horizontal scrolling, comboboxes, color-preview swatches,
custom header draft/save/Hidden/reset/purpose precedence and complete cleanup.
Idle-settling checks confirm no repeating styling callbacks. Existing regressions
pass for resizing, pane height, plugin ordering, layout profiles, purpose labels,
toasts, Alt chrome, resize-grip clearance and core-field collapse. Release startup
is also checked from a clean extraction, without development-folder helpers.

COLOUR SCHEMES
Settings > Navigator Interface > Colour scheme. These are EDMC's own two theme
colours (Appearance > Normal Text and Highlighted Text):
- Elite Dangerous: #b36804 / #efa201, matching the game's default orange HUD.
  If you changed your HUD colour in the game, it will not match exactly.
- EDMC Default: #ff8000 / white.
- My Original: the colours you had before you first opened this page, if they
  differ from the two above.
Choose one, press Apply, then OK. Apply fills in EDMC's Appearance colours; EDMC
saves them when you press OK. Save Current As... stores the current colours
under a name (up to 40 characters). Delete removes one of your own schemes;
the built-in ones cannot be deleted. If you later pick other colours in
Appearance, the page simply shows "Current colours: Custom".

DARK / TRANSPARENT ONLY
EDMC's Default theme uses Windows' own colours and window frame, so these
settings only work in the Dark or Transparent themes: Colour scheme, fixed
window width and height, and similar text wrapping. They are greyed out while
Default is chosen in Appearance and keep their values. Transparent uses the
same two colours as Dark.

HEADER JUSTIFY AND COLLAPSE MEMORY
Justify headers: Center, Left, or Left (Hidden) / Center (Open). Press OK to apply. Left keeps each panel's
collapse button on the right and moves each header as one block, so Radio's
collapsed controls stay beside its title. Turning Navigator Interface off restores every
header to its plugin's own layout.

Collapse memory covers plugins outside the Navigator suite. When you click a
plugin's collapse button, its state is saved in EDMC's config. At the next start
that panel is opened or collapsed to match. Layout profiles save it too. Nothing
is changed inside the other plugin; Navigator Interface presses its own button.

PURPOSE LABELS
Two independent options are OFF by default:
  Use Exobiology header for BioScan
  Use Geology header for Pioneer
Each is available when the matching plugin panel is loaded. They adapt only
that panel's label; they do not edit either third-party plugin's source files.
Live status text, predictions and signal summaries are retained. Collapsed
labels become Exobiology (Hidden) and Geology (Hidden). Switching an option
off restores the owner's most recent text immediately. Native plugin names
remain in EDMC's settings and plugin list.

APPEARANCE AND LAYOUT
- Hide vertical scrollbars completely, retaining mouse-wheel scrolling, or
  show a thin handle with a chosen color and width.
- Compact the stock collapse/expand controls across compatible plugins.
- Fit BioScan and Pioneer data panes, sharing available height equally.
- Keep dark/transparent text wrapping similar to the default theme.
- Reorder whole plugin panels in Settings; Default Order restores EDMC order.
  New panels are placed after saved ones. Plugin identities are not renamed.
- Collapse the Commander/Ship/Suit/System/Station fields with the top-right
  stock arrow. Only the collapsed header reads Commander Profile (Hidden).
  The native Suit row's conditional visibility is retained.

WINDOW CONTROLS
- In dark/transparent modes, drag the bottom-right triangle to resize.
  It is 11x11 px, follows Normal text color, and reserves its own bottom row
  below plugins/footers. It does not overlap the last panel's controls.
- Optional width and height locks apply to borderless dark/transparent modes.
  Dragging updates active locks. The default theme keeps native resizing.
- Optional Alt modes hide either the menu alone or both title/menu. Press
  and release Alt in focused EDMC to reveal/hide them. These options are
  mutually exclusive and off by default. Always-on-top remains supported.

FOOTER
Authentication success and other status messages expire after five seconds;
their row/padding is removed, and later messages can appear again. Toast text
is centered. Optional independent controls hide Pioneer Export, EDMC Update,
and BioScan Fetch EDSM Data. Those three controls default off.

COMPATIBILITY AND DATA
BioScan and Pioneer are optional, installed separately. Adaptations use their
already-loaded UI state and leave unsupported/missing panels alone. Settings
are kept in EDMC config under NavInterface_. No extra network services,
background polling or recurring refresh timer is added. Layout/theme updates
are coalesced from events. Shutdown restores the UI changes owned by this
plugin, including original third-party header text.

CURRENT SUITE HEADERS
Ship Computer: Ship / Ship (Hidden)
Systems Navigator: Cartography / Cartography (Hidden)
Docking Navigator: Docking (automatic visibility; no manual collapse button)
Neutron Highway Navigator: unchanged, with (Hidden) when collapsed.

Created collaboratively with ChatGPT (Tachikoma), with fixes contributed
through the user's shared builds. Human + AI = Future


High Contrast Backgrounds (25 October 2026)
Force High Contrast Backgrounds on All Plugins overrides each plugin's own choice without changing it. Off by default. Applies to main plugin panels;
popup styling remains with the shared popup service.
