# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""EDMC coordinator. Only the Tk main thread changes widgets."""
from __future__ import annotations
import copy
import os
from pathlib import Path
import queue
import shutil
import time
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from . import __version__
from .bindings import BindingCatalog
from .commands import CONTROL_PHRASES, GameState, MacroRunner, load_settings, normalise, phrase_map, save_settings, validate
from .speech import SpeechHost
from .wininput import WindowsInput
from .assistant import Knowledge, options as assistant_options, route, recognition_phrases, validate_options
from .ai import AIClient
from .chatbot import BuiltInChatbot, suite_snapshot
try:
    from config import config as edmc_config
except ImportError:
    edmc_config = None

def data_folder():
    if edmc_config is not None:
        for name in ("app_dir_path", "app_dir"):
            value = getattr(edmc_config, name, None)
            if value:
                return Path(value) / "Voice_Navigator"
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "EDMarketConnector" / "Voice_Navigator"

def palette(widget):
    background = widget.master.cget("background")
    text, accent = "SystemWindowText", "#2161a5"
    if edmc_config is not None:
        try:
            if edmc_config.get_int("theme"):
                from theme import theme
                background = (getattr(theme, "current", {}) or {}).get("background") or background
                text = edmc_config.get_str("dark_text") or "#ff8000"
                accent = edmc_config.get_str("dark_highlight") or "#ffffff"
        except (ImportError, KeyError, ValueError, TypeError, AttributeError):
            pass
    return background, text, accent

class Navigator:
    def __init__(self, folder, settings_path=None):
        self.folder = Path(folder)
        self.path = Path(settings_path) if settings_path else data_folder() / "settings.json"
        self.settings, self.recovery = load_settings(self.path)
        self.events = queue.Queue(maxsize=2000)
        self.catalog, self.state = BindingCatalog(), GameState()
        self.runner = MacroRunner(WindowsInput(), self.state, self.emit)
        self.knowledge, self.ai = Knowledge(), AIClient()
        self.chatbot = BuiltInChatbot(self.knowledge)
        self.assistant_answer = ''
        self._assistant_generation, self._ai_busy = 0, False
        self.host = SpeechHost(self.folder, self.path.parent / "speech-cache", self.events)
        self.frame = self.manager = self.timer = None
        self.stopped = self.listening = self.starting = False
        self.logs, self.last_phrase, self.last_heard = [], ("", 0.), ""
        self.status_text = "Stopped"
        self.latest_text = self.recovery or ""
        self._colors = None
        self._collapsed = None
        self._theme_job = None
        self._theme_bindings = []
        self.reload_bindings()
    def emit(self, kind, value):
        try:
            self.events.put_nowait(("macro", kind, value))
        except queue.Full:
            pass
    def log(self, text):
        line = time.strftime("%H:%M:%S") + "  " + str(text)
        if self.settings.get("activity_log_enabled", True):
            self.logs = (self.logs + [line])[-250:]
            if self.manager is not None and self.manager.winfo_exists():
                self.manager.append_log(line)
        self.latest_text = str(text)
        self.render()
    def persist(self, candidate):
        validate(candidate)
        if self.recovery and self.path.exists():
            shutil.copy2(self.path, self.path.with_name("settings.recovered-" + str(time.time_ns()) + ".json"))
            self.recovery = ""
        save_settings(self.path, candidate)
        self.settings = copy.deepcopy(candidate)
    def apply_settings(self, candidate):
        running = self.listening or self.starting
        self.persist(candidate)
        if not assistant_options(self.settings)['use_frontier']:
            self.knowledge.frontier = None
        self.apply_theme()
        self.stop_listening()
        self.reload_bindings()
        if self.manager is not None and self.manager.winfo_exists():
            self.manager.refresh()
        if running:
            self.start_listening()
        self.render()
    def reload_bindings(self):
        catalog = BindingCatalog()
        try:
            if self.settings.get("bindings_cleared", False):
                catalog.warnings.append("All keybindings cleared in (N) Voice")
                self.catalog, self.index = catalog, {}
            else:
                catalog.reload(override=self.settings.get("binds_override", ""))
                self.catalog, self.index = catalog, phrase_map(self.settings)
        except (OSError, ValueError) as error:
            self.latest_text = "Bindings: " + str(error)
            self.catalog, self.index = catalog, {}
    def build(self, parent):
        self.frame = tk.Frame(parent)
        # Same symmetric header structure as Radio. Interface owns alignment.
        self.frame.columnconfigure((0, 2), uniform="voice_header_edges")
        self.frame.columnconfigure(1, weight=1)
        self.header = tk.Frame(self.frame)
        self.header.grid(row=0, column=1)
        self.title = tk.Label(self.header, text="Voice")
        self.title.grid(row=0, column=0)
        self.title.navigator_no_wrap = True
        self.header_sep = tk.Label(self.header, text="  |  ", padx=0, bd=0)
        self.header_sep.grid(row=0, column=1)
        self.header_sep.grid_remove()
        self.collapse_button = tk.Button(self.frame, text="\U0001f53c", command=self.toggle_collapsed)
        self.collapse_button.grid(row=0, column=2, sticky="ne")
        self.status = tk.Label(self.frame)
        self.status.navigator_no_wrap = True
        self.status.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(2, 4))
        buttons = tk.Frame(self.frame)
        self.buttons = buttons
        buttons.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(0, 5))
        for col in range(3):
            buttons.columnconfigure(col, weight=1, uniform="voicebuttons")
        self.listen_button = tk.Button(buttons, text="Listen", command=self.toggle_listening)
        self.listen_button.grid(row=0, column=0, sticky="ew", padx=(0, 2))
        tk.Button(buttons, text="Cancel Macro", command=self.cancel_macro).grid(row=0, column=1, sticky="ew", padx=2)
        tk.Button(buttons, text="Settings…", command=self.open_manager).grid(row=0, column=2, sticky="ew", padx=(2, 0))
        top = self.frame.winfo_toplevel()
        for event in ("<<ThemeChanged>>", "<<NavigatorThemeChanged>>"):
            self._theme_bindings.append((top, event, top.bind(event, self.schedule_theme, add="+")))
        self.apply_theme()
        self.frame.bind("<Destroy>", self.destroyed, add="+")
        self.render()
        self.timer = self.frame.after(100, self.poll)
        return self.frame
    def destroyed(self, event):
        if event.widget is self.frame:
            self.close()
    def schedule_theme(self, event=None):
        if not self.stopped and self._theme_job is None:
            self._theme_job = self.frame.after_idle(self.apply_theme)
    def apply_theme(self):
        self._theme_job = None
        if self.frame is None or self.stopped:
            return
        try:
            from plug import invoke
            invoke("(N) Interface", "Navigator Interface", "navigator_set_panel_contrast", "Navigator_Voice",
                   self.settings.get("high_contrast_background", False))
        except ImportError:
            pass
        background, text, accent = palette(self.frame)
        if self.settings.get("high_contrast_background", False):
            background = "black"
            if edmc_config is None or not edmc_config.get_int("theme"):
                text, accent = "white", "#ff8000"
        self._colors = background, text, accent
        def paint(widget):
            if isinstance(widget, (tk.Frame, tk.Label, tk.Button)):
                widget.configure(background=background)
            if isinstance(widget, tk.Label):
                widget.configure(foreground=text)
            # Suite rule (30 Oct 2026, Claude): clickable buttons use Highlighted Text. Listen keeps
            # its documented state colours (Highlighted while listening, Normal while stopped) in render().
            if isinstance(widget, tk.Button):
                widget.configure(foreground=accent)
            if isinstance(widget, tk.Button):
                widget.configure(activebackground=background, activeforeground=accent, highlightthickness=0)
            for child in widget.winfo_children():
                paint(child)
        paint(self.frame)
        self.title.configure(foreground=text)   # suite headers use Normal Text
        # Like every other plugin's collapse button, it is Normal Text (the Listen button keeps its own state colours).
        self.collapse_button.configure(foreground=text, activeforeground=text)
        self.render()
    def render(self):
        if self.frame is None or self.stopped:
            return
        collapsed = self.settings.get("collapsed", False)
        if collapsed != self._collapsed:
            self._collapsed = collapsed
            self.collapse_button.configure(text="\U0001f53d" if collapsed else "\U0001f53c")
            if collapsed:
                self.buttons.grid_remove()
                self.header_sep.grid()
                self.status.grid(in_=self.header, row=0, column=2, columnspan=1, sticky="", pady=0)
            else:
                self.header_sep.grid_remove()
                self.status.grid(in_=self.frame, row=1, column=0, columnspan=3, sticky="ew", pady=(2, 4))
                self.buttons.grid()
        if self.status.cget("text") != self.status_text:
            self.status.configure(text=self.status_text)
        active = self.listening or self.starting
        listen_text = "Stop Listening" if active else "Listen"
        if self.listen_button.cget('text') != listen_text:
            self.listen_button.configure(text=listen_text)
        if self.settings.get("listen_status_colors", False):
            listen_color = "#d32f2f" if active else "#1f9d3a"
        else:
            listen_color = self._colors[2] if active else self._colors[1]
        if self.listen_button.cget("foreground") != listen_color:
            self.listen_button.configure(foreground=listen_color)
    def toggle_collapsed(self):
        candidate = copy.deepcopy(self.settings)
        candidate['collapsed'] = not candidate.get('collapsed', False)
        try:
            self.persist(candidate)
            self.render()
        except (OSError, ValueError) as error:
            self.log('Could not save panel state: ' + str(error))
    def toggle_listening(self):
        self.stop_listening() if self.listening or self.starting else self.start_listening()
    def start_listening(self):
        self.reload_bindings()
        assistant = assistant_options(self.settings)
        if not self.index and not (assistant['reports_enabled'] or assistant['conversation_enabled']):
            self.log("Enable at least one voice macro before listening.")
            return
        self.host.start(self.settings, recognition_phrases(self.settings, self.index))
        self.starting, self.status_text = True, "Starting"
        self.log("Starting offline recognition. First use may build the local helper.")
    def stop_listening(self):
        self._assistant_generation += 1
        self.host.stop()
        self.runner.cancel()
        self.listening = self.starting = False
        self.status_text = "Stopped"
        self.render()
    def check_engine(self):
        self.stop_listening()
        self.host.start(self.settings, [], mode="probe")
        self.status_text = "Checking Engine"
        self.render()
    def preview_tts(self, settings):
        if self.listening and not self.starting:
            self.host.speak("(N) Voice test.", settings)
            self.log("TTS preview sent to the active speech host")
            return
        self.host.start(settings, [], mode="tts_preview", text="(N) Voice test.")
        self.status_text = "TTS Preview"
        self.render()
    def cancel_macro(self):
        self.runner.cancel()
        self.log("Macro cancellation requested")
    def preview(self, macro):
        if not self.runner.submit(macro, self.catalog, True):
            self.log("A macro is already running")
    def recognised(self, event):
        text = str(event.get("text", ""))
        confidence = float(event.get("confidence", 0))
        self.last_heard = "%s (%d%%)" % (text, round(confidence * 100))
        if confidence < float(self.settings.get("confidence", .72)):
            self.log("Below recognition threshold: " + text)
            return
        kind, value = route(text, self.settings, self.index)
        if kind == 'control':
            self.cancel_macro() if value == 'cancel macro' else self.stop_listening()
            return
        if kind == 'ambiguous':
            self.deliver_answer(value)
            return
        key = normalise(text)
        if kind == 'unmatched':
            self.log("No matching macro: " + text)
            return
        now = time.monotonic()
        if key == self.last_phrase[0] and now - self.last_phrase[1] < .8:
            return
        self.last_phrase = (key, now)
        if kind == 'assistant':
            self.ask_assistant(value)
            return
        if not self.runner.submit(value, self.catalog, False):
            self.log("A macro is running; phrase ignored")
    def deliver_answer(self, text, speak=True):
        self.assistant_answer = str(text)
        if self.manager is not None and self.manager.winfo_exists():
            self.manager.assistant_page.set_answer(self.assistant_answer)
        self.log('Assistant: '+self.assistant_answer)
        if speak and assistant_options(self.settings)['speak'] and self.listening:
            try:
                self.host.speak(self.assistant_answer, self.settings)
            except OSError as error:
                self.log('Assistant speech unavailable: '+str(error))
    def ask_assistant(self, question, test=False, candidate=None):
        settings = candidate if candidate is not None else self.settings
        opts = validate_options(settings)
        profile = next(p for p in opts['profiles'] if p['id']==opts['active_profile'])
        builtin = profile['kind']=='builtin'
        if test and builtin:
            self.deliver_answer('Built In Chatbot is ready. No connection or API key is needed. '+
                self.chatbot.answer('assistant help', opts), speak=False)
            return
        if test:
            question = 'Reply with the word Connected.'
        elif not question.strip():
            self.deliver_answer('What would you like to know?')
            return
        elif not (opts['reports_enabled'] or opts['conversation_enabled']):
            self.deliver_answer('Enable local reports or conversational AI in Assistant settings.', speak=False)
            return
        if not test:
            local = self.chatbot.answer(question, opts, suite_snapshot(self.knowledge, question=question)) if (
                opts['reports_enabled'] or (builtin and opts['conversation_enabled'])) else None
            if local is not None:
                self._assistant_generation += 1  # A newer local answer supersedes an old AI request.
                self.deliver_answer(local)
                return
            if builtin:
                self.deliver_answer('Built In Chatbot does not understand that question yet. Say Assistant help for supported topics, '
                                    'or add a report phrase in settings. No online request was made.')
                return
            if not opts['conversation_enabled']:
                self.deliver_answer('I can answer the local report topics listed in Assistant settings. Conversational AI is off.')
                return
        if self._ai_busy:
            self.deliver_answer('An AI request is already running.', speak=False)
            return
        generation = self._assistant_generation
        facts = self.knowledge.context()
        self._ai_busy = True
        self.deliver_answer('Testing AI connection…' if test else 'Asking '+profile['name']+'…', speak=False)
        def work():
            try:
                answer = self.ai.answer(profile, question, opts, facts, test=test)
                if test: answer = 'Connection replied: '+answer
            except (ValueError, OSError) as error:
                answer = str(error)
            try:
                self.events.put_nowait(('assistant', generation, (answer, not test)))
            except queue.Full:
                # A full queue is transient; allow the UI drain to make room.
                try: self.events.put(('assistant', generation, (answer, not test)), timeout=1)
                except queue.Full: pass
        threading.Thread(target=work, daemon=True).start()
    def poll(self):
        if self.stopped:
            return
        try:
            for _ in range(120):
                item = self.events.get_nowait()
                if item[0] == 'assistant':
                    self._ai_busy = False
                    if item[1] == self._assistant_generation:
                        self.deliver_answer(item[2][0], speak=item[2][1])
                    continue
                if item[0] == "macro":
                    kind, value = item[1:]
                    if kind == "done":
                        self.log(("Preview complete: " if value["dry_run"] else "Macro complete: ") + value["name"])
                        if (not value["dry_run"] and value["reply"] and value.get("speak_reply", False)
                                and self.settings.get("speak_replies", True) and self.listening):
                            try:
                                self.host.speak(value["reply"], self.settings)
                            except OSError as error:
                                self.log("Reply unavailable: " + str(error))
                    else:
                        self.log(("Error: " if kind == "error" else "") + str(value))
                    continue
                _, generation, event = item
                if generation != self.host.generation:
                    continue
                kind = event.get("type")
                if kind == "ready":
                    self.listening, self.starting, self.status_text = True, False, "Listening"
                    self.log("Offline recognizer ready: " + event.get("culture", ""))
                elif kind == "recognized" and self.listening:
                    self.recognised(event)
                elif kind == "probe":
                    engines = event.get("recognizers", [])
                    voices = event.get("voices", [])
                    if self.manager is not None and self.manager.winfo_exists():
                        self.manager.set_tts_voices(voices)
                    self.status_text = "Stopped"
                    recognizer_text = ("Available recognizers: " + ", ".join(e["name"] for e in engines)
                                       if engines else "No Windows desktop recognizer is available to this process.")
                    voice_text = ("Installed TTS voices: " + ", ".join(v["name"] for v in voices)
                                  if voices else "No installed Windows TTS voices were detected.")
                    self.log(recognizer_text + " | " + voice_text)
                elif kind == "tts_preview":
                    self.status_text = "Stopped"
                    self.log("TTS preview completed")
                elif kind == "error":
                    self.listening = self.starting = False
                    self.status_text = {"no_microphone": "No Mic Connected",
                                        "audio_input_unavailable": "Microphone Unavailable"}.get(
                                            event.get("code"), "Engine Error")
                    self.runner.cancel()
                    self.log("Speech: " + event.get("message", "Unknown error"))
                elif kind == "warning":
                    self.log(event.get("message", "Speech helper warning"))
                elif kind == "exited":
                    running = self.listening or self.starting
                    self.listening = self.starting = False
                    if self.status_text not in ("Engine Error", "Microphone Unavailable", "No Mic Connected"):
                        self.status_text = "Stopped"
                    self.runner.cancel()
                    if running:
                        self.log("Speech helper stopped (exit %s)" % event.get("code"))
        except queue.Empty:
            pass
        except (ValueError, TypeError) as error:
            self.log("Voice event: " + str(error))
        self.render()
        if not self.stopped:
            self.timer = self.frame.after(100, self.poll)
    def open_manager(self):
        from .editor import MacroManager
        if self.manager is not None and self.manager.winfo_exists():
            self.manager.lift()
        else:
            self.manager = MacroManager(self)
    def close(self):
        if self.stopped:
            return
        self.stopped = True
        self._assistant_generation += 1
        for top, event, binding in self._theme_bindings:
            top.unbind(event, binding)
        self._theme_bindings.clear()
        if self.frame is not None and self._theme_job is not None:
            self.frame.after_cancel(self._theme_job)
            self._theme_job = None
        self.host.stop()
        self.runner.close()
        if self.frame is not None and self.timer is not None:
            try:
                self.frame.after_cancel(self.timer)
            except tk.TclError:
                pass
        if self.manager is not None:
            try:
                self.manager.destroy()
            except tk.TclError:
                pass

_app = None
def plugin_start3(plugin_dir):
    global _app
    _app = Navigator(plugin_dir)
    return "(N) Voice"
def plugin_app(parent):
    return _app.build(parent)
def plugin_stop():
    if _app:
        _app.close()
def dashboard_entry(cmdr, is_beta, entry):
    if _app:
        _app.state.update(entry)
        _app.knowledge.dashboard(entry)
def journal_entry(cmdr, is_beta, system, station, entry, state):
    if _app:
        previous = (_app.knowledge.owner, _app.knowledge.system)
        _app.knowledge.journal(cmdr, is_beta, system, station, entry, state)
        if previous != (_app.knowledge.owner, _app.knowledge.system):
            _app._assistant_generation += 1
        if entry.get("event") in ("Shutdown", "Fileheader"):
            _app.state.clear()

def cmdr_data(data, is_beta):
    if _app and assistant_options(_app.settings)['use_frontier']:
        _app.knowledge.capi(data, is_beta)
def plugin_prefs(parent, cmdr, is_beta):
    try:
        import myNotebook as nb
        try:
            from plug import invoke
            outer = invoke("(N) Interface", "Navigator Interface", "navigator_scroll_settings", parent)
            frame = getattr(outer, "navigator_settings_content", None)
        except ImportError:
            outer = None
            frame = None
        if frame is None:
            outer = nb.Frame(parent)
            frame = outer
        nb.Label(frame, text="(N) Voice " + __version__).grid(row=0, column=0, padx=10, pady=10, sticky="w")
        nb.Label(frame, text="Offline recognition, Elite bindings, and editable voice macros.").grid(row=1, column=0, padx=10, sticky="w")
        ttk.Button(frame, text="Commands and Listening Settings…", command=_app.open_manager).grid(row=2, column=0, padx=10, pady=10, sticky="w")
        _app._prefs_contrast = tk.BooleanVar(frame, value=_app.settings.get("high_contrast_background", False))
        nb.Checkbutton(frame, text="High Contrast Background", variable=_app._prefs_contrast).grid(
            row=3, column=0, padx=10, pady=(0, 10), sticky="w")
        return outer
    except ImportError:
        return tk.Frame(parent)
def prefs_changed(cmdr, is_beta):
    if _app:
        preference = getattr(_app, "_prefs_contrast", None)
        if preference is not None:
            try:
                candidate = copy.deepcopy(_app.settings)
                candidate["high_contrast_background"] = preference.get()
                _app.persist(candidate)
            except (OSError, ValueError, tk.TclError) as error:
                _app.log("Could not save background preference: " + str(error))
            finally:
                _app._prefs_contrast = None
        _app.schedule_theme()
