Voice Navigator 0.2.2 — TEST BUILD — 26 OCTOBER 2026
The panel header now uses EDMC Normal Text like every other suite header.

Earlier in 0.2.1:
Required companion: Navigator Interface 1.2.10 or newer.
Assistant: Built In Chatbot, optional AI connections and Frontier snapshots;
keyword routing, local reports and key-free portable backups. Clean panel and shared popup services retained.

Previous release notes are retained below.

Voice Navigator 0.2.0 — direct development patch, 25 OCTOBER 2026
Built In Chatbot is now the first Assistant connection choice. It answers
common game/plugin information questions without an AI model, key or network.
Existing provider selections remain; choose Built In Chatbot to use it.
Known/cached facts and missing data are distinguished, as are plotted jumps
versus Navigator waypoints and arrival-star versus live ship/body distances.
Assistant now supports optional local reports and conversation through local
Ollama, OpenAI, or OpenAI-compatible servers. Independent ship/Assistant keyword
switches, aliases, editable report phrases, named AI connections and Assistant
backups are available in Settings. Features default off; online AI requires its
own opt-in. API keys stay in Windows Credential Manager, outside portable backups.
Optional Frontier account snapshots reuse EDMC data without extra API requests.
See README.md for setup, limits and validation scope.

Voice Navigator 0.1.6 — 24 OCTOBER 2026 (historical)
Required companion: Navigator Interface 1.2.9 or newer. Install it alongside
this plugin for shared EDMC layout fixes, popup styling and window memory.
Removed the copied popup compatibility engine, private-service fallback,
standalone sizing pass and duplicate table-font styling. The Interface
public popup hook handles them. Plugin-specific meter/editor layout stays
here. All 0.1.5 fixes remain, including 10-second holds and transparency.

Release notes / current AI handoff: shared workspace AI_HANDOFF.md.
The older release history below is retained for reference.

VOICE NAVIGATOR 0.1.5 — TEST BUILD — 24 OCTOBER 2026
Part of Commander Thalinor's Navigator collaboration with ChatGPT, Claude and Gemini.

Offline Windows voice commands for Elite Dangerous, hosted by EDMarketConnector.
No VoiceAttack or cloud speech subscription is required. (Since 0.2.2 the
speech helper is built on your PC from the included VoiceHost.cs source; no
prebuilt .exe is shipped.)

NEW IN 0.1.5
- Hold an action continuously for up to 10 seconds, including scanner triggers.
- Main Voice panel and meter use EDMC's transparent background color.
- First-open sizes use the commander's tested reference dimensions: Commands
  1112x918, Edit Command 1026x690, action picker 818x653. Screen bounds still
  apply; Interface preserves existing user-saved sizes and positions.
- Global Dry run and its startup instructions are removed. Press Listen and
  focus Elite to use game input. Preview (no keys) remains a separate action.
  Legacy dry-run settings no longer silently prevent recognized game commands.

EARLIER IN 0.1.4 — FIRST-OPEN SIZE
Fresh windows fit their requested controls after layout, including larger fonts.
Navigator Interface now supplies the shared window service. With Interface 1.2.8,
first-use sizing is shared across ordinary EDMC/plugin popups. Saved user sizes
are preserved.

EARLIER IN 0.1.3 — ACTION PICKER AND POPUP MEMORY
Commands lists saved voice macros (ten starters), not every imported game action.
Add > Add Action shows the imported actions for the selected control section.
Actions lacking a keyboard binding are visible with their unavailable reason;
assign a keyboard shortcut in Elite before using one. Search and scrolling work
within this list. OK — Use Selected Action and Cancel stay outside the scrolling
area; double-click or Enter can also confirm a valid selected action.
With Navigator Interface 1.2.7, popup position/size are remembered across reopening
and restarts. Reset All Popup Windows to Defaults is in Interface Settings.
Navigator Interface is required and supplies popup styling and window memory.

EARLIER IN 0.1.2 — EDITOR DISPLAY FIXES
Popup windows use Navigator Interface's existing styling service when available,
with an independent fallback when it is absent. Tables follow the displayed font
height instead of clipping large text. Command/step buttons use two rows. Dark
mode includes the popup controls, caption and microphone-meter trough; returning
to Default restores native colors. Updates follow actual window/theme events.
Navigator Interface does not need replacing for this fix. Saved commands remain.

INSTALL
Close EDMC. Extract the Voice_Navigator folder into:
  %LOCALAPPDATA%\EDMarketConnector\plugins
Restart EDMC. Install only one copy of Voice_Navigator.
Existing suite plugin folders do not need replacing for this test.

GETTING STARTED
1. Connect your microphone and select it as the default Windows input device.
2. Open Macros > Listening Settings > Check Speech Engine.
3. Press Listen in the main Voice Navigator panel, then give Elite focus.
4. Say "galaxy map". The map opens using your imported keyboard binding.
5. Say it again to close it. Activity Log shows recognition and macro results.
6. Stop Listening when finished. Pause Radio narration during this first test
   so spoken articles do not interfere with recognition.

Voice Navigator will not focus the game for you. Macros > Preview (no keys)
checks a selected command without sending game input. The user's prior live
tests confirmed hardpoints and landing gear; individual bindings still depend
on your active Elite control profile.

COMMANDS AND EDITING
Ten starter macros have eighteen phrases. Commands show Ready, Disabled or
Unavailable based on their current imported bindings. Unavailable commands
remain editable; they cannot send keys. Assign a keyboard binding in Elite
and Reload Bindings to make one available. Gamepad-only actions are not
translated into gamepad input by this build.

Macros supports Add, Edit, Enable/Disable, Remove, Preview and Reload Bindings.
Phrases are one per line. Each command has a controls context and an optional
spoken reply. Steps may be binding actions or pauses, with hold/gap/repeat
settings and reordering. Supported state-aware toggles can request on/off
instead of blindly toggling. Duplicate enabled phrases are rejected.

The command prefix in Listening Settings is optional, and applies to EVERY
phrase when set: prefix "computer" makes "computer galaxy map" the command.
Language is blank by default to use Windows' installed default recognizer;
enter an installed culture such as en-US if needed. Confidence defaults to .72.
Changing listening settings saves them and restarts an active listener.
Closing a command editor without saving discards its draft.

Cancel Macro stops the current sequence and releases injected held keys.
Stop Listening also cancels the current macro. Keys are sent only while
EliteDangerous64.exe is in the foreground. State-aware ship commands wait
for live EDMC status and confirmation. Preview always sends no keys.

DATA AND PRIVACY
Active Elite binding files are read, never modified. All four active preset
sections are imported. An optional .binds override is available in Settings.
Your saved voice configuration lives outside the plugin folder:
  %LOCALAPPDATA%\EDMarketConnector\Voice_Navigator\settings.json
Speech processing stays on this PC. Microphone audio is not saved or uploaded.
The activity log contains the most recent recognized phrases and command
results in memory; it is not a microphone recording.
Listening is OFF at startup. Game input requires Listen and Elite focus.

TROUBLESHOOTING
- "Windows could not open the default microphone": connect/switch on the
  microphone and select it under Windows Settings > System > Sound > Input.
  Also check Windows microphone permissions for desktop applications.
- "No Windows desktop speech recognizer": install the Windows Speech
  component for the chosen language. Engine availability and microphone
  availability are separate checks.
- No matching command: check the prefix, phrases, enabled status and confidence.
- Unavailable binding: add a keyboard shortcut for that action in Elite.
- Keys rejected: Elite and EDMC must run at compatible privilege levels and
  Elite must keep focus. This test build does not change Windows permissions.

EARLY-BUILD LIMITS
No automatic start, free-form conversation, plugin-to-plugin Radio controls,
or imported commercial voice packs. Radio coexistence and live EDMC appearance
still need the commander's test. This build does not coordinate concurrent
game input with Neutron's map helper; leave that helper idle during testing.

The header has the suite's stock collapse control. Closing/collapsing a panel
does not imply a listening stop: press Stop Listening to stop the microphone.
To uninstall, close EDMC and move the Voice_Navigator plugin folder out of the
plugins directory. Configuration can remain for later reinstallation.
