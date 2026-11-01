# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Standard EDMC settings controls for explicitly requested history jobs."""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime, timezone
import threading
import queue
import copy
import os

try:
    from . import history
except ImportError:
    import history


class Recovery:
    def __init__(self, host):
        self.host = host
        self.messages = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.label = None
        self.status = 'Recovery runs only when requested. No background online checks.'
        self.store = host._load('recovery.json', {'commanders': {}})
        self.window = None

    def commander(self):
        return (self.host._active_commander or history.latest_commander(self.host._journal_dir())
                or self.store.get('last_commander'))

    def record(self, commander):
        return self.store.get('commanders', {}).get((commander or '').casefold(), {})

    def save_record(self, commander, events=None, visits=None):
        record = self.record(commander).copy()
        if events is not None:
            record['events'] = history.unique_records(record.get('events', []), events)
        if visits is not None:
            record['visits'] = history.normalize_visits(record.get('visits', []) + visits)
        self.store.setdefault('commanders', {})[commander.casefold()] = record
        self.store['last_commander'] = commander
        history.atomic_json(os.path.join(self.host._data_dir(), 'recovery.json'), self.store)

    def set_status(self, text):
        self.status = text
        if self.label is not None:
            try:
                self.label.configure(text=text)
            except tk.TclError:
                self.label = None

    def start(self, name, worker, done):
        if self.busy or self.host._scanning:
            messagebox.showinfo('Dashboard History', 'Please let the current history job finish first.')
            return
        self.busy = True
        self.cancel.clear()
        self.set_status(name + '…')
        def run():
            try:
                result = worker()
                self.messages.put(('done', (done, result)))
            except Exception as error:
                # Workers use sanitized provider messages. No credentials are logged.
                self.messages.put(('error', str(error)))
        threading.Thread(target=run, name='DashboardHistory', daemon=True).start()

    def poll(self):
        while not self.messages.empty():
            kind, payload = self.messages.get_nowait()
            if kind == 'progress':
                self.set_status(payload)
            elif kind == 'error':
                self.busy = False
                self.set_status('History operation failed: ' + payload)
            else:
                self.busy = False
                callback, result = payload
                try:
                    callback(result)
                except Exception as error:
                    self.set_status('History operation failed: ' + str(error))

    def require_commander(self):
        name = self.commander()
        if not name:
            messagebox.showinfo('Dashboard History', 'Load your commander once, or restore a Dashboard backup first.')
        return name

    def import_journals(self):
        if not (name := self.require_commander()):
            return
        folder = filedialog.askdirectory(title='Select archived journals for ' + name)
        if not folder:
            return
        def work():
            records, _ = history.collect(folder, name, stop=self.cancel.is_set)
            if not records:
                raise ValueError('No matching commander journals were found in that folder.')
            return records
        def done(records):
            self.save_record(name, events=records)
            self.host._start_scan(fresh=True)
            self.set_status(f'Imported {len(records):,} journal records for {name}. Rebuilding odometer.')
        self.start('Reading archived journals', work, done)

    def export_backup(self):
        if not (name := self.require_commander()):
            return
        target = filedialog.asksaveasfilename(title='Export Dashboard backup', defaultextension='.json',
            initialfile='Dashboard_Backup_' + datetime.now().strftime('%Y-%m-%d') + '.json',
            filetypes=[('Dashboard backup', '*.json')])
        if not target:
            return
        self.host._count_trip_time()
        base = {'format': history.FORMAT, 'version': history.VERSION, 'commander': name,
                'created': datetime.now(timezone.utc).isoformat(),
                'odometer': copy.deepcopy(self.host._odo), 'stopwatch': copy.deepcopy(self.host._watch),
                'scope': self.host._stats_scope()}
        record = copy.deepcopy(self.record(name))
        folder = self.host._journal_dir()
        def work():
            base['events'], _ = history.collect(folder, name, record.get('events', []), stop=self.cancel.is_set)
            base['visits'] = record.get('visits', [])
            if not base['events'] and not base['visits']:
                raise ValueError('No journal history is available to back up yet.')
            history.atomic_json(target, base)
        self.start('Exporting Dashboard backup', work,
                   lambda _: self.set_status('Dashboard backup exported: ' + os.path.basename(target)))

    def restore_backup(self):
        source = filedialog.askopenfilename(title='Restore Dashboard backup', filetypes=[('Dashboard backup', '*.json')])
        if not source:
            return
        def done(data):
            name = self.commander()
            if name and name.casefold() != data['commander'].casefold():
                raise ValueError('This backup belongs to another commander. Load that commander before restoring it.')
            if not messagebox.askyesno('Restore Dashboard Backup',
                    'Merge this commander\'s saved history and restore their Trip and Stopwatch?\n'
                    'Existing history is retained. A safety copy of the current counters is saved first.'):
                self.set_status('Restore cancelled.')
                return
            odo = validate_state(data.get('odometer', {}), self.host._odo_defaults())
            watch = validate_state(data.get('stopwatch', {}), self.host._watch_defaults())
            if watch.get('running'):
                created = datetime.fromisoformat(data['created']).timestamp()
                start = watch.get('start')
                if start:
                    watch['elapsed'] = float(watch.get('elapsed', 0)) + max(0, created - start)
            watch['running'], watch['start'] = False, None
            history.atomic_json(os.path.join(self.host._data_dir(), 'before_restore.json'),
                {'format': history.FORMAT, 'version': history.VERSION,
                 'commander': name or data['commander'], 'created': datetime.now(timezone.utc).isoformat(),
                 'events': self.record(name).get('events', []), 'visits': self.record(name).get('visits', []),
                 'scope': self.host._stats_scope(), 'odometer': self.host._odo, 'stopwatch': self.host._watch})
            self.save_record(data['commander'], data['events'], data['visits'])
            if odo:
                self.host._odo.clear()
                self.host._odo.update(self.host._odo_defaults())
                self.host._odo.update(odo)
                self.host._trip_last = None
                self.host._session.clear()
                self.host._save('odometer.json', self.host._odo)
            if watch:
                # A restored running stopwatch must not accrue time while the PC was absent.
                self.host._watch.clear()
                self.host._watch.update(self.host._watch_defaults())
                self.host._watch.update(watch)
                self.host._save('stopwatch.json', self.host._watch)
            if data.get('scope') in self.host.STATS_SCOPES:
                self.host.config.set(self.host.PREFIX + 'StatsScope', data['scope'])
            self.host._start_scan(fresh=True)
            self.set_status('Backup restored; rebuilding merged history. Stopwatch restored paused.')
        self.start('Reading Dashboard backup', lambda: history.read_backup(source), done)

    def edsm_dialog(self):
        if self.busy or self.host._scanning:
            messagebox.showinfo('Dashboard History', 'Please let the current history job finish first.')
            return
        if not (name := self.require_commander()):
            return
        if self.window is not None and self.window.winfo_exists():
            self.window.lift()
            return
        window = self.window = tk.Toplevel(self.host._root)
        window.title('Import EDSM History')
        window.transient(self.host._root)
        window.columnconfigure(1, weight=1)
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        variables = [tk.StringVar(value=value) for value in (name, '', today[:4] + '-01-01', today)]
        ttk.Label(window, text='One-time download; nothing runs automatically.\n'
                  'Visits can extend Systems only after local jumps verify the ship.\n'
                  'Missing distance, jump counts and playtime cannot be inferred.\n'
                  'Large ranges take time: EDSM allows weekly batches at limited rates.',
                  justify='left').grid(row=0, column=0, columnspan=2, padx=12, pady=10, sticky='w')
        for row, (text, var) in enumerate(zip(('Commander', 'EDSM API Key', 'From (UTC YYYY-MM-DD)',
                                                              'Through (UTC YYYY-MM-DD)'), variables), 1):
            ttk.Label(window, text=text).grid(row=row, column=0, sticky='w', padx=12, pady=4)
            ttk.Entry(window, textvariable=var, show='*' if row == 2 else '',
                      state='readonly' if row == 1 else 'normal', width=28).grid(row=row, column=1, sticky='ew', padx=12, pady=4)
        ttk.Label(window, text='The key is used for this download only; it is not saved.').grid(
            row=5, column=0, columnspan=2, padx=12, pady=8)
        def begin():
            commander, key, start, finish = [v.get().strip() for v in variables]
            if not key:
                messagebox.showinfo('EDSM History', 'Enter your EDSM API key.', parent=window)
                return
            # Clear the visible key and destroy its field before the worker starts.
            variables[1].set('')
            window.destroy()
            def progress(done, total):
                self.messages.put(('progress', f'EDSM: {done} of {total} weekly batches downloaded.'))
            def done(result):
                visits, cancelled = result
                self.save_record(commander, visits=visits)
                self.host._start_scan(fresh=True)
                count = len(self.record(commander).get('visits', []))
                self.set_status(f'EDSM {"cancelled; completed batches saved" if cancelled else "import complete"}. '
                                f'{count:,} unique visits stored. Verified ship visits extend Systems only.')
            self.start('Downloading EDSM history',
                lambda: history.download_edsm(commander, key, start, finish, self.cancel, progress), done)
        ttk.Button(window, text='Import Once', command=begin).grid(row=6, column=0, padx=12, pady=12)
        ttk.Button(window, text='Close', command=window.destroy).grid(row=6, column=1, padx=12, pady=12, sticky='e')
        # Required Interface styles the dialog with the suite's popup palette and remembers its geometry.
        # Suite rule: the window never gets smaller than what shows all of its buttons.
        window.update_idletasks()
        window.minsize(window.winfo_reqwidth(), window.winfo_reqheight())
        window.navigator_window_id = 'Ship_Computer:edsm_import'
        try:
            from plug import invoke
            invoke("(N) Interface", "Navigator Interface", "navigator_attach_window", window)
        except ImportError:
            pass

    def build(self, parent, row):
        box = ttk.LabelFrame(parent, text='History Recovery and Backup')
        box.grid(row=row, column=0, sticky='ew', padx=10, pady=10)
        for i, (label, action) in enumerate((('Import Archived Journals…', self.import_journals),
                ('Export Dashboard Backup…', self.export_backup), ('Restore Dashboard Backup…', self.restore_backup),
                ('Import EDSM History Once…', self.edsm_dialog))):
            ttk.Button(box, text=label, command=action).grid(row=i // 2, column=i % 2, sticky='ew', padx=6, pady=4)
        ttk.Button(box, text='Cancel Current History Job', command=self.cancel.set).grid(
            row=2, column=0, columnspan=2, padx=6, pady=4)
        self.label = ttk.Label(box, text=self.status, wraplength=440, justify='left')
        self.label.grid(row=3, column=0, columnspan=2, padx=6, pady=8, sticky='w')
        ttk.Label(box, text='Archived journals and backups rebuild the odometer. Trip is unchanged by journal/EDSM imports.\n'
                  'Backup restore also restores Trip/Stopwatch. Inara has no documented history download API.',
                  wraplength=440, justify='left').grid(row=4, column=0, columnspan=2, padx=6, pady=6, sticky='w')


def validate_state(state, defaults):
    import math
    result = {}
    for key, value in state.items():
        if key not in defaults:
            continue
        if key == 'trip_systems':
            if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
                raise ValueError('Invalid Trip systems in backup.')
        elif key == 'laps':
            if not isinstance(value, list) or len(value) > 200:
                raise ValueError('Invalid Stopwatch laps in backup.')
            for lap in value:
                if not isinstance(lap, dict) or not all(isinstance(lap.get(k), (int, float))
                        and math.isfinite(lap[k]) and lap[k] >= 0 for k in ('n', 'lap', 'total', 'jumps', 'ly')):
                    raise ValueError('Invalid Stopwatch lap in backup.')
        elif value is not None:
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError('Invalid Dashboard counter in backup.')
            if isinstance(defaults[key], bool) and not isinstance(value, bool):
                raise ValueError('Invalid Dashboard switch in backup.')
            if isinstance(defaults[key], int) and not isinstance(defaults[key], bool) and not isinstance(value, int):
                raise ValueError('Invalid Dashboard count in backup.')
        elif defaults[key] is not None:
            raise ValueError('Missing Dashboard value in backup.')
        result[key] = value
    return result
