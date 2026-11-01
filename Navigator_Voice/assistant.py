# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Local Assistant knowledge and deterministic routing. No network access here."""
from __future__ import annotations
import copy
import math
import re
import time
from urllib.parse import urlsplit

TOPICS = {'fuel': 'Fuel status', 'life': 'Biological signals', 'system': 'Current system',
          'ship': 'Ship', 'cargo': 'Cargo', 'credits': 'Credits', 'help': 'Assistant help',
          'nearest_life': 'Nearest recorded life', 'trader': 'Material traders',
          'distance': 'Distance to a system', 'jumps': 'Jumps remaining', 'route': 'Route summary',
          'inventory': 'Material inventory', 'trip': 'Trip summary', 'radio': 'Now playing',
          'docking': 'Docking and landing pad', 'system_info': 'System information',
          'services': 'Station services'}


def builtin_profile():
    return dict(id='builtin', name='Built In Chatbot', kind='builtin', endpoint='', model='')


def spoken(text):
    return re.sub(r'\s+', ' ', re.sub(r'[^\w\s\-\']', ' ', str(text))).strip().casefold()


def defaults():
    phrases = {'fuel': ['what is my fuel status', "what's my fuel status", 'fuel status'],
               'life': ['what planet in this system has life', 'which planets have life',
                        'where are the biological signals'],
               'system': ['where am i', 'what system am i in'],
               'ship': ['what ship am i flying'], 'cargo': ['what is my cargo'],
               'credits': ['how many credits do i have'], 'help': ['assistant help', 'what can you tell me'],
               'nearest_life': ['where is the nearest planet with life'],
               'trader': ['where is the material trader', 'where is the raw material trader'],
               'distance': ['how far is it to Sol'], 'jumps': ['how many jumps do i have left'],
               'route': ['what is my next waypoint', 'what is my route destination'],
               'inventory': ['how much iron do i have'], 'trip': ['how far have i travelled this trip'],
               'radio': ['what is playing on the radio'], 'docking': ['what is my landing pad'],
               'system_info': ['what is the population of this system'],
               'services': ['where can i find interstellar factors']}
    return dict(reports_enabled=False, conversation_enabled=False, keyword_only=True,
                keyword='Computer', aliases=[], speak=True, response_length='Brief',
                use_frontier=False, share_context=False, allow_online=False,
                active_profile='builtin', profiles=[builtin_profile(),
                    dict(id='local', name='Local Ollama', kind='ollama',
                         endpoint='http://127.0.0.1:11434', model=''),
                    dict(id='openai', name='OpenAI', kind='openai',
                         endpoint='https://api.openai.com/v1', model='')],
                queries=[dict(phrase=p, topic=t) for t, ps in phrases.items() for p in ps])


def options(settings):
    result = defaults()
    result.update(copy.deepcopy(settings.get('assistant_settings', {})))
    # Add the built-in choice to older saved setups without replacing their
    # selected provider, names, model choices, credentials or report phrases.
    profiles = result.get('profiles')
    if isinstance(profiles, list):
        builtins = [p for p in profiles if isinstance(p, dict) and p.get('id') == 'builtin']
        result['profiles'] = (builtins or [builtin_profile()]) + [p for p in profiles
            if not isinstance(p, dict) or p.get('id') != 'builtin']
    return result


def ship_prefix(settings):
    wake = str(settings.get('wake_word', '')).strip().casefold()
    return wake if settings.get('ship_keyword_only', bool(wake)) else ''


def local_endpoint(endpoint):
    return urlsplit(endpoint).hostname in ('localhost', '127.0.0.1', '::1')


def validate_options(settings):
    raw = settings.get('assistant_settings', {})
    if not isinstance(raw, dict):
        raise ValueError('Assistant settings must be an object')
    def contains_secret(value):
        if isinstance(value, dict):
            return any(str(k).casefold() in ('api_key','apikey','token','secret','password','authorization')
                       or contains_secret(v) for k,v in value.items())
        return isinstance(value, list) and any(contains_secret(v) for v in value)
    if contains_secret(raw):
        raise ValueError('API keys belong in Windows Credential Manager, not portable settings')
    opts = options(settings)
    for key in ('reports_enabled', 'conversation_enabled', 'keyword_only', 'speak',
                'use_frontier', 'share_context', 'allow_online'):
        if not isinstance(opts[key], bool):
            raise ValueError('Assistant ' + key + ' must be true or false')
    if 'ship_keyword_only' in settings and not isinstance(settings['ship_keyword_only'], bool):
        raise ValueError('Ship Inputs keyword switch must be true or false')
    for keyword in (opts['keyword'], settings.get('wake_word', '')):
        if not isinstance(keyword, str) or len(keyword) > 80:
            raise ValueError('Keywords must be text, up to 80 characters')
    if not isinstance(opts['aliases'], list) or len(opts['aliases']) > 12:
        raise ValueError('Use up to 12 Assistant keyword aliases')
    words = [opts['keyword']] + opts['aliases']
    if any(not isinstance(w, str) or not spoken(w) or len(w) > 80 for w in words):
        raise ValueError('Enter a nonempty Assistant keyword and aliases')
    if len(set(map(spoken, words))) != len(words):
        raise ValueError('Assistant keywords and aliases must be distinct')
    if opts['response_length'] not in ('Brief', 'Detailed'):
        raise ValueError('Choose Brief or Detailed replies')
    enabled = opts['reports_enabled'] or opts['conversation_enabled']
    if settings.get('ship_keyword_only', False) and not spoken(settings.get('wake_word', '')):
        raise ValueError('Enter a keyword for Ship Inputs, or turn Keyword Only off')
    ship = spoken(ship_prefix(settings))
    if enabled and opts['keyword_only'] and ship and any(
            w == ship or w.startswith(ship+' ') or ship.startswith(w+' ')
            for w in map(spoken, words)):
        raise ValueError('Ship Inputs and Assistant keywords must be distinct')
    if not isinstance(opts['queries'], list) or len(opts['queries']) > 200:
        raise ValueError('Use up to 200 local report phrases')
    seen = set()
    for query in opts['queries']:
        if not isinstance(query, dict) or query.get('topic') not in TOPICS:
            raise ValueError('Choose a supported local report topic')
        phrase = query.get('phrase', '')
        if not isinstance(phrase, str) or not spoken(phrase) or len(phrase) > 150:
            raise ValueError('Report phrases need 1 to 150 characters')
        if spoken(phrase) in seen:
            raise ValueError('Duplicate report phrase: ' + phrase)
        seen.add(spoken(phrase))
    profiles = opts['profiles']
    if not isinstance(profiles, list) or not 1 <= len(profiles) <= 21:
        raise ValueError('Keep Built In Chatbot and up to 20 AI connections')
    ids = set()
    for p in profiles:
        if not isinstance(p, dict) or any(k not in ('id', 'name', 'kind', 'endpoint', 'model') for k in p):
            raise ValueError('Invalid AI connection; API keys do not belong in settings')
        if any(not isinstance(p.get(k), str) or len(p[k]) > 300 for k in ('id','name','kind','endpoint','model')):
            raise ValueError('Connection fields must be text, up to 300 characters')
        if not re.fullmatch(r'[\w-]{1,80}', p['id']) or p['id'] in ids or not p['name'].strip():
            raise ValueError('Connections need unique IDs and nonempty names')
        ids.add(p['id'])
        if p['kind'] == 'builtin':
            if p != builtin_profile():
                raise ValueError('Built In Chatbot is a fixed offline choice')
            continue
        if p['id'] == 'builtin':
            raise ValueError('The built-in ID is reserved for Built In Chatbot')
        u = urlsplit(p['endpoint'])
        if u.scheme not in ('http', 'https') or not u.hostname or u.username or u.password or u.query or u.fragment:
            raise ValueError('Use a plain HTTP(S) connection address without credentials')
        if u.scheme != 'https' and not local_endpoint(p['endpoint']):
            raise ValueError('Remote AI connections require HTTPS')
        if p['kind'] not in ('ollama', 'openai', 'compatible'):
            raise ValueError('Choose Ollama, OpenAI, or OpenAI-compatible')
        if p['kind'] == 'ollama' and not local_endpoint(p['endpoint']):
            raise ValueError('Local Ollama must use a loopback address')
        if p['kind'] == 'openai' and p['endpoint'].rstrip('/') != 'https://api.openai.com/v1':
            raise ValueError('OpenAI uses https://api.openai.com/v1; choose compatible for other servers')
    if opts['active_profile'] not in ids:
        raise ValueError('Select an available AI connection')
    return opts


def route(text, settings, index):
    """Exact macros only; assistant-addressed speech never falls through to keys."""
    key = spoken(text)
    opts = options(settings)
    enabled = opts['reports_enabled'] or opts['conversation_enabled']
    macro = next((m for p, m in index.items() if spoken(p) == key), None)
    ship = spoken(ship_prefix(settings))
    control_prefix = ship + ' ' if ship else ''
    if key in (control_prefix+'cancel macro', control_prefix+'stop listening'):
        return 'control', key[len(control_prefix):]
    if enabled:
        for word in sorted(map(spoken, [opts['keyword']] + opts['aliases']), key=len, reverse=True):
            if key == word or key.startswith(word+' '):
                if macro is not None:
                    if not opts['keyword_only']:
                        continue  # An optional assistant name must not steal an exact ship command.
                    return 'ambiguous', 'That phrase matches both Assistant and a macro. Use distinct phrases.'
                return 'assistant', key[len(word):].strip()
    # With both keywords off, conflicting report/macro phrases require clarification.
    if macro is not None:
        if opts['reports_enabled'] and not opts['keyword_only'] and any(spoken(q['phrase']) == key for q in opts['queries']):
            return 'ambiguous', 'That phrase matches both a report and a macro. Add a keyword or change the phrase.'
        return 'macro', macro
    if enabled and not opts['keyword_only']:
        return 'assistant', key
    return 'unmatched', key


def recognition_phrases(settings, index):
    opts = options(settings)
    wake = ship_prefix(settings)
    result = set(index) | {(wake+' ' if wake else '')+c for c in ('cancel macro', 'stop listening')}
    builtin = next(p for p in opts['profiles'] if p['id']==opts['active_profile'])['kind']=='builtin'
    if opts['reports_enabled'] or (opts['conversation_enabled'] and builtin):
        prefixes = [opts['keyword']] + opts['aliases'] if opts['keyword_only'] else ['']
        result.update((p+' ' if p else '')+q['phrase'] for p in prefixes for q in opts['queries'])
    return sorted(result)


class Knowledge:
    def __init__(self):
        self.clear()

    def clear(self):
        self.owner = None
        self.system = self.station = self.ship = ''
        self.credits = None
        self.fuel = self.cargo = None
        self.fuel_at = self.cargo_at = 0
        self.life = {}
        self.frontier = None
        self.position = None
        self.coordinates = {'sol': (0., 0., 0.)}
        self.bodies = {}
        self.materials = {}
        self.inventory = None
        self.nav_route = None
        self.nav_index = 0
        self.game_jumps = self.game_destination = None
        self.target = None
        self.nav_seen = self.in_jump = self.route_ending = False
        self.pad = None

    def journal(self, cmdr, beta, system, station, entry, state=None):
        owner = (cmdr, bool(beta))
        if entry.get('event') in ('Shutdown', 'Fileheader'):
            self.clear()
            return
        if self.owner != owner:
            self.clear()
            self.owner = owner
        if system != self.system:
            self.life = {}
            self.bodies = {}
            self.position = None
            self.pad = None
        self.system, self.station = system or '', station or ''
        from .chatbot import update_knowledge
        update_knowledge(self, entry, state or {})
        if entry.get('event') in ('LoadGame', 'Loadout'):
            self.ship = entry.get('ShipName') or entry.get('Ship') or self.ship
        if entry.get('event') == 'LoadGame':
            self.credits = entry.get('Credits')
        if entry.get('event') in ('SAASignalsFound', 'FSSBodySignals') and entry.get('BodyName'):
            self.life[entry['BodyName']] = self.bio_count(entry.get('Signals', []))

    @staticmethod
    def bio_count(signals):
        if not isinstance(signals, (list, tuple)):
            return 0
        return sum(s.get('Count', 0) for s in signals if isinstance(s, dict)
                   and 'biological' in str(s.get('Type', '')).casefold()
                   and isinstance(s.get('Count'), (int, float)) and math.isfinite(s['Count']) and s['Count']>0)

    def dashboard(self, entry):
        now = time.monotonic()
        # Missing fields replace old telemetry rather than implying it is current.
        self.fuel, self.fuel_at = entry.get('Fuel'), now
        self.cargo, self.cargo_at = entry.get('Cargo'), now

    def capi(self, data, beta):
        commander = data.get('commander') or {}
        if self.owner != (commander.get('name'), bool(beta)):
            return
        # Whitelist only useful facts; never retain tokens/full account payloads.
        self.frontier = dict(at=time.monotonic(), credits=commander.get('credits'),
                             system=(data.get('lastSystem') or {}).get('name'),
                             station=(data.get('lastStarport') or {}).get('name'))

    def answer(self, question, opts, cached_life=None):
        key = spoken(question)
        topic = next((q['topic'] for q in opts['queries'] if spoken(q['phrase']) == key), None)
        # Natural variations remain local, including unknown/missing-data replies.
        if topic is None:
            if re.search(r'\bfuel\b', key) and (key=='fuel' or re.search(r'\b(my|our|status|level|remaining|left|much|have)\b',key)):
                topic = 'fuel'
            elif re.search(r'\b(biological|biology)\b', key) or ('life' in key.split() and re.search(r'\b(planet|planets|bodies|system)\b',key)):
                topic = 'life'
            elif re.search(r'\bcredits\b', key) and re.search(r'\b(my|our|many|balance|have)\b',key):
                topic = 'credits'
            elif re.search(r'\bcargo\b', key) and (key=='cargo' or re.search(r'\b(my|our|have|aboard|onboard)\b',key)):
                topic = 'cargo'
        if topic is None or not opts['reports_enabled']:
            return None
        if topic == 'help':
            return 'Ask about fuel, biological signals, your system, ship, cargo or credits. Edit report phrases in Assistant settings.'
        if topic == 'system': return 'Current system: ' + (self.system or 'unknown') + '.'
        if topic == 'ship': return 'Current ship: ' + (self.ship or 'unknown') + '.'
        if topic == 'credits':
            if (opts['use_frontier'] and self.frontier and isinstance(self.frontier.get('credits'), (int,float))
                    and math.isfinite(self.frontier['credits'])):
                return 'Frontier snapshot: {:,.0f} credits, received {} minutes ago.'.format(
                    self.frontier['credits'], int((time.monotonic()-self.frontier['at'])/60))
            return 'Current credit balance is unknown. Enable Frontier snapshots and use EDMC Update to receive an account snapshot.'
        if topic in ('fuel', 'cargo'):
            value, at = (self.fuel, self.fuel_at) if topic == 'fuel' else (self.cargo, self.cargo_at)
            if time.monotonic()-at > 30 or value is None:
                return 'Current ' + topic + ' telemetry is unavailable or more than 30 seconds old.'
            if topic == 'cargo':
                return 'Cargo on board: {:g} tonnes.'.format(value) if isinstance(value,(int,float)) and math.isfinite(value) else 'Cargo amount is unknown.'
            main = value.get('FuelMain') if isinstance(value, dict) else None
            reserve = value.get('FuelReservoir') if isinstance(value, dict) else None
            if not isinstance(main, (int,float)) or not math.isfinite(main):
                return 'Main fuel level is unknown.'
            text = 'Main fuel: {:g} tonnes.'.format(round(main, 2))
            if isinstance(reserve, (int,float)):
                text += ' Reservoir: {:g} tonnes.'.format(round(reserve, 2))
            return text
        if topic == 'life':
            bodies = dict(cached_life or {})
            bodies.update(self.life)
            found = ['{} ({} signals)'.format(name, count) for name, count in sorted(bodies.items()) if count > 0]
            if not found:
                return 'No biological signals are recorded in the available data for this system. Unscanned bodies may still have life.'
            limit = 4 if opts['response_length'] == 'Brief' else 15
            return 'Recorded biological signals: ' + '; '.join(found[:limit]) + (
                '; and {} more bodies.'.format(len(found)-limit) if len(found)>limit else '.') + ' Scan coverage may be incomplete.'
        return None

    def context(self):
        return dict(system=self.system or 'unknown', ship=self.ship or 'unknown',
                    fuel=self.fuel if time.monotonic()-self.fuel_at <= 30 else None,
                    biological_signals=dict(self.life))
