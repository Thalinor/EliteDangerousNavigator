# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Background-only journal history and optional read-only EDSM requests."""
from __future__ import annotations

import gzip
import io
import json
import logging
import os
from pathlib import Path
import queue
import tempfile
import threading
import time
import requests

try:
    from .system_data import SystemBook, EVENTS, edsm_record
    from .atlas import Atlas, EVENTS as ATLAS_EVENTS
except ImportError:
    from system_data import SystemBook, EVENTS, edsm_record
    from atlas import Atlas, EVENTS as ATLAS_EVENTS

logger = logging.getLogger("EDMC.Navigator_Cartography")
CACHE_VERSION = 6   # 6: controller/state/acquisition snapshots; one local background rebuild
MAX_RESPONSE = 4 * 1024 * 1024
# One-time optional seed of known traders/brokers, built from Spansh by the suite author
# so each user downloads ~1 MB once instead of querying Spansh for every station.
LANDMARKS_URL = ("https://github.com/Thalinor/EliteDangerousNavigator/releases/download/"
                 "cartography-data-v1/cartography_landmarks.json.gz")
MAX_LANDMARKS_DOWNLOAD = 8 * 1024 * 1024
MAX_LANDMARKS_JSON = 48 * 1024 * 1024


def read_json(path: Path, default):
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path: Path, value) -> None:
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix="systems_", suffix=".tmp", delete=False) as f:
            temporary = f.name
            json.dump(value, f)
        os.replace(temporary, path)
        temporary = None
    except OSError:
        logger.warning("Could not save Systems Navigator cache", exc_info=True)
    finally:
        if temporary:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def journal_history(folder: str | None, cache: dict | None = None, stop=None):
    if not folder or not Path(folder).is_dir():
        book = SystemBook()
        book.atlas = Atlas()
        return book, {}
    files = sorted(Path(folder).glob("Journal*.log"))
    signatures = {}
    for p in files:
        try:
            st = p.stat()
            signatures[p.name] = [st.st_size, st.st_mtime_ns]
        except OSError:
            pass
    cache = cache if isinstance(cache, dict) else {}
    if cache.get("version") == CACHE_VERSION and cache.get("files") == signatures:
        book = SystemBook(cache.get("records", {}))
        book.atlas = Atlas(cache.get("atlas"))
        return book, cache
    book = SystemBook()
    book.atlas = Atlas()
    commander, beta, system, address = "", False, None, None
    keys = tuple('"'+event+'"' for event in EVENTS | ATLAS_EVENTS | {"Commander", "LoadGame", "Fileheader", "FileHeader"})
    for path in files:
        if stop and stop():
            break
        try:
            with path.open(encoding="utf-8-sig", errors="replace") as stream:
                for line in stream:
                    if stop and stop():
                        break
                    if not any(key in line for key in keys):
                        continue
                    try:
                        e = json.loads(line)
                    except ValueError:
                        continue
                    event = e.get("event")
                    if commander:
                        book.navigation(commander, beta, e)
                    if event in ("Fileheader", "FileHeader"):
                        beta = "beta" in str(e.get("gameversion") or "").lower()
                    elif event == "Commander":
                        commander = str(e.get("Name") or "")
                        system, address = None, None
                    elif event == "LoadGame":
                        commander = str(e.get("Commander") or commander)
                        system, address = None, None
                    elif event in ("Location", "FSDJump", "CarrierJump"):
                        system = e.get("StarSystem")
                        address = e.get("SystemAddress")
                    if commander and event in ATLAS_EVENTS:
                        book.atlas.feed(commander, beta, system, e, history=True)
                    if (commander and system and event in EVENTS
                            and (e.get("SystemAddress") is None or address is None or e["SystemAddress"] == address)):
                        book.feed(commander, beta, system, e)
        except OSError:
            logger.warning("Could not read a journal file", exc_info=True)
    return book, {"version": CACHE_VERSION, "files": signatures, "records": book.records, "atlas": book.atlas.data}


def _request_json(url, params=None, payload=None):
    try:
        from config import user_agent
    except ImportError:
        user_agent = "EDMC"
    request = requests.get if payload is None else requests.post
    kwargs = {"params":params} if payload is None else {"json":payload}
    with request(url, headers={"User-Agent":str(user_agent)+" Cartography/0.3.12",
                              "Accept":"application/json"}, timeout=(4,8), stream=True, **kwargs) as response:
        response.raise_for_status()
        chunks, size = [], 0
        for chunk in response.iter_content(chunk_size=65536):
            size += len(chunk)
            if size > MAX_RESPONSE:
                raise ValueError("Response exceeded size limit")
            chunks.append(chunk)
    return json.loads(b"".join(chunks))


def fetch_edsm(system: str, address: int | None):
    payload = {}
    errors = []
    for key,url,params in (
        ("bodies","https://www.edsm.net/api-system-v1/bodies",{"systemName":system}),
        ("info","https://www.edsm.net/api-v1/system",{"systemName":system,"showInformation":1,"showCoordinates":1}),
        ("stations","https://www.edsm.net/api-system-v1/stations",{"systemName":system})):
        try:
            result = _request_json(url,params)
        except Exception:
            errors.append(key)
            continue
        # EDSM answers [] (an empty list) for a system it does not know.
        # Treat that as an empty object so callers can always use .get().
        payload[key] = result if isinstance(result, dict) else {}
    if not payload:
        raise ValueError("All EDSM endpoints unavailable")
    record = edsm_record(payload.get("bodies",{}),system,address)
    record["atlas"] = payload
    record["partial_errors"] = errors
    return record


def fetch_traders(system):
    # Three category queries share one job/cache, requested only by the Traders view.
    data = {}
    for category in ("Raw","Manufactured","Encoded"):
        try:
            reply = _request_json("https://spansh.co.uk/api/stations/search",payload={
                "reference_system":system,"filters":{"material_trader":{"value":[category]}},
                "sort":[{"distance":{"direction":"asc"}}],"size":10,"page":0})
            keys={"name","system_name","distance","distance_to_arrival","has_large_pad","large_pads","medium_pads","small_pads","type","is_planetary","system_is_permit_required","updated_at"}
            data[category] = {"results":[{k:v for k,v in row.items() if k in keys} for row in reply.get("results",[])]}
        except Exception:
            data[category] = {"error":True,"results":[]}
    return data


def fetch_landmarks():
    """Download the gzipped station-data file once; size-limited before and after unpacking."""
    try:
        from config import user_agent
    except ImportError:
        user_agent = "EDMC"
    with requests.get(LANDMARKS_URL, headers={"User-Agent": str(user_agent)+" Cartography/0.3.12"},
                      timeout=(6, 30), stream=True) as response:
        response.raise_for_status()
        chunks, size = [], 0
        for chunk in response.iter_content(chunk_size=65536):
            size += len(chunk)
            if size > MAX_LANDMARKS_DOWNLOAD:
                raise ValueError("Station data download exceeded size limit")
            chunks.append(chunk)
    with gzip.GzipFile(fileobj=io.BytesIO(b"".join(chunks))) as stream:
        raw = stream.read(MAX_LANDMARKS_JSON + 1)
    if len(raw) > MAX_LANDMARKS_JSON:
        raise ValueError("Station data file is larger than expected")
    return json.loads(raw)


class DataService:
    """Workers publish data through a queue; they never call Tk."""
    def __init__(self, folder: Path):
        self.folder = folder
        self.results = queue.Queue()
        self.jobs = queue.Queue()
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name="SystemsNavigatorData", daemon=True)
        self.thread.start()

    def history(self, folder: str | None):
        self.jobs.put(("history", folder))

    def lookup(self, system: str, address: int | None, refresh: bool = False):
        self.jobs.put(("edsm", system, address, refresh))

    def traders(self, system, refresh=False):
        self.jobs.put(("traders", system, refresh))

    def landmarks_load(self):
        self.jobs.put(("landmarks_load",))

    def landmarks_save(self, snapshot):
        self.jobs.put(("landmarks_save", snapshot))

    def landmarks_download(self):
        self.jobs.put(("landmarks_download",))

    def close(self):
        self.stop_event.set()
        self.jobs.put(None)

    def _run(self):
        cached = read_json(self.folder/"edsm_cache.json", {})
        online = cached.get("systems", {}) if isinstance(cached, dict) and cached.get("version") == 2 else {}
        if not isinstance(online, dict):
            online = {}
        checked = set()
        while not self.stop_event.is_set():
            job = self.jobs.get()
            if job is None:
                return
            try:
                if job[0] == "history":
                    old = read_json(self.folder/"history_cache.json", {})
                    book, cache = journal_history(job[1], old, self.stop_event.is_set)
                    if self.stop_event.is_set():
                        return
                    if cache:
                        write_json(self.folder/"history_cache.json", cache)
                    self.results.put(("history", book))
                elif job[0] == "landmarks_load":
                    self.results.put(("landmarks_load", read_json(self.folder/"landmarks.json", {})))
                elif job[0] == "landmarks_save":
                    write_json(self.folder/"landmarks.json", job[1])
                elif job[0] == "landmarks_download":
                    try:
                        self.results.put(("landmarks_download", fetch_landmarks()))
                    except Exception as error:
                        logger.info("Station data download unavailable", exc_info=True)
                        self.results.put(("landmarks_download", {"error": str(error) or type(error).__name__}))
                elif job[0] == "traders":
                    name = job[1]
                    cache = read_json(self.folder/"traders_cache.json", {})
                    item = cache.get(name.casefold(), {})
                    ttl = 300 if any(v.get("error") for v in item.get("data",{}).values()) else 86400
                    if (len(job)>2 and job[2]) or time.time()-item.get("when",0) >= ttl:
                        item = {"when":time.time(),"data":fetch_traders(name)}
                        cache[name.casefold()] = item
                        if len(cache)>32:
                            cache.pop(min(cache,key=lambda k:cache[k]["when"]))
                        write_json(self.folder/"traders_cache.json",cache)
                    self.results.put(("traders",name,item))
                else:
                    name, address, refresh = job[1:]
                    key = name.casefold()
                    item = online.get(key, {})
                    ttl = 86400 if item.get("data", {}).get("known") else 900
                    if item.get("error"):
                        ttl = 300
                    valid_address = item.get("address") == address
                    session_key = (key, address)
                    cooldown = item.get("error") and time.time() - item.get("when", 0) < 300
                    force = refresh and session_key not in checked and not cooldown
                    if force and valid_address and item.get("data"):
                        self.results.put(("edsm_cached", name, address, item))
                    if force or time.time() - item.get("when", 0) >= ttl or not valid_address:
                        try:
                            data = fetch_edsm(name, address)
                            item = {"when": time.time(), "address": address, "data": data}
                        except Exception:
                            logger.info("EDSM lookup unavailable for %s", name, exc_info=True)
                            # Failure is not a successful 'system absent' answer.
                            previous = item.get("data") if valid_address else None
                            item = {"when": time.time(), "address": address, "error": True}
                            if previous:
                                item["data"] = previous  # an outage must not erase known facts
                        if self.stop_event.is_set():
                            return
                        online[key] = item
                        if len(online) > 512:
                            oldest = min(online, key=lambda k: online[k].get("when", 0))
                            del online[oldest]
                        write_json(self.folder/"edsm_cache.json", {"version": 2, "systems": online})
                    checked.add(session_key)
                    self.results.put(("edsm", name, address, item))
            except Exception:
                logger.exception("Systems Navigator background job failed")
                self.results.put(("failed", job[0], job[1:3]))
