# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Journal-first Cartography model. No GUI, network calls or timers here."""
from __future__ import annotations
from datetime import datetime, timezone
import math

SEP = "  |  "
UNKNOWN = "Unknown"
EVENTS = {"Location", "FSDJump", "CarrierJump", "Docked", "Scan", "FSSDiscoveryScan",
          "FSSAllBodiesFound", "SAAScanComplete", "SAASignalsFound", "FSSSignalDiscovered",
          "ProspectedAsteroid", "ShipTargeted", "MissionAccepted", "MissionRedirected",
          "MissionCompleted", "MissionFailed", "MissionAbandoned", "Missions", "Bounty",
          "RedeemVoucher", "PayBounties", "FactionKillBond", "DockingDenied"}


def stamp(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=timezone.utc).timestamp()
    except (ValueError, TypeError):
        return 0.0


def clean(value):
    if value is None or value == "":
        return UNKNOWN
    if isinstance(value, dict):
        value = value.get("Name", value.get("name", UNKNOWN))
    text = str(value)
    ring_classes={"eRingClass_MetalRich":"Metal Rich","eRingClass_Metalic":"Metallic",
                  "eRingClass_Rocky":"Rocky","eRingClass_Icy":"Icy"}
    if text in ring_classes: return ring_classes[text]
    if text.endswith("Resources") and text in {"PristineResources","MajorResources","CommonResources","LowResources","DepletedResources"}:
        return text[:-9]
    if text.startswith("$"):
        text = text.strip("$;").replace("SYSTEM_SECURITY_", "").replace("system_security_", "")
        text = text.replace("economy_", "").replace("government_", "").replace("FactionState_", "").replace("AsteroidMaterialContent_", "")
        return text.replace("_", " ").title()
    return text


def distance(value, unit="Ls"):
    try:
        return f"{float(value):,.1f} {unit}"
    except (ValueError, TypeError):
        return UNKNOWN


def field(row, key, default=UNKNOWN):
    return row.get(key, {}).get("v", default)


def powerplay_text(meta, top_two=True):
    """Control and acquisition are separate; the broad Powers list is unranked."""
    snapshot = field(meta, "powerplay", None)
    if not isinstance(snapshot, dict):
        powers = field(meta, "powers", None)
        return "Control unknown" if powers else ("None" if powers == [] else UNKNOWN)
    state = snapshot.get("state") or ""
    controller = snapshot.get("controller") or ""
    acquisition = state.casefold() in {"unoccupied", "uncontrolled", "expansion", "contested"}
    if controller and not acquisition:
        return controller + (f" ({state})" if state else "")
    text = state if acquisition else (f"Control unknown ({state})" if state else "Control unknown")
    ranked = {}
    for item in snapshot.get("progress", []):
        if not isinstance(item, dict):
            continue
        name, value = item.get("Power"), item.get("ConflictProgress")
        if (isinstance(name, str) and name.strip() and not isinstance(value, bool)
                and isinstance(value, (int, float)) and math.isfinite(value) and value >= 0):
            ranked[name.strip()] = max(value, ranked.get(name.strip(), 0))
    if acquisition and ranked:
        items = sorted(ranked.items(), key=lambda item: (-item[1], item[0].casefold()))
        if top_two:
            items = items[:2]
        text += SEP + "Acquisition: " + ", ".join(f"{name}: {value:.1%}" for name, value in items)
    if not state and not controller and snapshot.get("powers") == []:
        return "None"
    return text


def put(row, key, value, at=0, local=True):
    if value is None or value == "":
        return
    old = row.get(key)
    # Web observations must be strictly newer to replace a local observation.
    # A response's download time is deliberately never used as an observation time.
    if old:
        if not local and old.get("local") and (not at or at <= old.get("at", 0)):
            return
        if at < old.get("at", 0):
            return
    row[key] = {"v": value, "at": at, "local": local}


class Atlas:
    def __init__(self, data=None):
        self.data = data if isinstance(data, dict) else {}
        self.data.setdefault("systems", {})
        self.data.setdefault("missions", {})
        self.encounters = {}
        self.signals = {}
        self.prospector = None
        self.current = None
        self.legal = UNKNOWN
        self.mission_removals = {}
        self.mission_snapshots = {}
        self.visit_scans = set()
        self.visit_expected = None

    @staticmethod
    def owner(cmdr, beta):
        return (cmdr or "").casefold() + (":beta" if beta else ":live")

    def record(self, cmdr, beta, name):
        key = self.owner(cmdr, beta) + "/" + (name or "").casefold()
        return self.data["systems"].setdefault(key, {"meta": {}, "bodies": {}, "objects": {}})

    def merge(self, newer):
        for key, record in newer.data["systems"].items():
            dest = self.data["systems"].setdefault(key, {"meta": {}, "bodies": {}, "objects": {}})
            for collection in ("meta", "bodies", "objects"):
                if collection == "objects":
                    for row in record[collection].values():
                        target=self.object(dest,{k:field(row,k,None) for k in ("name","marketId")})
                        if target is not None:
                            for k,v in row.items(): put(target,k,v["v"],v["at"],v["local"])
                    continue
                if collection == "meta":
                    items = [(dest[collection], record[collection])]
                else:
                    items = [(dest[collection].setdefault(k, {}), row) for k, row in record[collection].items()]
                for target, row in items:
                    for k, v in row.items():
                        put(target, k, v["v"], v["at"], v["local"])
        # Live mission callbacks are newer than a replay, including removals.
        for owner, missions in newer.data["missions"].items():
            existing=self.data["missions"].setdefault(owner,{})
            snapshot=newer.mission_snapshots.get(owner)
            if snapshot is not None:
                existing={k:v for k,v in existing.items() if k in snapshot}
            existing.update(missions)
            for mid in newer.mission_removals.get(owner,set()): existing.pop(mid,None)
            self.data["missions"][owner]=existing
        self.mission_removals=newer.mission_removals
        self.mission_snapshots=newer.mission_snapshots
        self.visit_scans=newer.visit_scans
        self.visit_expected=newer.visit_expected
        self.encounters, self.signals = newer.encounters, newer.signals
        self.current, self.legal, self.prospector = newer.current, newer.legal, newer.prospector

    def feed(self, cmdr, beta, name, entry, history=False):
        event = entry.get("event")
        at = stamp(entry.get("timestamp"))
        owner = self.owner(cmdr, beta)
        missions = self.data["missions"].setdefault(owner, {})
        mid = str(entry.get("MissionID", ""))
        if event == "Missions":
            active = {str(m.get("MissionID")) for m in entry.get("Active", [])}
            if not history: self.mission_snapshots[owner]=active
            self.data["missions"][owner] = {k:v for k,v in missions.items() if k in active}
        elif event in {"MissionAccepted", "MissionRedirected"} and mid:
            old = missions.setdefault(mid, {})
            old.update(entry)
        elif event in {"MissionCompleted", "MissionFailed", "MissionAbandoned"}:
            missions.pop(mid, None)
            if not history: self.mission_removals.setdefault(owner,set()).add(mid)
        if not name:
            return
        r = self.record(cmdr, beta, name)
        meta = r["meta"]
        if event in {"Location", "FSDJump", "CarrierJump"}:
            if any(key in entry for key in ("ControllingPower", "PowerplayState", "Powers",
                                             "PowerplayConflictProgress")):
                # One timestamped observation prevents old controllers/progress surviving
                # a newer unoccupied system report or a background history merge.
                put(meta, "powerplay", {
                    "controller": entry.get("ControllingPower") if isinstance(entry.get("ControllingPower"), str) else "",
                    "state": entry.get("PowerplayState") if isinstance(entry.get("PowerplayState"), str) else "",
                    "powers": entry.get("Powers") if isinstance(entry.get("Powers"), list) else None,
                    "progress": entry.get("PowerplayConflictProgress") if isinstance(entry.get("PowerplayConflictProgress"), list) else [],
                }, at)
            for source, key in (("SystemAllegiance", "allegiance"), ("SystemEconomy_Localised", "economy"),
                                ("SystemEconomy", "economy"), ("Population", "population"),
                                ("SystemSecurity_Localised", "security"), ("SystemSecurity", "security"),
                                ("SystemFaction", "faction"), ("Powers", "powers"),
                                ("StarPos", "coords"), ("Conflicts", "conflicts")):
                if source in entry and not (source in {"SystemEconomy", "SystemSecurity"} and source+"_Localised" in entry):
                    put(meta, key, entry[source], at)
            faction=entry.get("SystemFaction")
            if isinstance(faction,dict): put(meta,"state",faction.get("FactionState"),at)
            controlling = clean(faction)
            for f in entry.get("Factions", []):
                if f.get("Name") == controlling:
                    put(meta, "state", f.get("FactionState"), at)
                    put(meta, "reputation", f.get("MyReputation"), at)
                    put(meta, "faction_status", f.get("HappiestSystem") if "HappiestSystem" in f else None, at)
            if not history:
                current = (owner, name.casefold())
                if current != self.current:
                    self.encounters.clear()
                    self.signals.clear()
                    self.prospector = None
                    self.visit_scans.clear()
                    self.visit_expected = None
                    self.legal = UNKNOWN
                self.current = current
        if event == "FSSDiscoveryScan" and not history:
            self.visit_expected=entry.get("BodyCount")
        if event == "Scan" and entry.get("BodyName"):
            if not history: self.visit_scans.add(entry["BodyName"].casefold())
            row = r["bodies"].setdefault(entry["BodyName"].casefold(), {})
            for source, key in (("BodyName", "name"), ("PlanetClass", "type"), ("StarType", "star"),
                                ("DistanceFromArrivalLS", "distance"), ("Landable", "landable"),
                                ("Rings", "rings"), ("ReserveLevel", "reserves"), ("BodyID", "id")):
                put(row, key, entry.get(source), at)
        elif event in {"SAASignalsFound", "SAAScanComplete"}:
            bname = entry.get("BodyName")
            if not bname:
                bname = next((field(b,"name") for b in r["bodies"].values() if field(b,"id") == entry.get("BodyID")), None)
            if bname:
                row = r["bodies"].setdefault(bname.casefold(), {})
                put(row, "name", bname, at)
                if event == "SAAScanComplete":
                    put(row, "mapped", True, at)
                else:
                    put(row, "signals", entry.get("Signals", []), at)
        if event in {"Docked", "Location", "CarrierJump"} and entry.get("StationName"):
            self.object(r, {"name": entry["StationName"], "marketId": entry.get("MarketID"),
                           "type": entry.get("StationType"), "distanceToArrival": entry.get("DistFromStarLS"),
                           "services": entry.get("StationServices"), "body": entry.get("Body"),
                           "faction": clean(entry.get("StationFaction")), "landingPads": entry.get("LandingPads"),
                           "economy": entry.get("StationEconomy_Localised") or clean(entry.get("StationEconomy")),
                           **({"hostile":False,"access":False} if event=="Docked" else {})}, at, True)
        if event == "DockingDenied" and entry.get("StationName"):
            name=entry["StationName"]
            reason=entry.get("Reason")
            if reason in {"Hostile","NoReason","TooLarge","Distance","Offence","Offences"}:
                obj={"name":name}
                if reason=="Hostile": obj["hostile"]=True
                elif reason in {"TooLarge","Offence","Offences"}: obj["access"]=reason
                self.object(r,obj,at,True)
        if history:
            return
        if event == "FSSSignalDiscovered":
            key = entry.get("SignalName_Localised") or entry.get("SignalName") or UNKNOWN
            self.signals[key] = dict(entry)
            if entry.get("IsStation"):
                self.object(r, {"name": key, "type": "Unknown", "distanceToArrival": None}, at, True)
        elif event == "ProspectedAsteroid":
            self.prospector = dict(entry)
        elif event == "ShipTargeted" and entry.get("TargetLocked") and entry.get("ScanStage", 0) >= 3:
            pilot = entry.get("PilotName_Localised") or entry.get("PilotName")
            if pilot and (entry.get("LegalStatus") == "Wanted" or entry.get("Bounty", 0) > 0):
                # No unique target ID is provided. Keep a best-effort pilot/ship/faction key.
                key = (pilot, entry.get("Ship"), entry.get("Faction"))
                self.encounters[key] = dict(entry)

    @staticmethod
    def object(record, obj, at=0, local=False):
        name = obj.get("name")
        if not name:
            return
        # Match by MarketID first, scoped name second; migrate a name-only record.
        existing = None
        for candidate,row in record["objects"].items():
            old_id=field(row,"marketId",None)
            new_id=obj.get("marketId")
            if old_id is not None and new_id is not None:
                match=str(old_id)==str(new_id)
            else:
                match=str(field(row,"name","")).casefold()==name.casefold()
            if match:
                existing=candidate
                break
        key = existing or ("market:"+str(obj["marketId"]) if obj.get("marketId") is not None else name.casefold())
        row = record["objects"].setdefault(key, {})
        for k,v in obj.items():
            if v != UNKNOWN:
                put(row,k,v,at,local)
        return row

    def online(self, cmdr, beta, name, payload):
        def part(source, key):
            # EDSM uses [] for "nothing known"; older caches may hold that too.
            value = source.get(key) if isinstance(source, dict) else None
            return value if isinstance(value, dict) else {}
        r = self.record(cmdr,beta,name)
        info = part(payload, "info")
        at = stamp(info.get("date") or info.get("updateTime"))
        values = part(info, "information")
        for src,key in (("allegiance","allegiance"),("economy","economy"),("population","population"),
                        ("security","security"),("faction","faction"),("factionState","state")):
            put(r["meta"],key,values.get(src),at,False)
        if isinstance(info.get("coords"), dict):
            put(r["meta"],"coords",[info["coords"].get(k,0) for k in "xyz"],at,False)
        for body in part(payload, "bodies").get("bodies") or []:
            if not isinstance(body, dict) or not body.get("name"):
                continue
            row = r["bodies"].setdefault(body["name"].casefold(), {})
            at = stamp(body.get("updateTime"))
            for src,key in (("name","name"),("subType","type"),("distanceToArrival","distance"),
                            ("isLandable","landable"),("rings","rings"),("reserveLevel","reserves"),("bodyId","id")):
                put(row,key,body.get(src),at,False)
        for obj in part(payload, "stations").get("stations") or []:
            if not isinstance(obj, dict):
                continue
            obj=dict(obj)
            if not obj.get("services"):
                services=list(obj.get("otherServices") or [])
                services += [label for key,label in (("haveMarket","Market"),("haveShipyard","Shipyard"),("haveOutfitting","Outfitting")) if obj.get(key)]
                if services: obj["services"]=services
            self.object(r,obj,stamp(obj.get("updateTime",{}).get("information") if isinstance(obj.get("updateTime"),dict) else obj.get("updateTime")))

    def turn_in(self, cmdr, beta, system, station):
        for mission in self.data["missions"].get(self.owner(cmdr,beta), {}).values():
            # A generic mission destination can be an intermediate objective.
            # Promote explicit delivery/courier/passenger-transport destinations;
            # do not label a sightseeing or combat objective as a turn-in desk.
            kind=str(mission.get("Name") or "").casefold()
            transport=any(word in kind for word in ("delivery","courier","passengerbulk","passengervip"))
            if not transport or any(word in kind for word in ("sightseeing","tourism")):
                continue
            expiry = stamp(mission.get("Expiry"))
            if expiry and expiry < datetime.now(timezone.utc).timestamp():
                continue
            target = mission.get("NewDestinationStation") or mission.get("DestinationStation")
            target_system = mission.get("NewDestinationSystem") or mission.get("DestinationSystem")
            if target and target_system and target.casefold() == station.casefold() and target_system.casefold() == system.casefold():
                return True
        return False


def object_group(row):
    kind = str(field(row,"type","")).casefold()
    if "carrier" in kind:
        return "Carriers"
    if any(s in kind for s in ("planetary", "settlement", "surface")):
        return "Ports"
    if any(s in kind for s in ("coriolis", "orbis", "ocellus", "outpost", "asteroid", "starport")):
        return "Stations"
    return "Other"


def pad_size(row):
    pads = field(row,"landingPads",None)
    if isinstance(pads,dict):
        for key,label in (("Large","L"),("Medium","M"),("Small","S")):
            if pads.get(key, pads.get(key.lower(),0)):
                return label
    kind = str(field(row,"type","")).lower()
    if kind in {"coriolis","orbis","ocellus","fleet carrier","fleetcarrier","asteroid base"}:
        return "L"
    if kind == "outpost":
        return "M"
    return UNKNOWN


def object_rows(atlas,cmdr,beta,system,group,compatible=False,required="Unknown",tagger=None):
    """(name, detail) rows; with a tagger, (name, detail, tags) for service markers."""
    rows=[]
    for row in atlas.record(cmdr,beta,system)["objects"].values():
        if object_group(row) != group:
            continue
        name=field(row,"name")
        pad=pad_size(row)
        if compatible and required in ("S","M","L") and pad in ("S","M","L") and "SML".index(pad)<"SML".index(required):
            continue
        pin=atlas.turn_in(cmdr,beta,system,name)
        markers=[]
        if pin: markers.append("▣ Turn-In")
        if field(row,"access",None): markers.append("▢ Restricted: "+clean(field(row,"access")))
        if field(row,"hostile",False): markers.append("△ Hostile")
        try: dist=float(field(row,"distanceToArrival",float("inf")))
        except (TypeError,ValueError): dist=float("inf")
        detail=SEP.join([distance(None if math.isinf(dist) else dist), "Pad: "+pad,clean(field(row,"type"))]+markers)
        body=field(row,"body",None)
        if body: detail+=SEP+"Body: "+clean(body)
        services=field(row,"services",None)
        if services: detail+=SEP+", ".join(str(s) for s in services)
        if group=="Carriers":
            observed=max((v.get("at",0) for v in row.values()),default=0)
            if observed: detail+=SEP+"Observed: "+datetime.fromtimestamp(observed,timezone.utc).strftime("%Y-%m-%d")
        reputation=field(atlas.record(cmdr,beta,system)["meta"],"reputation",None)
        controlling=clean(field(atlas.record(cmdr,beta,system)["meta"],"faction",None))
        if isinstance(reputation,(int,float)) and reputation<=-90 and clean(field(row,"faction",None))==controlling:
            detail+=SEP+"△ Possible Hostility (Faction Reputation)"
        rows.append((not pin,dist,name,detail,tagger(row) if tagger else None))
    ordered=sorted(rows,key=lambda x:(x[0],x[1],x[2].casefold()))
    if tagger:
        return [(name,detail,tags) for _,_,name,detail,tags in ordered]
    return [(name,detail) for _,_,name,detail,_ in ordered]
