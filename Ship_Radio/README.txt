Ship Radio 0.1.10 — TEST BUILD — 25 OCTOBER 2026
Required companion: Navigator Interface 1.2.10 or newer.
Compact track display and unchanged-icon guards; includes suite high-contrast preference.

Previous release notes are retained below.

Ship Radio 0.1.9 — 24 OCTOBER 2026
Required companion: Navigator Interface 1.2.9 or newer. Install it alongside
this plugin for shared EDMC layout fixes, popup styling and window memory.
This increment documents the suite dependency; plugin behavior is unchanged.

Release notes / current AI handoff: shared workspace AI_HANDOFF.md.
The older release history below is retained for reference.

SHIP RADIO 0.1.8 - TEST BUILD - 2026-10-22
Part of the Navigator suite for EDMC.
Coded by Claude, with ChatGPT and Gemini, and Commander Thalinor.

Visible header: Radio. When collapsed: Radio  |  playback controls.
Radio deliberately omits (Hidden); other suite plugins are unchanged.
Project, EDMC settings name and plugin folder remain Ship Radio / Ship_Radio.

NEW IN 0.1.8: SHOW ONLY SUPPORTED PLAYBACK OPTIONS
Repeat and Shuffle are hidden in Streams, Distant Radio and Galnet. They appear
for local music only when usable: Repeat needs one loaded track, Shuffle needs
two. OFF options remain visible when supported so they can be switched ON.
An empty, unavailable or still-scanning folder hides both until usable music is
loaded. Saved Repeat/Shuffle settings are retained when switching modes.
The remaining controls recenter without empty button slots in both the expanded
row and collapsed Radio header. This uses existing source/queue update events,
not a stream probe, theme watchdog, new timer or periodic capability check.

NEW IN 0.1.7: INTERNET PLAYLIST GROUPS
Streams mode retains each imported PLS/M3U file as a playlist group:
  Previous / Next: tune the previous/next station URL inside this playlist.
  Down / Up: switch between playlists. Both levels wrap at their ends.
The last station is remembered separately for each playlist, across restarts.
One station disables Previous/Next; one playlist disables Down/Up. Changing
selection while stopped/paused does not start playback; playing streams retune.
The same controls work when collapsed in the Radio header. Repeat/Shuffle stay
local-music-only. This never seeks or skips a track inside a live broadcast.

Settings keeps one scrollable list with Playlist and Station columns. Filtering
matches either column. Import names the group after the file (browser duplicate
suffixes such as (1) are ignored). Re-importing the same file/group and URL does
not duplicate its stations. Removing every station in a group removes that group
from the playlist cycle; removing entries never changes the original PLS/M3U.

UPGRADING EXISTING STREAM IMPORTS
Older builds flattened the playlists and did not save group identities. Those
entries remain safely available as Custom Streams. Re-import your playlists once
in File > Settings > Ship Radio, then Apply/OK to restore their groups by exact
URL matches. You do not need to delete old stations first. Unmatched old links and
manually added links remain in Custom Streams. Different groups may deliberately
contain the same URL. Existing Galnet, Distant Radio and local-music controls keep
their previous behavior. No theme checks, provider calls or playback timers added.

The lower station / track information row and its spacing are unchanged.
Tested with all three supplied private playlists without opening their streams;
listener keys remain private and are never included in the release archive.

INSTALL
Close EDMC. Extract Ship_Radio into EDMC's plugins folder, replacing the same
folder. Restart EDMC. Do not install a second copy beside the existing one.
Settings, private stations and caches live separately in EDMC application data.
This build preserves existing settings and uses Windows' built-in audio/voice.

THE PANEL
Header: Radio, unread-Galnet dot, stock collapse button (plus controls when collapsed). The settings cog is
removed: all configuration is under File > Settings > Ship Radio.
First body line: source  |  available matching controls, centered as one compact
group across the panel. There is no fixed split or expanding source column.
Changing source keeps the entire group centered; the lower line is unchanged.
Second body line: current article/song information, never wrapped.
Galnet and Distant Radio retain v0.1.3's full-width title line. Streams and
Music retain station (35%, left)  |  track (65%, right), excluding divider width.
Long text holds, slides to show the end, holds, then returns to its beginning.

- Click source to cycle Galnet / Distant Radio / Streams / Music. The last
  two appear once their station lists contain entries.
- Previous / Next select a station within the playlist in Streams mode; their
  Galnet/local-music behavior is retained. Play/Pause retains its behavior. Play/Pause shows
  Pause while playing/tuning, Play while stopped/paused. Live radio resumes live.
- Down / Up change playlist in Streams mode; elsewhere they change station
  within the selected source. A music folder is one
  station, with all its supported files and subfolders in one playlist.
- Repeat, after the station arrows: Off -> Track -> Station -> Off.
  Off uses Normal Text; Track and Station use Highlighted Text. Track adds a
  small 1 to the loop graphic. Station loops the selected folder's playlist.
  Off stops at the end of that playlist. Default is Station.
- Shuffle, last: crossing arrows. Highlighted when usable (Music with at least
  two tracks); Hidden when unavailable. A small check marks shuffle ON.
  Toggling it preserves the current song and reorders only what comes next.
- Repeat/Shuffle apply only to Music. They are saved in settings.json and
  restored between sessions; there are deliberately no checkboxes/dropdowns
  for either in EDMC Settings. Manual Next/Previous still choose another track
  even when Repeat Track is selected.
- All icons share a cell size and adapt to the available row width. The button
  strip stays within roughly half the panel; the source/divider/controls group is centered. Theme changes
  use actual UI events; no recurring theme watchdog has been added.
- Wheel changes radio/music volume; over Galnet it changes voice volume.
- Collapsing hides the panel body and moves the SAME supported playback controls
  into the centered header: Radio  |  controls. They keep working, with the
  same enabled/disabled states, repeat/shuffle modes, theme and keyboard access.
  The stock expand/collapse button stays at the far right in its own cell.
  Expanding moves the controls back to their usual source/control row and
  removes the header divider. Playback is not restarted and no duplicate
  controls or new polling/theme timers are created. Collapsed state is remembered.

EDMC SETTINGS: FILE > SETTINGS > SHIP RADIO
One standard scrollable page, with vertical scrollbar. Both station lists
also have standard vertical/horizontal scrollbars. Wheel over a list scrolls
that list; wheel over other settings scrolls the page. Changes commit through
EDMC Apply/OK. Closing/cancelling discards edits not previously applied.

Local Music
  Add multiple folders. Each station is named after its selected folder.
  The list shows station name, full folder path and supported-file count.
  Add Folder / Remove Selected / Rescan Selected. Removing entries never
  deletes music. Multiple selections are supported for removal/rescanning.
  Scans run in background workers at selection/settings load, or on Rescan;
  there are no repeating filesystem scans. Readable subfolders are included,
  unreadable subfolders are skipped, and there is no fixed 5,000-track ceiling.
  Unavailable roots remain in the list and can be rescanned when reconnected.
  Adding an unrelated station does not restart current playback. Removing the
  current station stops it. Duplicate folder locations are not added twice.

Internet Radio
  Filter playlist/station names; Import Playlist (.pls/.m3u); Add Link; Rename;
  Remove Selected. Names are shown, private listener links are not.
  The Playlist column shows grouping; stream links and listener keys are hidden.
  Removing filtered entries removes the selected station, not another index.
  Distant Radio data saver remains available. HLS playlists are not supported.

Galnet Voice
  Enabled installed Windows voices are loaded asynchronously when Settings
  opens. Refresh Voices reloads that list. Windows Default is always an option.
  Speaking Speed: -10 to +10, 0 = Normal.
  Pitch: -50% to +50%, 0 = Normal. Pitch is requested through Windows speech
  markup and its audible effect depends on the selected installed voice.
  Voice Volume is independent of radio/music volume.
  Preview Voice / Stop Preview / Reset Voice Defaults. Preview uses a separate
  helper and does not stop the main radio or consume/mark a Galnet article.
  The preview helper closes after enumeration/preview or when Settings closes.
  Voice changes apply to subsequent articles; Preview uses the draft values.
  Play Only Unread Galnet Articles (default OFF) skips articles already marked
  heard. An article is marked heard when started, as in prior builds; this is
  not a guarantee it was listened to in full. Manual track controls remain usable.

Playback
  Radio/Music Volume; Autoplay on EDMC startup (default OFF); Pause on game
  shutdown (default ON); Remember Local Music Track And Position (default OFF).
  Position memory is per folder station and saves on pause, source/station
  change and clean EDMC shutdown. It never starts audio by itself. Resume uses
  the same file if it still exists; otherwise the station starts normally.
  No playback history is reconstructed and abrupt crashes can lose recent position.

PLAYBACK AND PRIVACY
Windows Media Player's control handles supported local audio codecs; available
formats depend on Windows/codecs. Windows N editions may need Media Feature Pack.
Galnet uses installed Windows speech voices, with no cloud voice subscription.
The existing hidden-helper message pump and private loopback stream handoff
are retained from v0.1.3. ICY metadata is separated from audio; when absent,
internet radio shows Track Unknown. No audio is recorded to disk.
Private URLs (including listener keys) stay in EDMC's ShipRadio application-data
folder, including stations.json and possibly settings.json. Do not share those
files if they contain private keys. They are never included in release ZIPs.
Voice preview and folder scans do not contact online music services.
Galnet data: cms.zaonce.net. Distant Radio metadata: radio.distantworlds3.space.
Your own streams contact their selected servers. No new metadata polling added.

VALIDATION
Automated Windows/Tk checks cover collapsed startup, working header controls,
repeat collapse/expand and collapse-button clearance, plus layout/colours at narrow/wide widths and
larger fonts, settings staging/apply/cancel, lists/filter/remove, background
folder scans, repeat/shuffle, unread Galnet, and saved local-track positions.
Real muted Windows checks cover voice enumeration, selected voice, rate/pitch
markup, XML escaping, pause/resume/stop, local WAV playback/seek/end, and live
Distant Radio playback with track metadata. Live EDMC testing remains necessary.

CREDITS
Distant Radio - the official radio of Distant Worlds 3
(https://distantworlds3.space/radio/). Ship Radio plays their public streams
with their permission. All credit for the station, its DJs and shows belongs to
Distant Radio. Ship Radio does not claim the stream as its own.
Galnet is Frontier Developments' in-universe news service.

ABOUT AND TERMS
Coded by Claude, with ChatGPT and Gemini, and Commander Thalinor.

You can use this plugin freely for your own personal, non-commercial use.
You can distribute it freely as long as the code has not been modified and
you do not claim it's your own work. You may NOT sell this plugin, use this
plugin for commercial use, or use its code in your projects without prior
authorization.

Human + AI = Future


High Contrast Backgrounds (25 October 2026)
High Contrast Background is available on this plugin's EDMC settings page
and defaults off. Navigator Interface applies it and can force it on for all
main plugin panels. Turning off the force option restores individual choices.
