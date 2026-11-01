# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Ship Radio: a compact EDMC media panel - Galnet read aloud, Distant Radio
(Distant Worlds 3), your own internet streams and music folders.

Part of the Navigator suite. Playback uses Windows' own media player and voice
through a hidden helper (engine.py); this file is the panel, settings and logic.
"""
from __future__ import annotations

import json
import copy
import random
import sys
import logging
import os
import queue
import tempfile
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, simpledialog
from typing import Any

import myNotebook as nb
from config import appname, config

try:
    from . import sources, stream_groups
    from .engine import Engine
except ImportError:                     # loaded without its package (tests)
    import sources  # type: ignore[no-redef]
    import stream_groups
    from engine import Engine  # type: ignore[no-redef]

logger = logging.getLogger(f"{appname}.{os.path.basename(os.path.dirname(__file__))}")

TITLE = "(N) Radio"
HEADER_TITLE = "Radio"
VERSION = "0.1.15"
SEP = "  |  "
SOURCES = ("galnet", "dw3", "streams", "music")
SOURCE_LABELS = {"galnet": "Galnet", "dw3": "Distant Radio", "streams": "Streams", "music": "Music"}
# Sources whose information line is one full-width title (no station column).
SINGLE_LINE_SOURCES = ("galnet", "dw3")
DEFAULT_SETTINGS: dict[str, Any] = {
    "source": "dw3",
    "station": {},            # source -> station id
    "stream_playlist": "",     # active internet playlist
    "stream_station": {},      # playlist -> last selected station URL
    "volume": 60,
    "autoplay": False,
    "shuffle": False,
    "repeat": "station",
    "resume_music": False,
    "music_resume": {},
    "galnet_unread": False,
    "voice": "",
    "voice_rate": 0,
    "voice_pitch": 0,
    "voice_volume": 60,
    "data_saver": False,
    "pause_on_shutdown": True,
    "galnet_heard": [],
    "collapsed": False,
}
ABOUT_TEXT = (
    "(N) Radio - part of the Navigator suite.\n\n"
    "Coded by Claude, with ChatGPT and Gemini, and Commander Thalinor.\n\n"
    "Galnet articles: Frontier Developments' Galnet, read aloud by your Windows voice.\n"
    "Distant Radio: " + sources.DW3_CREDIT + ". Streams are Distant Radio's own public links; "
    "all credit for the station and its shows belongs to them.\n\n"
    "Human + AI = Future"
)

DATA_DIR = ""
SETTINGS_PATH = ""
STATIONS_PATH = ""
CACHE_PATH = ""

_settings: dict[str, Any] = dict(DEFAULT_SETTINGS)
_library: dict[str, list] = {"streams": [], "folders": []}
_galnet: list[dict] = []
_dw3: list[dict] = [dict(item) for item in sources.DW3_FALLBACK]
_engine = Engine()
_results: queue.Queue = queue.Queue()
_jobs_pending = 0

# playback state (main thread only)
_state = "stopped"            # stopped | loading | playing | paused
_tracks: list = []            # current station's files / articles
_track = 0
_position = 0.0
_title_now = ""               # live title from the stream / DW3 API
_playing_key: tuple | None = None
_next_np_poll = 0.0
_flash_text = ""
_flash_until = 0.0
_marquee = 0
_marquee_needed = False
_marquee_start: dict = {}      # label -> (text, tick it started showing)
_info_mode = ""               # "galnet" = one full-width title, "split" = station | track
_tick_job = None
_stopped = False

# widgets
_app_frame = _header_frame = _title_label = _cog_button = _collapse_button = None
_body = _source_label = _now_label = _station_label = _info_row = _info_sep = None
_controls: list = []
_theme_controls: list = []
_theme_bindings: list = []
_gear_image = None
_theme_pending = None
_theme_signature = None
_prefs: dict[str, Any] = {}
_settings_view = None
_music_cache = {}
_music_pending = {}
_music_versions = {}
_music_start = None
_music_deferred = False
_resume_seek = None
_controls_frame = _buttons_frame = _header_sep = None
_compact_track_sep = _compact_track_label = None

# =========================================================================== files
def _write_json(path: str, data: Any) -> None:
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=folder, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2)
        os.replace(temp, path)
    except BaseException:
        try:
            os.unlink(temp)
        except OSError:
            pass
        raise


def _read_json(path: str, default: Any) -> Any:
    try:
        with open(path, encoding="utf-8") as stream:
            return json.load(stream)
    except FileNotFoundError:
        return default
    except (OSError, ValueError):
        logger.exception("Ship Radio: could not read %s", os.path.basename(path))
        return default


def _load_settings() -> None:
    global _settings, _library
    saved = _read_json(SETTINGS_PATH, {})
    _settings = copy.deepcopy(DEFAULT_SETTINGS)
    if isinstance(saved, dict):
        _settings.update({k: saved[k] for k in DEFAULT_SETTINGS if k in saved})
    if isinstance(saved, dict) and 'voice_volume' not in saved:
        _settings['voice_volume'] = _settings.get('volume',60)
    for key, low, high in (('volume',0,100),('voice_volume',0,100),('voice_rate',-10,10),('voice_pitch',-50,50)):
        try: _settings[key] = max(low,min(high,int(_settings[key])))
        except (TypeError,ValueError): _settings[key] = DEFAULT_SETTINGS[key]
    if _settings.get('repeat') not in ('off','track','station'): _settings['repeat']='station'
    if not isinstance(_settings.get('music_resume'),dict): _settings['music_resume']={}
    if _settings.get("source") not in SOURCES:
        _settings["source"] = "dw3"
    if not isinstance(_settings.get("station"), dict):
        _settings["station"] = {}
    if not isinstance(_settings.get('stream_station'),dict):_settings['stream_station']={}
    if not isinstance(_settings.get('stream_playlist'),str):_settings['stream_playlist']=''
    library = _read_json(STATIONS_PATH, {})
    _library = {"streams": [], "folders": []}
    if isinstance(library, dict):
        for key in _library:
            values=library.get(key, [])
            _library[key] = [item for item in values if isinstance(item, dict)] if isinstance(values,list) else []
    _library['streams']=stream_groups.normalize(_library['streams'])


def _save_settings() -> None:
    try:
        _write_json(SETTINGS_PATH, {k: _settings[k] for k in DEFAULT_SETTINGS})
    except OSError:
        logger.exception("Ship Radio: could not save settings")


def _save_library() -> None:
    # Stream links can carry private listener keys. They are kept only here,
    # in EDMC's application data, never in the plugin folder or the log.
    try:
        _write_json(STATIONS_PATH, _library)
    except OSError:
        logger.exception("Ship Radio: could not save stations")


# =========================================================================== stations
def _stream_playlist() -> str:
    groups=stream_groups.playlists(_library['streams'])
    wanted=_settings.get('stream_playlist','')
    for group in groups:
        if group.casefold()==wanted.casefold():return group
    # Preserve the old flattened selection when first migrating/re-importing.
    old=_settings['station'].get('streams')
    for item in _library['streams']:
        if old and item.get('url')==old:return stream_groups.group_name(item)
    return groups[0] if groups else ''


def _stations(source: str) -> list[dict]:
    if source == "galnet":
        return [{"id": "galnet", "name": "Galnet News"}]
    if source == "dw3":
        return _dw3
    if source == "streams":
        group=_stream_playlist().casefold()
        return [{"id": s.get("url", ""), "name": s.get("name", "Stream"), "url": s.get("url", "")}
                for s in _library["streams"] if s.get("url") and stream_groups.group_name(s).casefold()==group]
    return [{"id": f.get("path", ""), "name": os.path.basename(os.path.normpath(f.get("path", ""))) or f.get("path") or "Music",
             "path": f.get("path", "")} for f in _library["folders"] if f.get("path")]


def _station_index(source: str | None = None) -> int:
    source = source or _settings["source"]
    stations = _stations(source)
    wanted = (_settings.get('stream_station',{}).get(_stream_playlist(),_settings['station'].get(source))
              if source=='streams' else _settings['station'].get(source))
    for index, station in enumerate(stations):
        if station["id"] == wanted:
            return index
    return 0


def _current_station() -> dict | None:
    stations = _stations(_settings["source"])
    return stations[_station_index()] if stations else None


def _select_station(source: str, index: int) -> None:
    stations = _stations(source)
    if stations:
        _settings["station"][source] = stations[index % len(stations)]["id"]
        if source=='streams':
            _settings['stream_playlist']=_stream_playlist()
            _settings['stream_station'][_stream_playlist()]=_settings['station'][source]


def _available_sources() -> list[str]:
    return [s for s in SOURCES if s in ("galnet", "dw3") or _stations(s)]


# =========================================================================== workers
def _run_job(kind: str, function, *args) -> None:
    """Network work off the Tk thread; results come back through _results."""
    global _jobs_pending
    _jobs_pending += 1

    def work() -> None:
        try:
            _results.put((kind, function(*args), None))
        except Exception as error:          # reported on the Tk thread
            _results.put((kind, None, error))
    threading.Thread(target=work, name=f"ShipRadio-{kind}", daemon=True).start()
    _schedule_tick()


def _refresh_galnet() -> None:
    _run_job("galnet", sources.fetch_galnet, 20)


def _handle_result(kind: str, value: Any, error: Exception | None) -> None:
    global _galnet, _dw3, _title_now
    if kind == "music":
        _finish_music_scan(value)
        return
    if kind == "galnet":
        if error is not None:
            logger.warning("Ship Radio: Galnet unavailable (%s)", type(error).__name__)
            if not _galnet:
                _flash("Galnet unavailable - try again later")
            return
        if value:
            _galnet = value
            try:
                _write_json(CACHE_PATH, {"galnet": _galnet, "dw3": _dw3})
            except OSError:
                pass
            if _settings["source"] == "galnet" and _state == "stopped":
                _load_tracks()
    elif kind == "dw3":
        if error is None and value:
            _dw3 = value
    elif kind == "np":
        station_id, text = value if error is None and value else (None, "")
        station = _current_station()
        if station_id and station and station.get("id") == station_id and _settings["source"] == "dw3":
            _title_now = text
    _refresh()


# =========================================================================== playback
def _folder_key(path):
    return os.path.normcase(os.path.abspath(os.path.normpath(path)))


def _request_music_scan(path, force=False):
    key = _folder_key(path)
    if key in _music_pending and not force:
        return
    generation = _music_versions.get(key,0)+1
    _music_versions[key]=generation
    _music_pending[key]=generation
    def scan():
        try: return key,generation,sources.scan_folder(path),''
        except OSError: return key,generation,[],'Unavailable'
    _run_job('music',scan)


def _finish_music_scan(result):
    global _tracks,_track,_music_start
    if not result:
        return
    key,generation,files,error=result
    if _music_versions.get(key) != generation:
        return
    _music_pending.pop(key,None)
    _music_cache[key]={'tracks':files,'error':error}
    station=_current_station()
    if _settings['source']=='music' and station and _folder_key(station['path'])==key:
        current=_tracks[_track] if _tracks and _track<len(_tracks) else None
        if _state not in ('playing','paused'):
            _install_music(files,station)
        elif current is not None:
            # Rescanning keeps the current song and its position.
            remaining=[f for f in files if f not in _tracks[:_track+1]]
            if _settings['shuffle']: random.shuffle(remaining)
            _tracks=_tracks[:_track+1]+remaining
        if _music_start==key:
            _music_start=None
            if files and not error:
                _play_current()
            else:
                _stop()
                _flash('Folder Unavailable' if error else 'No Supported Music Files')
    if _settings_view is not None and _settings_view.alive():
        _settings_view.refresh_folders()
    _refresh()


def _install_music(files,station):
    global _tracks,_track,_resume_seek
    _tracks=list(files);_track=0;_resume_seek=None
    bookmark=_settings['music_resume'].get(_folder_key(station['path']),{}) if _settings['resume_music'] else {}
    selected=bookmark.get('track')
    if _settings['shuffle']: random.shuffle(_tracks)
    if selected in _tracks:
        _track=_tracks.index(selected)
        try: _resume_seek=max(0,float(bookmark.get('position',0)))
        except (TypeError,ValueError): _resume_seek=None


def _load_tracks() -> None:
    global _tracks,_track,_resume_seek
    source,station=_settings['source'],_current_station()
    _tracks=[];_track=0;_resume_seek=None
    if source=='galnet':
        heard=set(_settings.get('galnet_heard',[]))
        _tracks=[a for a in _galnet if not _settings['galnet_unread'] or a['id'] not in heard]
    elif source=='music' and station:
        key=_folder_key(station['path'])
        cached=_music_cache.get(key)
        if cached is not None:
            _install_music(cached['tracks'],station)
        else:
            _request_music_scan(station['path'])


def _remember_music():
    if _settings.get('resume_music') and _playing_key and _playing_key[0]=='music' and _tracks:
        _settings['music_resume'][_folder_key(_playing_key[1])]={'track':_tracks[_track % len(_tracks)],'position':max(0,_position)}


def _cycle_repeat():
    if _settings['source']!='music' or not _tracks:return
    modes=('off','track','station')
    _settings['repeat']=modes[(modes.index(_settings['repeat'])+1)%3]
    _save_settings();_refresh()


def _toggle_shuffle():
    global _tracks
    if _settings['source']!='music' or len(_tracks)<2:return
    _settings['shuffle']=not _settings['shuffle']
    tail=_tracks[_track+1:]
    if _settings['shuffle']:random.shuffle(tail)
    else:tail.sort(key=sources._natural_key)
    _tracks=_tracks[:_track+1]+tail
    _save_settings();_refresh()


def _play_current() -> None:
    """Start whatever is selected: stream, track or Galnet article."""
    global _state, _title_now, _playing_key, _next_np_poll, _position, _music_start, _music_deferred
    source, station = _settings["source"], _current_station()
    _title_now, _position = "", 0.0
    if not Engine.available():
        _flash("(N) Radio plays audio on Windows only")
        return
    if station is None:
        _flash("No stations here yet - add them in Settings")
        return
    if source == "galnet":
        if _state=="stopped" and _settings["galnet_unread"]:_load_tracks()
        if not _galnet:
            _refresh_galnet()
            _flash("Fetching Galnet…")
            return
        if not _tracks:
            _load_tracks()
        if not _tracks:
            _flash('No Unread Galnet Articles' if _settings['galnet_unread'] else 'No Galnet Articles')
            return
        article = _tracks[_track % len(_tracks)]
        ok = _engine.send("speak", text=sources.galnet_speech(article), rate=_settings['voice_rate'],
                          pitch=_settings['voice_pitch'],voice=_settings['voice'],volume=_settings['voice_volume'])
        heard = [i for i in _settings.get("galnet_heard", []) if i != article["id"]]
        _settings["galnet_heard"] = (heard + [article["id"]])[-60:]
    elif source == "music":
        if not _tracks:
            _load_tracks()
        if not _tracks:
            key=_folder_key(station['path'])
            if key in _music_pending:
                _music_start=key;_music_deferred=True
                _state='loading';_playing_key=('music',station['id'])
                _refresh();return
            _flash('Folder Unavailable' if _music_cache.get(key,{}).get('error') else 'No Supported Music Files')
            return
        _music_deferred=False;_music_start=None
        ok = _engine.send("play", url=_tracks[_track % len(_tracks)])
    else:
        url = station.get("saver") if source == "dw3" and _settings.get("data_saver") else station.get("url")
        ok = _engine.send("play", url=url)
        if source == "dw3":
            _next_np_poll = 0.0
    if not ok:
        _flash("Could not start Windows audio - see the EDMC log")
        return
    _engine.send("volume", value=int(_settings.get("volume", 60)), voice_value=_settings["voice_volume"])
    _state = "loading"
    _playing_key = (source, station["id"])
    _save_settings()
    _schedule_tick()
    _refresh()


def _is_live_stream() -> bool:
    return _settings["source"] in ("dw3", "streams")


def _play_pause() -> None:
    global _state,_music_start
    if _settings['source']=='music' and _music_deferred:
        if _state=='loading':
            _music_start=None;_state='paused';_refresh()
        else:_play_current()
        return
    if _state in ("playing", "loading"):
        if _is_live_stream():
            _engine.send("stop")          # a paused radio resumes live, like a real radio
        else:
            _engine.send("pause")
        _state = "paused"
        _remember_music();_save_settings()
    elif _state == "paused" and _playing_key == (_settings["source"], (_current_station() or {}).get("id")):
        if _is_live_stream():
            _play_current()
            return
        _engine.send("resume")
        _state = "playing"
    else:
        _play_current()
        return
    _refresh()


def _stop() -> None:
    global _state, _title_now, _playing_key, _music_start, _music_deferred
    _remember_music();_music_start=None;_music_deferred=False
    if _engine.running():
        _engine.send("stop")
    _state, _title_now, _playing_key = "stopped", "", None
    _save_settings()
    _refresh()


def _step_track(direction: int) -> None:
    global _track,_resume_seek
    _remember_music();_resume_seek=None
    if _settings['source']=='streams':
        _step_stream_station(direction)
        return
    if _settings["source"] not in ("galnet", "music"):
        return
    if not _tracks:
        _load_tracks()
    if not _tracks:
        return
    if direction < 0 and _position > 3 and _settings["source"] == "music" and _state in ("playing", "paused"):
        _engine.send("seek", pos=0)       # stereo behaviour: first press restarts the track
        return
    _track = (_track + direction) % len(_tracks)
    if _state in ("playing", "loading", "paused"):
        _play_current()
    else:
        _refresh()


def _step_stream_station(direction: int) -> None:
    stations=_stations('streams')
    if len(stations)<2:return
    target=(_station_index('streams')+direction)%len(stations)
    continuing=_state in ('playing','loading')
    _stop()
    _select_station('streams',target)
    _load_tracks();_save_settings()
    if continuing:_play_current()
    else:_refresh()


def _step_stream_playlist(direction: int) -> None:
    groups=stream_groups.playlists(_library['streams'])
    if len(groups)<2:return
    old=_stream_playlist()
    current=_current_station()
    if current:_settings['stream_station'][old]=current['id']
    target=groups[(groups.index(old)+direction)%len(groups)]
    continuing=_state in ('playing','loading')
    _stop()
    _settings['stream_playlist']=target
    _select_station('streams',_station_index('streams'))
    _load_tracks();_save_settings()
    if continuing:_play_current()
    else:_refresh()


def _step_station(direction: int) -> None:
    source = _settings["source"]
    if source=='streams':
        _step_stream_playlist(direction)
        return
    stations = _stations(source)
    if len(stations) < 2:
        _flash("Only one station here" if stations else "No stations here yet")
        return
    continuing=_state in ("playing","loading")
    _stop()
    _select_station(source, _station_index() + direction)
    _load_tracks()
    _save_settings()
    if continuing:
        _play_current()
    else:
        _stop()
    if source in SINGLE_LINE_SOURCES or source == "music":
        _flash((_current_station() or {}).get("name", ""), 3.0)   # say where the tuner landed


def _cycle_source(_event=None) -> None:
    order = _available_sources()
    current = _settings["source"]
    continuing=_state in ("playing","loading")
    _stop()
    _settings["source"] = order[(order.index(current) + 1) % len(order)] if current in order else order[0]
    _load_tracks()
    _save_settings()
    if _settings["source"] == "galnet" and not _galnet:
        _refresh_galnet()
    if continuing:
        _play_current()
    else:
        _stop()


def _handle_engine(event: dict) -> None:
    global _state, _position, _title_now, _resume_seek
    kind = event.get("ev")
    if kind == "state":
        reported = event.get("state")
        _position = float(event.get("pos") or 0)
        if reported == "ended":
            if _state not in ("playing","loading"): return
            _on_ended()
            return
        if reported in ("playing", "loading") and _state in ("playing", "loading"):
            _state = reported
            if reported=='playing' and _resume_seek is not None and _settings['source']=='music':
                seek=_resume_seek;_resume_seek=None
                if seek>0:_engine.send('seek',pos=seek)
        elif reported == "paused" and _state != "stopped":
            _state = "paused"
        title = str(event.get("title") or "").strip()
        if _settings["source"] == "streams" and title:
            _title_now = title
    elif kind == "metadata":
        _title_now = str(event.get("title") or "").strip()
    elif kind == "notice":
        _flash(str(event.get("msg") or "Voice Setting Unavailable"))
    elif kind == "error":
        what, message = event.get("what"), str(event.get("msg") or "")
        logger.warning("Ship Radio: Windows %s reported: %s", what, message[:200])
        if what in ("media", "play", "speak"):
            _state = "stopped"
            _flash("Could not play that - check the link or file")
        elif what in ("player", "voice"):
            _flash("Windows Media Player or voice is unavailable")
    elif kind == "exit" and _state != "stopped" and not _stopped:
        _state = "stopped"
        _flash("Audio helper closed")
    _refresh()


def _on_ended() -> None:
    global _track,_state,_position,_resume_seek
    source=_settings['source'];_position=0;_resume_seek=None
    if source=='music' and _tracks:
        mode=_settings['repeat']
        if mode=='track':
            _play_current();return
        if _track+1>=len(_tracks):
            if mode=='off':
                _remember_music();_state='stopped';_save_settings();_flash('End Of Station');return
            if _settings['shuffle']:
                previous=_tracks[_track];random.shuffle(_tracks)
                if len(_tracks)>1 and _tracks[0]==previous:_tracks.append(_tracks.pop(0))
        _track=(_track+1)%len(_tracks)
        _play_current()
    elif source=='galnet' and _tracks:
        next_track=_track+1
        heard=set(_settings.get('galnet_heard',[]))
        while next_track<len(_tracks) and _settings['galnet_unread'] and _tracks[next_track]['id'] in heard:
            next_track+=1
        if next_track>=len(_tracks):
            _state='stopped';_flash('End Of Galnet');return
        _track=next_track;_play_current()
    else:
        _state='stopped';_flash('Stream Ended - Press Play To Reconnect')


# =========================================================================== timer
def _schedule_tick() -> None:
    global _tick_job
    if _tick_job is None and _app_frame is not None and not _stopped:
        _tick_job = _app_frame.after(250, _tick)


def _tick() -> None:
    """Drain engine/worker results; keep running only while something is active."""
    global _tick_job, _jobs_pending, _marquee, _next_np_poll
    _tick_job = None
    if _stopped or not _widget_alive(_app_frame):
        return
    for event in _engine.drain():
        _handle_engine(event)
    while True:
        try:
            kind, value, error = _results.get_nowait()
        except queue.Empty:
            break
        _jobs_pending = max(0, _jobs_pending - 1)
        _handle_result(kind, value, error)
    if _settings["source"] == "dw3" and _state in ("playing", "loading") and time.monotonic() >= _next_np_poll:
        station = _current_station()
        if station:
            _next_np_poll = time.monotonic() + 20
            _run_job("np", lambda sid=station["id"]: (sid, sources.fetch_dw3_now_playing(sid)))
    _marquee += 1
    _refresh_now()
    if _engine.running() or _jobs_pending or _flash_until > time.monotonic() or _state != "stopped" or _marquee_needed:
        _schedule_tick()


def _flash(text: str, seconds: float = 4.0) -> None:
    global _flash_text, _flash_until
    _flash_text, _flash_until = text, time.monotonic() + seconds
    _refresh_now()
    _schedule_tick()


# =========================================================================== display
def _now_parts() -> tuple[str, str]:
    source, station = _settings["source"], _current_station()
    name = station["name"] if station else "No Stations"
    if _flash_until > time.monotonic():
        return name, _flash_text
    if station is None:
        return name, "Add In Settings"
    if _state == "loading":
        return name, "Tuning…"
    if source == "galnet":
        if not _galnet:
            return name, "No Articles Yet"
        articles = _tracks or _galnet
        article = articles[_track % len(articles)]
        return name, f"{_track % len(articles) + 1}/{len(articles)}: {article['title']}"
    if source == "music" and _tracks:
        return name, sources.track_title(_tracks[_track % len(_tracks)])
    if _state in ("playing", "paused"):
        return name, _title_now or ("Track Unknown" if _state == "playing" else "Paused")
    return name, name if source == "dw3" else "Stopped"


def _now_text() -> str:
    return SEP.join(_now_parts())


def _layout_info() -> None:
    """Galnet: the article title gets the whole line (every station is Galnet).
    Other sources: station (35%)  |  track (65%)."""
    global _info_mode
    if not _widget_alive(_info_row):
        return
    mode = "galnet" if _settings["source"] in SINGLE_LINE_SOURCES else "split"
    if mode == _info_mode:
        return
    _info_mode = mode
    _marquee_start.clear()
    if mode == "galnet":
        _station_label.grid_remove()
        _info_sep.grid_remove()
        _now_label.grid_configure(column=0, columnspan=3)
        _now_label.configure(anchor=tk.W)
    else:
        _station_label.grid()
        _info_sep.grid()
        _now_label.grid_configure(column=2, columnspan=1)
        _now_label.configure(anchor=tk.E)
    _size_now_line()


def _size_now_line(event=None) -> None:
    if _settings.get('collapsed'):
        _refresh_now()
        return
    if not _widget_alive(_info_row):
        return
    font = tkfont.Font(font=_now_label.cget("font"))
    width = event.width if event is not None else _info_row.winfo_width()
    if _info_mode == "galnet":
        _info_row.columnconfigure(0, minsize=0, weight=1)
        _info_row.columnconfigure(2, minsize=0, weight=0)
    else:
        usable = max(1, width - font.measure(SEP))
        _info_row.columnconfigure(0, minsize=round(usable * .35), weight=0)
        _info_row.columnconfigure(2, minsize=max(1, usable - round(usable * .35)), weight=0)
    _refresh_now()


def _ticker(label, text: str) -> str:
    """One clean line that never wraps around on itself: hold at the start,
    slide left until the end is visible, hold, then return to the start."""
    global _marquee_needed
    try:
        font = tkfont.Font(font=label.cget("font"))
        width = label.winfo_width()
    except tk.TclError:
        return text
    if width <= 20 or font.measure(text) <= width:
        _marquee_start.pop(str(label), None)
        return text
    _marquee_needed = True
    shown, started = _marquee_start.get(str(label), ("", 0))
    if shown != text:
        _marquee_start[str(label)] = (text, _marquee)
        started = _marquee
    furthest = 0
    while furthest < len(text) - 1 and font.measure(text[furthest:]) > width:
        furthest += 1
    hold = 6                                   # about 1.5 s at each end
    step = (_marquee - started) * 3 // 4       # about 3 characters a second
    position = step % (hold + furthest + hold)
    offset = 0 if position < hold else min(furthest, position - hold)
    return text[offset:]


def _refresh_now() -> None:
    global _marquee_needed
    _marquee_needed = False
    if not _widget_alive(_now_label) or not _widget_alive(_station_label):
        return
    if _settings.get('collapsed'):
        if _widget_alive(_compact_track_label) and _compact_track_label.winfo_manager():
            text = _ticker(_compact_track_label, ' '.join(str(_now_parts()[1]).split()))
            if _compact_track_label.cget('text') != text:
                _compact_track_label.configure(text=text)
            if _marquee_needed:
                _schedule_tick()
        return
    _layout_info()
    station_text, track_text = _now_parts()
    pairs = ((_now_label, track_text),) if _info_mode == "galnet" else \
        ((_station_label, station_text), (_now_label, track_text))
    for label, text in pairs:
        # One line only: created with wraplength=0 and marked navigator_no_wrap, so nothing rewraps it.
        text = _ticker(label, text)
        if label.cget("text") != text:
            label.configure(text=text)
    if _marquee_needed:
        _schedule_tick()


def _refresh() -> None:
    if not _widget_alive(_title_label):
        return
    collapsed = bool(_settings.get("collapsed"))
    title = HEADER_TITLE
    if _title_label.cget("text") != title:
        _title_label.configure(text=title)
    if _collapse_button is not None:
        glyph = "\U0001f53d" if collapsed else "\U0001f53c"
        if _collapse_button.cget('text') != glyph:
            _collapse_button.configure(text=glyph)
    if _body is not None:
        if collapsed and _body.winfo_manager():
            _body.grid_remove()
        elif not collapsed and not _body.winfo_manager():
            _body.grid()
    if _buttons_frame is not None:
        target = _header_frame if collapsed else _controls_frame
        if str(_buttons_frame.grid_info().get('in', '')) != str(target):
            _buttons_frame.grid(in_=target, row=0, column=2, sticky=tk.E)
        if collapsed and not _header_sep.winfo_manager():
            _header_sep.grid()
        elif not collapsed and _header_sep.winfo_manager():
            _header_sep.grid_remove()
        _layout_controls()
    if _source_label is not None:
        name = SOURCE_LABELS[_settings["source"]]
        if _source_label.cget("text") != name:
            _source_label.configure(text=name)
    tracks_ok = (_settings["source"] in ("galnet", "music") or
                 _settings['source']=='streams' and len(_stations('streams'))>1)
    stations_ok = (len(stream_groups.playlists(_library['streams']))>1 if _settings['source']=='streams'
                   else len(_stations(_settings["source"])) > 1)
    for control in _controls:
        control.set_shape_state(_state)
        if control.kind in ("prev", "next"):
            control.configure(state=tk.NORMAL if tracks_ok else tk.DISABLED)
        elif control.kind in ("up", "down"):
            control.configure(state=tk.NORMAL if stations_ok else tk.DISABLED)
        elif control.kind in ('repeat','shuffle'):
            usable=_control_supported(control.kind)
            control.configure(state=tk.NORMAL if usable else tk.DISABLED)
            mode=(_settings['repeat'],_settings['shuffle'],usable)
            if getattr(control,'_mode_key',None)!=mode:
                control._mode_key=mode
                control.redraw()
    _refresh_now()


# =========================================================================== drawing
def _widget_alive(widget) -> bool:
    try:
        return widget is not None and bool(widget.winfo_exists())
    except tk.TclError:
        return False


def _palette():
    try:
        from theme import theme
        palette = getattr(theme, "current", None) or {}
    except Exception:
        palette = {}

    def label_colour(option, fallback):
        try:
            if _widget_alive(_title_label):
                return _title_label.cget(option) or fallback
        except tk.TclError:
            pass
        return fallback
    try:
        default_highlight = config.get_str("dark_highlight", default="#ff8000") or "#ff8000"
    except Exception:
        default_highlight = "#ff8000"
    return (palette.get("foreground") or label_colour("foreground", "black"),
            palette.get("highlight") or default_highlight,
            palette.get("background") or label_colour("background", "white"))


class _Control(tk.Canvas):
    """A stereo-style button drawn in code, sized to the text line."""

    SHAPES = ("prev", "play", "next", "down", "up", "repeat", "shuffle")

    def __init__(self, parent, kind: str, command, reference) -> None:
        super().__init__(parent, width=16, height=16, highlightthickness=0, bd=0, cursor="hand2")
        self.kind, self._command, self._reference = kind, command, reference
        self._enabled, self._foreground, self._playing = True, None, False
        for sequence in ("<Button-1>", "<Return>", "<space>"):
            self.bind(sequence, self._clicked)
        self.bind("<Map>", self.redraw)
        self.configure(takefocus=True)
        _theme_controls.append(self)

    def _clicked(self, _event=None) -> str:
        if self._enabled:
            self._command()
        return "break"

    def set_shape_state(self, state: str) -> None:
        # One key, one icon: shows Pause while audio is playing or tuning,
        # Play while stopped or paused - i.e. what pressing it will do.
        playing = state in ("playing", "loading")
        if self.kind == "play" and playing != self._playing:
            self._playing = playing
            self.redraw()

    def redraw(self, _event=None) -> None:
        try:
            line = int(tkfont.Font(font=self._reference.cget("font")).metrics("linespace"))
            background = self._reference.cget("background")
        except (tk.TclError, ValueError):
            line, background = 18, "white"
        normal, highlight, _ = _palette()
        colour = (self._foreground or highlight) if self._enabled else normal
        if self.kind=='repeat' and _settings['repeat']=='off':colour=normal
        h = getattr(self,"_cell",max(12,line-2))
        w = h
        signature = (w, h, str(background), str(colour), self._enabled, self._playing,
                     _settings['repeat'] if self.kind == 'repeat' else None,
                     _settings['shuffle'] if self.kind == 'shuffle' else None)
        if getattr(self, '_draw_signature', None) == signature:
            return
        self._draw_signature = signature
        wanted = dict(width=w, height=h, background=background, cursor="hand2" if self._enabled else "")
        changed = {key: value for key, value in wanted.items() if str(self.cget(key)) != str(value)}
        if changed:
            tk.Canvas.configure(self, **changed)
        shape = (w, h, str(colour), self._playing,
                 _settings['repeat'] if self.kind == 'repeat' else None,
                 _settings['shuffle'] if self.kind == 'shuffle' else None)
        if getattr(self, '_shape_signature', None) == shape:
            return  # A changed background does not require rebuilding vector icons.
        self._shape_signature = shape
        self.delete("all")
        m = h * 0.2                        # margin
        top, bottom, mid = m, h - m, h / 2
        bar = max(2, round(h * 0.12))
        fill = dict(fill=colour, outline=colour)
        if self.kind == "play":
            # Pause bars while playing; play triangle while stopped or paused.
            if self._playing:
                left = (w - 3 * bar) / 2
                for offset in (0, 2 * bar):
                    self.create_rectangle(left + offset, top, left + offset + bar, bottom, **fill)
            else:
                self.create_polygon(m, top, m, bottom, w - m, mid, **fill)
        elif self.kind in ("prev", "next"):
            # |◀◀ and ▶▶| : skip track
            tri = (w - 2 * m - bar) / 2
            if self.kind == "prev":
                self.create_rectangle(m, top, m + bar, bottom, **fill)
                x = m + bar
                for i in range(2):
                    self.create_polygon(x + tri * (i + 1), top, x + tri * (i + 1), bottom, x + tri * i, mid, **fill)
            else:
                for i in range(2):
                    self.create_polygon(m + tri * i, top, m + tri * i, bottom, m + tri * (i + 1), mid, **fill)
                self.create_rectangle(w - m - bar, top, w - m, bottom, **fill)
        elif self.kind == "up":
            self.create_polygon(m * 0.6, bottom, w - m * 0.6, bottom, w / 2, top, **fill)
        elif self.kind == "down":
            self.create_polygon(m * 0.6, top, w - m * 0.6, top, w / 2, bottom, **fill)

        elif self.kind == 'repeat':
            self.create_line(w*.22,h*.3,w*.78,h*.3,w*.84,h*.42,fill=colour,width=1.5,joinstyle=tk.ROUND)
            self.create_line(w*.78,h*.7,w*.22,h*.7,w*.16,h*.58,fill=colour,width=1.5,joinstyle=tk.ROUND)
            self.create_polygon(w*.75,h*.13,w*.94,h*.3,w*.75,h*.44,**fill)
            self.create_polygon(w*.25,h*.56,w*.06,h*.7,w*.25,h*.87,**fill)
            if _settings['repeat']=='track':
                self.create_text(w*.5,h*.51,text='1',fill=colour,font=('TkDefaultFont',-max(7,round(h*.49))))
        elif self.kind == 'shuffle':
            self.create_line(w*.12,h*.25,w*.32,h*.25,w*.68,h*.75,w*.82,h*.75,fill=colour,width=1.5)
            self.create_line(w*.12,h*.75,w*.32,h*.75,w*.68,h*.25,w*.82,h*.25,fill=colour,width=1.5)
            for y in (.25,.75):self.create_polygon(w*.75,h*(y-.13),w*.96,h*y,w*.75,h*(y+.13),**fill)
            if _settings['shuffle']:
                self.create_line(w*.35,h*.86,w*.45,h*.96,w*.65,h*.79,fill=colour,width=1.5)

    def configure(self, cnf=None, **kw):
        # EDMC themes hand-cursor widgets as text (foreground/font). Consume
        # those here; the canvas itself does not take them.
        if isinstance(cnf, dict):
            kw, cnf = {**cnf, **kw}, None
        redraw = False
        colour = kw.pop("foreground", kw.pop("fg", None))
        if colour is not None and str(colour) != str(self._foreground):
            self._foreground, redraw = colour, True
        if kw.pop("font", None) is not None:
            redraw = True
        if "state" in kw:
            enabled = kw.pop("state") != tk.DISABLED
            redraw = redraw or enabled != self._enabled
            self._enabled = enabled
        if "background" in kw or "bg" in kw:
            key = 'background' if 'background' in kw else 'bg'
            if str(kw[key]) != str(self.cget('background')):
                redraw = True
            else:
                kw.pop(key)
        result = tk.Canvas.configure(self, cnf, **kw) if (cnf or kw) else None
        if redraw and hasattr(self, "_reference"):
            self.redraw()
        return result

    config = configure


# =========================================================================== theme
def _control_supported(kind):
    if kind=='repeat':return _settings['source']=='music' and len(_tracks)>=1
    if kind=='shuffle':return _settings['source']=='music' and len(_tracks)>=2
    return True


def _layout_controls():
    if not _widget_alive(_buttons_frame) or not _controls:return
    visible=[control for control in _controls if _control_supported(control.kind)]
    for control in _controls:
        if control not in visible and control.winfo_manager():control.pack_forget()
    font=tkfont.Font(font=_source_label.cget('font'))
    width=max(1,_app_frame.winfo_width())
    inset=max(2,font.measure(' '))
    source_width=max(font.measure(name) for name in SOURCE_LABELS.values())
    budget=max(70,min(round(width*.5),width-source_width-font.measure(SEP)-2*inset))
    if _settings.get('collapsed'):
        available=width-2*_collapse_button.winfo_reqwidth()-font.measure(HEADER_TITLE)-font.measure(SEP)-8
        budget=max(68,min(budget,available))
    gap=2
    cell=max(8,min(font.metrics('linespace')-2,(budget-gap*(len(visible)-1))//len(visible)))
    actual=cell*len(visible)+gap*(len(visible)-1)
    if int(_buttons_frame.cget('width'))!=actual or int(_buttons_frame.cget('height'))!=cell:
        _buttons_frame.configure(width=actual,height=cell)
    _buttons_frame.grid_configure(padx=0)
    for i,control in enumerate(visible):
        control.pack(side=tk.LEFT,padx=(0 if i==0 else gap,0))
        if getattr(control,'_cell',None)!=cell:
            control._cell=cell;control.redraw()
    _layout_compact_track()


def _layout_compact_track(event=None):
    """Use remaining header space without letting metadata resize the panel."""
    if not _widget_alive(_compact_track_label):
        return
    font = tkfont.Font(font=_compact_track_label.cget('font'))
    start = _header_frame.winfo_x() + _header_frame.winfo_width()
    text_x = start + _compact_track_sep.winfo_reqwidth()
    end = _collapse_button.winfo_x() - 6
    available = end - text_x
    visible = bool(_settings.get('collapsed')) and available >= max(12, font.measure('0'))
    if visible:
        middle = _header_frame.winfo_y() + _header_frame.winfo_height() // 2
        for widget, options in ((_compact_track_sep, dict(x=start, y=middle, anchor='w')),
                (_compact_track_label, dict(x=text_x, y=middle, anchor='w', width=available))):
            current = widget.place_info()
            if any(str(current.get(key, '')) != str(value) for key, value in options.items()):
                widget.place(**options)
        _refresh_now()
    else:
        for widget in (_compact_track_sep, _compact_track_label):
            if widget.winfo_manager():
                widget.place_forget()


def _theme_event(_event=None) -> None:
    global _theme_pending
    if not _stopped and _app_frame is not None and _theme_pending is None:
        _theme_pending = _app_frame.after_idle(_apply_theme)


def _apply_theme() -> None:
    global _theme_pending, _theme_signature
    _theme_pending = None
    if _stopped or not _widget_alive(_title_label):
        return
    normal, highlight, background = _palette()
    references = []
    for reference in (_source_label, _title_label):
        font = tkfont.Font(font=reference.cget('font'))
        references.append((str(reference.cget('background')),
                           tuple(sorted(font.actual().items())), font.metrics('linespace')))
    signature = (normal, highlight, background, tuple(references), _app_frame.winfo_width(),
                 bool(_settings.get('collapsed')), _settings['source'])
    if _theme_signature == signature:
        return  # Tk broadcasts style changes from unrelated plugin panels too.
    _theme_signature = signature
    # Settings gear uses Normal Text, like the header it sits beside.
    for widget in list(_theme_controls):
        if not _widget_alive(widget):
            _theme_controls.remove(widget)
        elif isinstance(widget, _Control):
            widget.configure(foreground=highlight, background=background)
        else:
            widget.configure(foreground=highlight, background=background)
    for widget in (_compact_track_sep, _compact_track_label):
        if _widget_alive(widget):
            wanted = dict(foreground=normal, background=background, font=_title_label.cget('font'))
            changes = {key: value for key, value in wanted.items() if str(widget.cget(key)) != str(value)}
            if changes:
                widget.configure(**changes)
    try:
        _title_label.configure(padx=0, borderwidth=0)
        _layout_controls()
        _size_now_line()
    except tk.TclError:
        pass


# =========================================================================== actions
def _wheel(event) -> str:
    direction=1 if getattr(event,'delta',0)>0 or getattr(event,'num',None)==4 else -1
    voice=_settings['source']=='galnet'
    key='voice_volume' if voice else 'volume'
    _settings[key]=max(0,min(100,int(_settings[key])+direction*5))
    if _engine.running():
        if voice:_engine.send('voice_volume',value=_settings[key])
        else:_engine.send('volume',value=_settings[key],voice_value=_settings['voice_volume'])
    _save_settings();_flash(('Voice Volume: ' if voice else 'Volume: ')+str(_settings[key])+'%')
    return 'break'


def _toggle_collapsed() -> None:
    _settings["collapsed"] = not _settings.get("collapsed")
    _save_settings()
    _refresh()


# =========================================================================== EDMC hooks
def plugin_start3(plugin_dir: str) -> str:
    global DATA_DIR, SETTINGS_PATH, STATIONS_PATH, CACHE_PATH, _galnet, _dw3, _stopped
    _stopped = False
    appdir = getattr(config, "app_dir_path", None) or getattr(config, "app_dir", None) or \
        os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "EDMarketConnector")
    DATA_DIR = os.path.join(os.fspath(appdir), "ShipRadio")
    os.makedirs(DATA_DIR, exist_ok=True)
    SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")
    STATIONS_PATH = os.path.join(DATA_DIR, "stations.json")
    CACHE_PATH = os.path.join(DATA_DIR, "cache.json")
    _load_settings()
    cache = _read_json(CACHE_PATH, {})
    if isinstance(cache, dict):
        if isinstance(cache.get("galnet"), list):
            _galnet = [a for a in cache["galnet"] if isinstance(a, dict) and a.get("title")]
        if isinstance(cache.get("dw3"), list) and cache["dw3"]:
            _dw3 = [s for s in cache["dw3"] if isinstance(s, dict) and s.get("url")] or _dw3
    _load_tracks()
    logger.info("%s %s loaded", TITLE, VERSION)
    return TITLE


def plugin_app(parent):
    """Build the panel; on failure show a one-line notice instead of vanishing."""
    try:
        return _build_panel(parent)
    except Exception:
        logger.exception("%s could not build its panel", TITLE)
    global _app_frame, _title_label, _cog_button, _collapse_button, _body, _source_label, _now_label
    try:
        if _app_frame is not None:
            _app_frame.destroy()
    except tk.TclError:
        pass
    _title_label = _cog_button = _collapse_button = _body = _source_label = _now_label = None
    _controls.clear()
    _theme_controls.clear()
    _app_frame = tk.Frame(parent)
    tk.Label(_app_frame, text=f"{TITLE} {VERSION}: panel failed to start.\nSee the EDMC debug log.",
             justify=tk.CENTER).grid(row=0, column=0)
    _app_frame.columnconfigure(0, weight=1)
    return _app_frame


def _build_panel(parent):
    global _app_frame, _header_frame, _title_label, _cog_button, _collapse_button
    global _body, _source_label, _now_label, _station_label, _info_row, _info_sep, _stopped, _info_mode, _controls_frame, _buttons_frame, _header_sep, _theme_signature
    global _compact_track_sep, _compact_track_label
    _info_mode = ""
    _theme_signature = None
    _stopped = False
    _controls.clear()
    _theme_controls.clear()
    _app_frame = tk.Frame(parent)
    _app_frame.columnconfigure((0,2), uniform='radio_header_edges')
    _app_frame.columnconfigure(1, weight=1)

    # Symmetric edge cells keep the compact header clear of the right collapse key.
    _header_frame = tk.Frame(_app_frame)
    _header_frame.grid(row=0, column=1)
    _header_frame.bind('<Configure>', _layout_compact_track, add='+')
    _title_label = tk.Label(_header_frame, text=HEADER_TITLE)
    _title_label.grid(row=0,column=0)
    _cog_button = None
    _header_sep = tk.Label(_header_frame,text=SEP,padx=0,bd=0)
    _header_sep.grid(row=0,column=1)
    _header_sep.grid_remove()
    # Place the metadata in spare space outside the Interface-aligned header.
    # It never participates in requested size, so changing titles cannot resize EDMC.
    _compact_track_sep = tk.Label(_app_frame, text=SEP, padx=0, bd=0)
    _compact_track_sep.navigator_no_wrap = True
    _compact_track_label = tk.Label(_app_frame, text='', anchor=tk.W, width=1, height=1,
                                   wraplength=0, padx=0, bd=0)
    _compact_track_label.navigator_no_wrap = True
    _collapse_button = tk.Button(_app_frame, text="\U0001f53c", command=_toggle_collapsed)
    _collapse_button.grid(row=0, column=2, sticky=tk.NE)

    # Row 2: Source  |  |◀◀ ▶❚❚ ■ ▶▶|  ▼ ▲  |  now playing
    _body = tk.Frame(_app_frame)
    _body.grid(row=1, column=0, columnspan=3, sticky=tk.EW)
    _body.columnconfigure(0, weight=1)
    controls_row = tk.Frame(_body)
    controls_row.grid(row=0, column=0)  # Natural-width group centered as a whole.
    controls_row.columnconfigure(0,weight=0)
    _controls_frame=controls_row
    _source_label = tk.Label(controls_row, text="", cursor="hand2", padx=0, bd=0, takefocus=True,
                             anchor=tk.W)
    _source_label.navigator_no_wrap = True
    _source_label.grid(row=0, column=0)
    for sequence in ("<Button-1>", "<Return>", "<space>"):
        _source_label.bind(sequence, _cycle_source)
    _theme_controls.append(_source_label)
    tk.Label(controls_row, text=SEP, padx=0, bd=0).grid(row=0, column=1)
    buttons = tk.Frame(_app_frame)
    buttons.grid(in_=controls_row,row=0, column=2,sticky=tk.E)
    buttons.pack_propagate(False)
    _buttons_frame=buttons
    # No Stop key: Play/Pause covers it, and changing station or source
    # stops the old one automatically.
    for kind,command in (('prev',lambda:_step_track(-1)),('play',_play_pause),
                         ('next',lambda:_step_track(1)),('down',lambda:_step_station(-1)),
                         ('up',lambda:_step_station(1)),('repeat',_cycle_repeat),('shuffle',_toggle_shuffle)):
        control=_Control(buttons,kind,command,_source_label)
        control.pack(side=tk.LEFT)
        _controls.append(control)
    _app_frame.bind('<Configure>',_theme_event,add='+')
    # Separate fixed-height information line: 35% station, 65% track, less divider.
    _info_row = tk.Frame(_body)
    _info_row.grid(row=1, column=0, sticky=tk.EW)
    _station_label = tk.Label(_info_row,text="",anchor=tk.W,width=1,height=1,wraplength=0,padx=0,bd=0)
    _station_label.grid(row=0,column=0,sticky=tk.EW)
    _info_sep = tk.Label(_info_row,text=SEP,padx=0,bd=0)
    _info_sep.grid(row=0,column=1)
    _now_label = tk.Label(_info_row,text="",anchor=tk.E,width=1,height=1,wraplength=0,padx=0,bd=0)
    _now_label.grid(row=0,column=2,sticky=tk.EW)
    for label in (_station_label, _now_label):
        label.navigator_no_wrap = True      # Navigator Interface: never wrap these lines
    _info_row.bind('<Configure>',_size_now_line)

    for widget in [_app_frame, _body, buttons, _info_row, _station_label, _now_label, _source_label, *_controls]:
        widget.bind("<MouseWheel>", _wheel, add="+")
        widget.bind("<Button-4>", _wheel, add="+")
        widget.bind("<Button-5>", _wheel, add="+")

    top = _app_frame.winfo_toplevel()
    for sequence in ("<<ThemeChanged>>", "<<NavigatorThemeChanged>>"):
        _theme_bindings.append((top, sequence, top.bind(sequence, _theme_event, add="+")))
    _app_frame.bind("<Map>", _theme_event, add="+")
    _theme_event()
    _refresh()
    _refresh_galnet()                     # quietly keep Galnet current at start-up
    _run_job("dw3", sources.fetch_dw3_stations)
    if _settings.get("autoplay") and Engine.available():
        _app_frame.after(3000, lambda: _state == "stopped" and _play_current())
    return _app_frame


def journal_entry(cmdr, is_beta, system, station, entry, state):
    if entry.get("event") == "Shutdown" and _settings.get("pause_on_shutdown") and _state in ("playing", "loading"):
        _play_pause()


def plugin_stop() -> None:
    global _stopped, _tick_job, _theme_pending
    _stopped = True
    _remember_music()
    if _settings_view is not None:_settings_view.close()
    _save_settings()
    for job in (_tick_job, _theme_pending):
        if job is not None and _app_frame is not None:
            try:
                _app_frame.after_cancel(job)
            except tk.TclError:
                pass
    _tick_job = _theme_pending = None
    for top, sequence, binding in _theme_bindings:
        try:
            top.unbind(sequence, binding)
        except tk.TclError:
            pass
    _theme_bindings.clear()
    _engine.close()


# =========================================================================== settings tab
def plugin_prefs(parent, cmdr, is_beta):
    global _settings_view
    if _settings_view is not None:_settings_view.close()
    try:
        from .settings_ui import RadioSettings
    except ImportError:
        from settings_ui import RadioSettings
    _settings_view=RadioSettings(parent,sys.modules[__name__])
    # Required Interface owns the shared contrast preference and rendering.
    try:
        from plug import invoke
        invoke("(N) Interface", "Navigator Interface", "navigator_background_preferences",
               _settings_view.body, "Navigator_Radio")
    except ImportError:
        pass
    return _settings_view.frame


def prefs_changed(cmdr, is_beta):
    if _settings_view is not None and _settings_view.alive():
        _settings_view.apply()
