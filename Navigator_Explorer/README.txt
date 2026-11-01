(N) Explorer 0.1.3 - TEST BUILD - 1 November 2026
NEW 0.1.3: Names follow the suite's capitals: Methane Dwarf Star, Icy Body, Neutron Star, Gas Giant with Water Based Life (every word capitalised except small joining words such as of, the, and, with). Sentences and messages keep a single capital at the start.
NEW 0.1.2: (1) No Highlighted Text inside the plugin: headings, the main star line, map marks and the status line are Normal Text (Highlighted Text stays on the panel header and tabs, where you can click). (2) The ship's flight path is kept apart from your ground track (on foot, in the SRV or landed). It is hidden by default; the Ship button (or the setting) shows it as a dotted, dimmer line, and the two lines never join. Points saved by 0.1.0 and 0.1.1 count as flight. (3) The map zooms out to 100 km.
NEW 0.1.1: (1) A system with nothing to scan says "Nothing here: no bodies to scan." once you have honked; it no longer keeps asking you to honk (Pioneer has the same quirk). After a honk that found bodies it says how many and to scan them. (2) No boxes: the values text and the map have no border, like Pioneer; the map shows a faint crosshair and a ring for the edge of the zoom range instead of a frame. (3) Capitals: Now, Max, Honk, Bio, Geo and the markers First Discovery, First Map, Mapped and Landable follow the suite's capitals.
NEW 0.1.0: first build. Exploration values and a surface map in one panel. Reads the journal and the game's own Status.json (through EDMC); sends nothing to the game and needs no web service.

VALUES TAB
- The current system at a glance, in the layout Pioneer made familiar: the system name, one line of tags and counts, the valuable bodies, unmapped biological signals, then every body with what it is worth now and at most, and the estimated system value at the bottom.
- Estimates use the community's published formula (MattG's exploration value thread) and agree with Pioneer's numbers. They are estimates: the game does not publish its rules, and the terraform bonus is shown as a range.
- The honk share counts once the main star is scanned. The Fully Scanned and Fully Mapped bonuses are listed, and count in the total once the system is complete.
- Valuable Bodies: planets you have not mapped yet whose best value reaches the minimum (default 800 kCr; change it in File > Settings > (N) Explorer). Each line gives the maximum value and the distance in ls.
- B# is bodies scanned out of bodies in the system (known after a honk), NB# is non-body objects.

TAGS (no emoji; short letters in brackets, like (F) elsewhere in the suite)
  (H)  honked        (S)  fully scanned        (M)  fully mapped
  (T)  terraformable [WW] body class letters (WW, ELW, AW, HMC, MR, R, RI, I, G-I ... G-V)
  Green tag  you were first.  Red (S) or (M) beside a body: someone had already scanned or mapped it.
  The colours come from (N) Interface and follow its accessibility setting (colouring off = plain text).

SURFACE TAB
- A map of where you have driven or walked on the current planet, drawn from the game's latitude, longitude and heading (north is up, the arrow is you).
- - and + zoom (100 m to 100 km from the centre to the edge). Mark drops a numbered bookmark where you stand; the four nearest list under the map with distance and bearing. Undo removes the last mark. Clear (tap twice) forgets this planet's map.
- Exobiology: each sample you log (Log / Sample) draws a dashed ring of the species' minimum distance round its spot, and the line under the map tells you if you are Too close and how far to walk. Finishing a species (Analyse) takes its rings down and leaves a dot.
- Everything is saved in EDMC's data folder \Navigator_Explorer (system.json and surface.json) and survives a restart.

NOT YET
- History across systems, sold/lost data and the galactic region name need ExploData (the plugin Pioneer and BioScan share). That is planned as an optional extra for the next build; this build works on its own.
- Nav beacon scans, footfall and the in-game overlay.

License and credits
Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"), licensed GPL-3.0-or-later (see LICENSE).
Humans + AI = Future. Built by Commander Thalinor in open collaboration with AI:
Claude (Anthropic), ChatGPT (OpenAI) and Gemini (Google). We say so proudly.
Parts adapted from Pioneer by Jeremy Rimpo (GPL-2.0-or-later); see NOTICE.txt and CREDITS.txt.
