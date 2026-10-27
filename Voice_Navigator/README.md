# Voice Navigator 0.2.2 — expanded test build

An EDMarketConnector plugin for offline voice commands and editable multi-step
macros in Elite Dangerous. Built collaboratively for the Navigator plugin suite.

No VoiceAttack, HCS pack, cloud AI service, API key, or recurring subscription
is required. Speech recognition uses the Windows desktop speech engine.

## Install

1. Close EDMC.
2. In EDMC's Settings → Plugins, use **Open** to find your active plugins folder.
   The usual location is %LOCALAPPDATA%\EDMarketConnector\plugins.
3. Copy the entire Voice_Navigator folder there. Its load.py must be directly
   inside that folder, with the other Python files and VoiceHost.cs.
4. Restart EDMC.

Navigator Interface is a required companion (tested baseline 1.2.10). It supplies
popup themes, readable table rows, and saved window geometry. No install block
is imposed if it is missing.

An earlier development draft may exist in your Codex working folder. Use this
complete folder as one unit; do not combine individual files from the drafts.

## Using Voice Navigator

1. Use a macro's **Preview** button to inspect its steps without sending keys.
2. Click **Settings… → Listening Settings → Check Speech Engine**. It reports
   installed recognition engines and TTS voices. The Activity Log can be
   disabled in Listening Settings.
3. Click **Listen** in the main plugin. The first start builds a small helper
   from the bundled C# source using Windows' .NET Framework compiler. This runs
   in the background and is cached in your EDMC data folder.
4. Return focus to Elite and say **galaxy map**, **landing gear down**, or
   **zero throttle**. Elite must be the foreground program for game input.
   The plugin does not change focus. Details remain in the optional Activity Log.

The main panel ends below its buttons. **High Contrast Background**, available
in EDMC's Voice Navigator settings and in Listening Settings, optionally uses
a black panel; it defaults off so Voice matches the other plugins. The global
Dry run switch and microphone meter have been retired. Explicit Preview still
sends no keys, and listening remains off until you start it.

The header arrow collapses Voice to **Voice Navigator  |  status** and hides
its buttons. Listening continues unchanged. Expand the arrow to restore the
separate status line and controls. The panel remembers its collapsed state;
Navigator Interface controls its center, left, or mixed header alignment.

The microphone is opened only after you click Listen. **Stop Listening**, the
spoken phrase **stop listening**, and closing EDMC stop the listener.
**Cancel Macro** or the spoken phrase **cancel macro** stops a sequence.

This is a first test build. Live microphone accuracy, latency, Elite input
acceptance, and native window appearance still need testing on Windows.

## Make your own voice macros

Open **Settings… → Elite Bindings**, select a preset section, and search for an
action. Select it and click **Create Voice Macro from Selected Action**.
Alternatively, use **Voice Macros → Add**.

A macro contains:

- A display name.
- One or more spoken phrases separated by semicolons.
- A game context: any, ship, SRV, or on foot.
- Ordered action and pause steps.
- Optional spoken acknowledgement after successful execution.

In **Edit Macro**, **Spoken** is off by default. The spoken reply field starts
with the command name, so users can enable it with one check or edit the text.
Listening Settings has a master switch for allowing replies at all.

Each action can have its own preset section, key hold time (0.02 to 10 seconds),
gap, and repeat count. Add, edit, remove, or move steps with the editor buttons.
**Preview** logs the sequence without sending keys.

For example, a custom “prepare to land” macro could contain:

1. Ship → Throttle Zero.
2. A 0.5-second pause.
3. Ship → Landing Gear, with **Ensure On / Deployed**.

The gap is applied after each press. Pauses can be zero to 30 seconds.
Hold times can be 0.02 to 10 seconds; repeat counts can be 1 to 20.
Macros can contain up to 64 steps and up to three minutes of configured timing.
Only one macro runs at a time; extra recognized commands are ignored while it
runs. Cancel and stop-listening phrases remain available.

**Ensure state** supports landing gear, hardpoints, ship lights, cargo scoop,
and night vision. It checks Status.json, skips a toggle if the desired state
is already set, and waits for the game's confirmation after sending a key.
An unconfirmed toggle is reported; it is not automatically repeated.

## Bindings

The plugin reads all supported actions from the active General, Ship, SRV, and
On Foot presets selected in StartPreset.4.start, including newer numbered
.binds versions such as 4.2. The Elite Bindings tab lists the complete loaded
catalog rather than a sample list. Legacy one-line StartPreset.start files are
also supported.

Each section reads its own selected file. The editor exposes all button
actions in that file, so you can explicitly choose the appropriate section.
Keyboard bindings in either Primary or Secondary slots are supported, along
with keyboard modifiers, arrow keys, right Control/Alt, and the numeric keypad.

Controller-only and unassigned actions are visible as **No keyboard binding**.
Assign a keyboard alternative in Elite, then click **Reload Bindings**. This
version sends keyboard input; it does not emulate a joystick or analogue axis.
It never changes your Elite binding files.

In **Elite Bindings**, **Load Keybinding File…** opens at Elite's usual bindings
folder when it exists; choose a custom location if needed. The selected file
is used for all four sections. **Default Keybindings** clears that override and
reloads Elite's active presets. **Clear All Keybindings** empties Voice
Navigator's loaded catalog after a warning; it never edits or deletes Elite's
files. Commands remain saved and can be rebound when keybindings are loaded
again. If a selected preset is built into Elite and has no file in the user
bindings folder, save a custom preset in Elite or load its .binds file.

## Recognition and replies

Leave the recognition language blank to select an installed Windows recognizer.
You can specify a culture such as en-US if that language is installed.
The confidence threshold defaults to 0.72.

An optional wake phrase is prepended to every command, including cancel and
stop. With “computer” set, say “computer landing gear down.”
Save Settings restarts an active listener with its updated vocabulary.

Replies use an installed Windows text-to-speech voice. **TTS Settings** lists
available Windows voices and provides rate, low/normal/high pitch, volume,
Preview Voice, and Reset Voice Defaults. Pitch response can vary by installed
voice. The microphone
recognizer ignores results while the helper is speaking and briefly afterward
to reduce feedback. A headset is useful when testing this behavior.

The Listen status button uses the EDMC Highlighted text color while listening
and Normal text color while stopped. An optional Listening Settings switch
uses the plugin suite's red `#d32f2f` while active and green `#1f9d3a` while
inactive instead.

## Troubleshooting

- **No Windows recognizer available:** check the Speech language components in
  Windows Settings → Time & language. Desktop speech components and online
  dictation are different facilities. Run EDMC under the Windows account with
  your speech setup. A restricted process can see a different set of engines;
  an empty probe result alone does not establish that the PC lacks speech.
- **Helper cannot build:** the plugin needs Windows' .NET Framework 4.x
  compiler and System.Speech assembly. The Activity Log gives compiler
  output. No downloads or administrative changes are performed automatically.
- **No recognition:** check Windows microphone privacy settings,
  the default input device, microphone mute, and the selected speech language.
- **Keys recognized but no game action:** keep Elite focused,
  and verify the listed keyboard binding. EDMC and Elite should run at the same
  privilege level. The Activity Log distinguishes rejected input from a
  missing binding.
- **Macro requires ship controls:** state-aware starter commands need current
  ship status supplied by EDMC while the game is running.
- **Menus:** map commands in the starter set toggle their maps. Complex
  docking/navigation menu sequences are not prebuilt in this version.

## Settings and development

The **Assistant** tab has Behavior, AI Connections and Report Phrases sections.
Local reports and conversational AI are independently enabled and default off.
**Built In Chatbot** is first in the connection selection and is selected for new
setups. Existing saved AI selections stay selected. This is a pattern-based
offline chatbot, not a trained AI model. It needs no API key, model installation
or network connection. Select it, enable local reports or chatbot/conversational
AI, then Save. Its address/model/key fields are disabled, and the built-in choice
cannot be removed. Test Chatbot runs a local readiness/help response.

It answers common variations of questions about fuel, cargo, materials, known
biological signals, nearest recorded life, cached material traders, distances,
game-plotted jumps, Navigator waypoints, trip data, radio playback, landing pad,
system information and recorded station services. Your own report phrases can
map to these topics. Say "Assistant help" for examples. Unrecognized questions
stay offline while Built In Chatbot is selected, even if online AI is allowed.

Distances to Sol use its fixed origin and your current system coordinates.
Other named systems need coordinates already recorded in the session, plotted
route or Cartography's loaded atlas. These are straight-line system distances,
not route length. Nearest life is ranked by available distance from the arrival
star, not live distance from your ship, and incomplete/unknown scans are stated.
Game jump counts and Navigator waypoints are reported separately; a waypoint
can take several jumps. Trader/service results may be stale and do not imply
permits, access or an exhaustive search. No query fetches fresh community data.
Optional plugins that are unavailable simply leave those answers unknown.

Use either/both Keyword Only switches: Ship Inputs has its own prefix, Assistant
defaults to Computer and accepts optional aliases such as Etalia. With both
switches off, exact macros run, other speech goes to Assistant, and overlapping
report/macro phrases ask for clarification. Assistant-addressed speech never
falls through to ship input. Existing saved macro wake phrases retain their behavior.

Local reports cover fuel, cargo, current system/ship, recorded biological signals,
credits snapshots and help. Add/remove report wordings and choose their topics.
Fuel/cargo require recent dashboard telemetry; incomplete scans remain unknown.
Biological answers can read Cartography's already-loaded current-system cache
without triggering a lookup. Frontier snapshots are optional: EDMC supplies
account data through its existing login and Update flow; Voice makes no extra
Frontier requests and does not access authorization tokens. Credits replies state
the snapshot's age. This integration does not provide arbitrary Frontier queries.

Conversational AI supports local Ollama, OpenAI Responses, and OpenAI-compatible
Chat Completions servers. Add/remove named connections and enter the exact model
available on your server/account. Local HTTP addresses must be loopback; remote
connections require HTTPS and the separate Allow online AI switch. Other provider
protocols are not yet supported. No AI runtime/model is installed or downloaded.
API keys save separately to this Windows user's Credential Manager, bound to the
connection/address. Keys are never placed in portable settings or backups. Use
Remove Key before removing a connection; changing its address needs a separately
saved key. Credentials are saved immediately by Save Key, independently of Cancel.

Local report topics answer first, including unavailable-data replies. General
conversation uses only the selected connection, with no automatic provider
fallback, browsing, ship-control tools or community-site requests. Questions go
to that connection; game context is included only with the sharing checkbox.
Conversation is currently single-turn, without a persistent chat history.
Repeated questions/context can use a 60-second in-memory response cache; one AI
request runs at a time, five seconds apart, with a 30-second connection timeout.
Errors are not retried automatically. Rate-limit cooldowns honor Retry-After and
increase on repeated throttling. OpenAI requests use store=false.

Save applies the Assistant form; OK saves and closes; Cancel closes without
saving draft settings. Ask uses saved settings. Try Routing previews a draft
phrase without sending keys or querying an AI. Test AI uses the selected draft
connection and sends a small test prompt, which can use paid API credits.
Opening settings and switching tabs never checks connections automatically.
Spoken answers use the existing Windows TTS settings and suppress recognition
during playback plus the helper's quiet interval. Listening remains manual.
Settings and the generated speech helper are stored under EDMC's data folder
in Voice_Navigator, outside the plugin's installation directory. Macros
survive replacing the plugin folder.
Listening Settings can disable Activity Log capture. Legacy global dry_run
settings are retired without removing saved macros or other preferences.
If a corrupt settings file is encountered, it is
preserved; saving replacements first makes a separate recovery copy.

The source is included. Python code requires Python 3.9 or later and uses the
standard library. EDMC supplies its own Python runtime; installing a separate
Python interpreter is not required to use the plugin.

## Backup

Open **Settings… → Backup**, between Assistant and Activity Log. Separate
buttons save plugin settings (including listening, TTS, appearance and binding
preferences), voice macros, Assistant settings, or everything together for a
complete restore. Assistant backups include report phrases and connection/model
settings; API keys remain in Windows Credential Manager. The Ship Inputs prefix
is a shared listening preference and belongs to the plugin-settings backup.

Backups use distinct, timestamped JSON filenames in the installed plugin's
**Backups** folder by default. Choose Backup Folder selects another location;
Move Backup Folder moves this plugin's backup files there without overwriting
files or moving unrelated contents;
Open Backup Folder opens it in Explorer. Keep personal backup files out of
release ZIPs.

Load a Backup recognizes its type and restores only that category. It also
accepts older Export Settings JSON files as complete backups. Before restoring,
it makes a complete backup of the current saved setup and stops listening.
The selected backup folder stays local and is not replaced during restore.
Save any edits in Listening/TTS Settings before backing up; backups use saved
settings. Backups contain configuration, not plugin code, generated speech
helpers, Windows speech installations, or Elite's original .binds files.

To run the platform-independent core checks from the archive root:

    python -m unittest discover -s tests -v

Tests use fixture bindings and fake input. They do not access a microphone or
send keys. See VALIDATION.md in the archive root for the checked and pending
parts of this release.

Navigator Interface can force High Contrast Backgrounds on All Plugins. That
override does not change Voice's saved individual choice; turning it off restores
the individual setting. All contrast settings default off.
