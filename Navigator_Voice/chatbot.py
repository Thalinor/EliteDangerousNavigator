# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Built In Chatbot: pattern matching and calculations over existing local facts.

No model, network, disk reads, UI access or ship-control calls are used here.
Suite adapters read whitelisted in-memory fields and never call renderers/lookups.
"""
from __future__ import annotations
import copy
import math
import re
import time
from .assistant import spoken, Knowledge


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def position(value):
    return tuple(value) if isinstance(value, (list, tuple)) and len(value)==3 and all(number(n) for n in value) else None


def field(row, name, default=None):
    value=row.get(name, {})
    return value.get('v', default) if isinstance(value, dict) else default


def distance_target(question):
    match=re.search(r'(?:distance (?:from here )?to|how far (?:is it |are we |am i )?(?:to|from)|how far is) (.+)',spoken(question))
    target=match.group(1) if match else 'sol'
    return re.sub(r' (?:from here|away|please|now|am i|are we)$','',target).strip()


def update_knowledge(k, entry, state):
    """Keep small current snapshots from EDMC callbacks, including plotted jumps."""
    event=entry.get('event')
    if event in ('Location','FSDJump','CarrierJump'):
        k.position=position(entry.get('StarPos'))
        if k.position is None and str(state.get('SystemName','')).casefold()==k.system.casefold():
            k.position=position(state.get('StarPos'))
        if k.position and k.system:
            k.coordinates[k.system.casefold()]=k.position
            if len(k.coordinates)>512:
                key=next(key for key in k.coordinates if key!='sol')
                k.coordinates.pop(key)
        k.in_jump=False
        if k.route_ending:
            arrived=k.game_destination and k.game_destination.casefold()==k.system.casefold()
            k.nav_route=None;k.game_jumps=0 if arrived else None
            k.game_destination=k.system if arrived else None;k.route_ending=False
        elif k.nav_route:
            names=[str(r.get('StarSystem','')).casefold() for r in k.nav_route]
            start=k.nav_index+1 if event=='FSDJump' else 0
            indices=[n for n,name in enumerate(names) if name==k.system.casefold() and n>=start]
            if indices:
                k.nav_index=indices[0];k.game_jumps=len(names)-k.nav_index-1
            else:
                k.game_jumps=None
        elif event in ('FSDJump','CarrierJump'):
            k.game_jumps=max(0,k.game_jumps-1) if number(k.game_jumps) and spoken(k.target or '')==spoken(k.system) else None
    if event=='StartJump' and entry.get('JumpType')=='Hyperspace':k.in_jump=True
    if event=='NavRouteClear':
        k.nav_seen=True
        if k.in_jump:k.route_ending=True
        else:k.nav_route=None;k.game_jumps=None;k.game_destination=None
    if event=='FSDTarget':
        count=entry.get('RemainingJumpsInRoute')
        if number(count) and int(count)==count and count>=0:
            k.game_jumps=int(count);k.target=entry.get('Name')
            if count==1:k.game_destination=k.target
    saved=state.get('NavRoute')
    route=entry.get('Route') if event=='NavRoute' else None
    if route is None and (event=='NavRoute' or not k.nav_seen) and isinstance(saved,dict):route=saved.get('Route')
    if isinstance(route,list):
        k.nav_seen=True;k.route_ending=False
        k.nav_route=[dict(r) for r in route[:20000] if isinstance(r,dict) and isinstance(r.get('StarSystem'),str)]
        if len(k.nav_route)!=len(route):
            k.nav_route=[]  # Partial/corrupt routes cannot establish a jump count.
        k.game_destination=k.nav_route[-1]['StarSystem'] if k.nav_route else None
        k.nav_index=next((n for n,r in enumerate(k.nav_route) if r['StarSystem'].casefold()==k.system.casefold()),-1)
        k.game_jumps=len(k.nav_route)-k.nav_index-1 if k.nav_index>=0 else None
        for row in k.nav_route:
            xyz=position(row.get('StarPos'))
            if xyz:k.coordinates[row['StarSystem'].casefold()]=xyz
        # This is a bounded session cache, never a galaxy download.
        if len(k.coordinates)>20000:
            k.coordinates={'sol':(0.,0.,0.),**{r['StarSystem'].casefold():position(r['StarPos'])
                for r in k.nav_route if position(r.get('StarPos'))}}
    if event=='Scan' and entry.get('BodyName'):
        row=k.bodies.setdefault(entry['BodyName'],{})
        for source,key in (('DistanceFromArrivalLS','distance'),('PlanetClass','type')):
            if source in entry:row[key]=entry[source]
    if event in ('SAASignalsFound','FSSBodySignals') and entry.get('BodyName'):
        k.bodies.setdefault(entry['BodyName'],{})['signals']=Knowledge.bio_count(entry.get('Signals',[]))
    for category in ('Raw','Manufactured','Encoded'):
        values=entry.get(category) if event=='Materials' else state.get(category)
        if isinstance(values,dict):
            k.materials[category]={str(n):v for n,v in values.items() if number(v) and v>=0}
        elif isinstance(values,list):
            k.materials[category]={v['Name']:v['Count'] for v in values
                if isinstance(v,dict) and isinstance(v.get('Name'),str) and number(v.get('Count')) and v['Count']>=0}
    cargo=state.get('Cargo')
    if isinstance(cargo,dict):k.inventory={str(n):v for n,v in cargo.items() if number(v) and v>=0}
    elif event=='Cargo' and entry.get('Vessel','Ship')=='Ship' and isinstance(entry.get('Inventory'),list):
        k.inventory={v['Name_Localised'] if v.get('Name_Localised') else v['Name']:v['Count']
            for v in entry['Inventory'] if isinstance(v,dict) and isinstance(v.get('Name'),str) and number(v.get('Count'))}
    if event=='DockingGranted':k.pad=entry.get('LandingPad')
    if event in ('DockingCancelled','DockingTimeout','DockingDenied','Undocked','StartJump'):k.pad=None


def suite_snapshot(knowledge, plugins=None, question=''):
    """Read existing suite memory on the Tk thread, with independent adapters."""
    if plugins is None:
        try:
            from plug import PLUGINS
            plugins=PLUGINS
        except ImportError:return {}
    result={}
    for plugin in tuple(plugins):
        folder=getattr(plugin,'folder','')
        module=getattr(plugin,'module',None)
        if module is None:continue
        try:
            if folder in ('Navigator_Cartography','Systems_Navigator'):
                context=module.context
                if ((context.commander,bool(context.is_beta))!=knowledge.owner
                        or (context.name or '').casefold()!=knowledge.system.casefold()):continue
                atlas=module._atlas
                key=atlas.owner(context.commander,context.is_beta)+'/'+knowledge.system.casefold()
                record=atlas.data.get('systems',{}).get(key,{})
                target=distance_target(question)
                target_key=atlas.owner(context.commander,context.is_beta)+'/'+target
                target_record=atlas.data.get('systems',{}).get(target_key,{})
                target_xyz=position(field(target_record.get('meta',{}),'coords'))
                if target_xyz:result['coordinates']={target:target_xyz}
                result['bodies']={field(row,'name',name):{
                    'signals':Knowledge.bio_count(field(row,'signals',[])),
                    'distance':field(row,'distance'), 'type':field(row,'type')}
                    for name,row in record.get('bodies',{}).items() if isinstance(row,dict)}
                result['meta']={name:field(record.get('meta',{}),name) for name in
                    ('population','economy','government','allegiance','security')}
                result['objects']=[{name:field(row,name) for name in ('name','type','distanceToArrival','services')}
                    for row in record.get('objects',{}).values() if isinstance(row,dict)]
                traders=getattr(module,'_traders',{}).get(knowledge.system.casefold())
                if isinstance(traders,dict):result['traders']=copy.deepcopy(traders)
                xyz=position(context.coordinates) or position(field(record.get('meta',{}),'coords'))
                if xyz:result['position']=xyz
            elif folder.startswith(('Navigator_Navigation','Navigator_Neutron_Highway','Neutron_Highway_Navigator')):
                snapshot=module._snapshot
                if (str(snapshot.get('location',{}).get('system_name','')).casefold()!=knowledge.system.casefold()
                        or bool(snapshot.get('game',{}).get('is_beta'))!=bool(knowledge.owner and knowledge.owner[1])):continue
                systems=module._route_systems
                index=module._route_index
                if systems:
                    result['navigator']=dict(end=systems[-1],next=systems[index+1] if 0<=index+1<len(systems) else None,
                        waypoints_left=max(0,len(systems)-index-1) if index>=0 else 'unknown',
                        kind=getattr(module,'_route_kind','route'),source='Loaded Navigator route')
            elif folder in ('Navigator_Dashboard','Ship_Computer') and knowledge.owner and not knowledge.owner[1]:
                if module._active_commander!=knowledge.owner[0]:continue
                odo=module._odo
                result['trip']={key:odo.get(key) for key in ('trip_ly','trip_jumps','trip_seconds','trip_landings')}
                cargo=module._cargo
                if cargo.known:result['cargo']=dict(cargo.counts)
                synthesis=module._synthesis
                result['materials']={category:dict(synthesis.materials.get(category,{})) for category in synthesis.known}
            elif folder in ('Navigator_Radio','Ship_Radio'):
                source=module._settings.get('source')
                title=module._title_now
                if source=='galnet':
                    tracks=module._tracks or module._galnet
                    if tracks:title=tracks[module._track%len(tracks)].get('title')
                elif source=='music' and module._tracks:
                    # Basename only: no file reads and no private directory/URL.
                    from pathlib import Path
                    title=Path(module._tracks[module._track%len(module._tracks)]).stem
                result['radio']=dict(state=module._state,title=title or 'Title unavailable',
                    source=module.SOURCE_LABELS.get(source,'Radio'))
        except (AttributeError,KeyError,TypeError,ValueError,IndexError):
            # An unavailable/version-changed plugin cannot break other answers.
            continue
    return result


def intent(question, opts):
    key=spoken(question)
    topic=next((q['topic'] for q in opts['queries'] if spoken(q['phrase'])==key),None)
    if topic=='life' and re.search(r'\b(nearest|closest)\b',key):return 'nearest_life'
    if topic:return topic
    if re.search(r'\bfuel\b',key) and (key=='fuel' or re.search(r'\b(my|our|status|level|remaining|left|much|have)\b',key)):
        return 'fuel'
    if re.search(r'\bcredits\b',key) and re.search(r'\b(my|our|many|balance|have)\b',key):return 'credits'
    if re.search(r'\bcargo\b',key) and (key=='cargo' or re.search(r'\b(my|our|have|aboard|onboard)\b',key)):return 'cargo'
    patterns=(
        ('trader',r'\b(?:material trader|materials trader|raw trader|encoded trader|manufactured trader)s?\b'),
        ('nearest_life',r'\b(?:nearest|closest)\b.*\b(?:life|biological|biology)\b'),
        ('trip',r'\btrip\b.*\b(?:distance|summary|jumps|travelled|traveled)\b|\b(?:travelled|traveled)\b.*\btrip\b'),
        ('distance',r'\b(?:how far|distance to|distance from here to)\b'),
        ('jumps',r'\bjumps?\b.*\b(?:left|remaining|remain|to go)\b'),
        ('route',r'\b(?:next waypoint|next stop|route destination|route summary|end of (?:my |the )?route)\b'),
        ('inventory',r'\b(?:how (?:much|many) .+ (?:do i|do we) have|material inventory|materials aboard)\b'),
        ('radio',r'\b(?:radio|now playing|song|track playing)\b'),
        ('docking',r'\b(?:landing pad|docking status|docked)\b'),
        ('system_info',r'\b(?:population|economy|government|allegiance|security)\b.*\b(?:system|here)\b'),
        ('services',r'\b(?:interstellar factors|station services|what services|shipyard|outfitting|repair station)\b'),
        ('help',r'^(?:help|what can you (?:do|tell me)|what can i ask|hello|hi|thank you|thanks)$'),
        ('system',r'\b(?:which|what) (?:star )?system (?:am i|are we)\b|^where (?:am i|are we)$'),
        ('ship',r'\b(?:what|which) ship (?:am i|are we)\b'))
    for topic,pattern in patterns:
        if re.search(pattern,key):return topic
    return None


class BuiltInChatbot:
    def __init__(self, knowledge):self.knowledge=knowledge

    def answer(self, question, opts, suite=None):
        k=self.knowledge;suite=suite or {};key=spoken(question)
        topic=intent(question,opts)
        if topic=='help':
            return ('Built In Chatbot answers from local game data and already-loaded plugin information. '
                'Ask about fuel, cargo, biological signals, nearest recorded life, material traders, distance to Sol or a known system, '
                'jumps remaining, next waypoint, materials, your trip, radio, landing pad, system facts or station services. '
                'No API key or online lookup is used.')
        if topic not in ('nearest_life','trader','distance','jumps','route','inventory','trip','radio','docking','system_info','services'):
            counts={name:row.get('signals',0) for name,row in suite.get('bodies',{}).items()}
            if topic=='cargo' and k.inventory is not None:
                counts_cargo=k.inventory
                return self.cargo(counts_cargo,opts)
            if topic=='cargo' and suite.get('cargo') is not None:return self.cargo(suite['cargo'],opts)
            return k.answer(question,{**opts,'reports_enabled':True},counts)
        if topic=='nearest_life':
            bodies=copy.deepcopy(suite.get('bodies',{}))
            for name,row in k.bodies.items():bodies.setdefault(name,{}).update(row)
            for name,count in k.life.items():bodies.setdefault(name,{})['signals']=count
            found=[(name,row) for name,row in bodies.items() if number(row.get('signals')) and row['signals']>0]
            known=[(row['distance'],name,row) for name,row in found if number(row.get('distance')) and row['distance']>=0]
            if not found:return 'No biological signals are recorded for this system yet. Unscanned bodies may still have life.'
            if not known:return 'Life is recorded on '+', '.join(name for name,_ in found[:4])+', but their distances are unknown, so I cannot rank the nearest.'
            distance,name,row=min(known,key=lambda item:item[0])
            return ('Closest recorded life by distance from the arrival star: {} at {:,.1f} light-seconds, {} biological signals. '
                    'This is not a live distance from your ship.'.format(name,distance,row['signals'])+
                    (' Some recorded life-bearing bodies have unknown distances.' if len(known)<len(found) else '')+
                    ' Unscanned bodies may be closer.')
        if topic=='distance':
            target=distance_target(question)
            origin=k.position or position(suite.get('position'))
            goal=k.coordinates.get(target) or position(suite.get('coordinates',{}).get(target))
            if target==k.system.casefold():goal=origin
            if not origin:return 'Current system coordinates are unknown. I need a Location or jump update to calculate distance.'
            if goal is None:return 'Coordinates for '+target+' are not available locally. I have not made an online lookup.'
            distance=math.dist(origin,goal)
            return 'Straight-line distance to {}: {:,.1f} light-years. A plotted route can be longer.'.format(target.title(),distance)
        if topic in ('jumps','route'):
            navigator=suite.get('navigator') or {}
            if topic=='route' and navigator:
                return 'Loaded Navigator route: next waypoint {}, destination {}, {} waypoints remaining. Waypoints can require multiple jumps.'.format(
                    navigator.get('next') or 'none',navigator.get('end') or 'unknown',navigator['waypoints_left'])
            if number(k.game_jumps):
                return 'Game-plotted route: {} jumps remaining{}.'.format(int(k.game_jumps),
                    ' to '+k.game_destination if k.game_destination else '')+(
                    ' This is the current game leg; the Navigator destination is '+navigator['end']+'.'
                    if navigator.get('end') and k.game_destination and spoken(navigator['end'])!=spoken(k.game_destination) else '')
            if navigator:
                return 'The game jump count is unknown. Navigator has {} waypoints remaining to {}; waypoints are not individual jumps.'.format(
                    navigator['waypoints_left'],navigator.get('end') or 'unknown')
            return 'No current plotted jump count is available. Plot a route in the game to supply that information.'
        if topic=='trader':
            item=suite.get('traders') or {};data=item.get('data') or {}
            categories=[c for c in ('Raw','Manufactured','Encoded') if c.casefold() in key.split()]
            if not categories:categories=['Raw','Manufactured','Encoded']
            replies=[]
            for category in categories:
                rows=(data.get(category) or {}).get('results') or []
                rows=[row for row in rows if isinstance(row,dict)]
                if not rows:
                    replies.append(category+': no cached result');continue
                row=min(rows,key=lambda r:r['distance'] if number(r.get('distance')) else float('inf'))
                reply='{}: {} in {}'.format(category,row.get('name') or 'unknown station',row.get('system_name') or 'unknown system')
                if number(row.get('distance')):reply+=', {:,.1f} light-years from this system'.format(row['distance'])
                if number(row.get('distance_to_arrival')):reply+=', {:,.0f} light-seconds from its arrival star'.format(row['distance_to_arrival'])
                replies.append(reply)
            age='Cache age unknown.'
            if number(item.get('when')):age='Cache received {} minutes ago.'.format(max(0,int((time.time()-item['when'])/60)))
            return 'Cached nearest known material traders: '+'; '.join(replies)+'. '+age+' Station data may be outdated. No lookup was made; permit and docking restrictions may apply.'
        if topic=='inventory':
            categories={**suite.get('materials',{}),**k.materials}
            match=re.search(r'how (?:much|many) (.+?) (?:do i|do we) have',key)
            if not match:
                return 'Recorded materials: '+', '.join('{} ({} units)'.format(c,sum(v.values())) for c,v in categories.items())+'.' if categories else 'Material inventory is unknown until a materials snapshot is received.'
            name=match.group(1);lookup=re.sub(r'[\s_-]','',name)
            found=[(category,value) for category,values in categories.items() for material,value in values.items()
                   if re.sub(r'[\s_-]','',spoken(material))==lookup]
            if not found:
                cargo=k.inventory if k.inventory is not None else suite.get('cargo',{})
                for commodity,value in cargo.items():
                    if re.sub(r'[\s_-]','',spoken(commodity))==('drones' if lookup=='limpets' else lookup) and number(value):
                        return 'Recorded ship cargo: {}: {:g} tonnes.'.format(name,value)
                return 'I have no recorded entry for '+name+'. I will not assume that means zero.'
            return name.title()+': '+', '.join('{} {} units'.format(value,category.lower()) for category,value in found)+'.'
        if topic=='trip':
            trip=suite.get('trip') or {}
            if not number(trip.get('trip_ly')):return 'Dashboard trip data is not available for this commander.'
            return 'Dashboard trip: {:,.1f} light-years, {} jumps, {} landings.'.format(
                trip['trip_ly'],trip.get('trip_jumps') if number(trip.get('trip_jumps')) else 'unknown',
                trip.get('trip_landings') if number(trip.get('trip_landings')) else 'unknown')
        if topic=='radio':
            radio=suite.get('radio') or {}
            return 'Radio: {}. {} — {}.'.format(radio['state'],radio['source'],radio['title']) if radio else 'Radio playback information is not available.'
        if topic=='docking':
            return 'Assigned landing pad: {}{}.'.format(k.pad,' at '+k.station if k.station else '') if k.pad is not None else 'No current landing pad assignment is recorded.'
        if topic=='system_info':
            meta=suite.get('meta') or {};fields=[name for name in ('population','economy','government','allegiance','security') if name in key.split()]
            if not fields:fields=list(meta)
            return 'Recorded system data: '+', '.join('{}: {}'.format(name,meta.get(name) if meta.get(name) is not None else 'unknown') for name in fields)+'. Cached information may be outdated.' if fields else 'System information is not available locally.'
        if topic=='services':
            wanted=next((v for v in ('interstellar factors','shipyard','outfitting','repair') if v in key),'')
            normalize=lambda s:re.sub(r'[^a-z0-9]','',str(s).casefold())
            objects=[]
            for obj in suite.get('objects',[]):
                services=obj.get('services') or []
                services=[services] if isinstance(services,str) else services
                if not wanted or any(normalize(wanted) in normalize(s) for s in services):objects.append(obj)
            if not objects:return 'No matching station services are recorded in this system. That does not prove the service is absent; no lookup was made.'
            objects.sort(key=lambda o:o['distanceToArrival'] if number(o.get('distanceToArrival')) else float('inf'))
            descriptions=[]
            for obj in objects[:4]:
                text=obj.get('name') or 'unknown station'
                if number(obj.get('distanceToArrival')):text+=' ({:,.0f} light-seconds from arrival)'.format(obj['distanceToArrival'])
                if not wanted:
                    services=obj.get('services') or []
                    text+=': '+(services if isinstance(services,str) else ', '.join(map(str,services)) or 'services unknown')
                descriptions.append(text)
            return 'Recorded in this system: '+'; '.join(descriptions)+'. Service and access information may be outdated.'
        return None

    @staticmethod
    def cargo(counts, opts):
        values=[(name,value) for name,value in counts.items() if number(value) and value>0]
        limit=5 if opts['response_length']=='Brief' else 15
        return 'Recorded ship cargo: '+('; '.join('{}: {:g} tonnes'.format(name,value) for name,value in values[:limit])
            if values else 'empty')+(' and {} more commodities'.format(len(values)-limit) if len(values)>limit else '')+'.'
