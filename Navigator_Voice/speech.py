# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Build and supervise the offline Windows speech helper without blocking Tk."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
from .assistant import options

def build_host(folder, cache):
    if os.name != "nt":
        raise OSError("Speech recognition requires Windows")
    source = folder / "VoiceHost.cs"
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    cache.mkdir(parents=True, exist_ok=True)
    executable = cache / ("VoiceHost-" + digest + ".exe")
    if executable.is_file():
        return executable
    windows = Path(os.environ.get("WINDIR", r"C:\Windows"))
    compilers = [windows / "Microsoft.NET" / arch / "v4.0.30319" / "csc.exe"
                 for arch in ("Framework64", "Framework")]
    compiler = next((p for p in compilers if p.is_file()), None)
    assembly_root = windows / "Microsoft.NET" / "assembly" / "GAC_MSIL" / "System.Speech"
    speech = next(assembly_root.glob("*/System.Speech.dll"), None)
    if compiler is None or speech is None:
        raise OSError("Windows .NET Framework 4.x speech components were not found. See README.")
    temporary = cache / ("VoiceHost-" + digest + ".building.exe")
    command = [str(compiler), "/nologo", "/target:exe", "/platform:anycpu", "/optimize+",
               "/out:" + str(temporary), "/reference:" + str(speech),
               "/reference:System.Web.Extensions.dll", str(source)]
    try:
        process = subprocess.run(command, capture_output=True, timeout=45,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        if process.returncode != 0 or not temporary.exists():
            detail = (process.stdout + process.stderr).decode(errors="replace").strip()
            raise OSError("The Windows voice helper could not build: " + (detail or str(process.returncode)))
        os.replace(temporary, executable)
    except subprocess.TimeoutExpired:
        raise OSError("Building the Windows voice helper timed out")
    finally:
        if temporary.exists():
            temporary.unlink()
    return executable

class SpeechHost:
    def __init__(self, folder, cache, events):
        self.folder, self.cache, self.events = folder, cache, events
        self.generation = 0
        self._process = None
        self._lock, self._write_lock = threading.Lock(), threading.Lock()
        self._build_lock = threading.Lock()
    def _event(self, generation, value):
        try:
            self.events.put_nowait(("speech", generation, value))
        except queue.Full:
            pass
    def start(self, settings, phrases, mode="listen", text=""):
        self.stop()
        generation = self.generation
        payload = {"mode": mode, "culture": settings.get("culture", ""), "phrases": sorted(phrases),
                   "tts_voice": settings.get("tts_voice", ""), "tts_rate": settings.get("tts_rate", 0),
                   "tts_pitch": settings.get("tts_pitch", "normal"),
                   "tts_volume": settings.get("tts_volume", 100), "text": text}
        assistant = options(settings)
        if assistant['reports_enabled'] or assistant['conversation_enabled']:
            payload['assistant_keywords'] = [assistant['keyword']] + assistant['aliases'] if assistant['keyword_only'] else []
            payload['assistant_dictation'] = True
        threading.Thread(target=self._launch, args=(generation, payload), daemon=True).start()
    def _launch(self, generation, payload):
        process = None
        try:
            with self._build_lock:
                executable = build_host(self.folder, self.cache)
            with self._lock:
                if generation != self.generation:
                    return
                process = subprocess.Popen([str(executable)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, encoding="utf-8", errors="replace", bufsize=1,
                    creationflags=subprocess.CREATE_NO_WINDOW)
                self._process = process
                # Write to this process before another start can replace it.
                with self._write_lock:
                    process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
                    process.stdin.flush()
            threading.Thread(target=self._stderr, args=(process, generation), daemon=True).start()
            self._read(process, generation)
        except (OSError, ValueError) as error:
            self._event(generation, {"type": "error", "message": str(error)})
            if process is not None:
                with self._lock:
                    if self._process is process:
                        self._process = None
                threading.Thread(target=self._reap, args=(process,), daemon=True).start()
    def speak(self, text, settings=None):
        settings = settings or {}
        with self._lock:
            process = self._process
            if process is None or process.poll() is not None:
                raise OSError("Voice helper is not running")
            with self._write_lock:
                process.stdin.write(json.dumps({"type": "speak", "text": text,
                    "tts_voice": settings.get("tts_voice", ""),
                    "tts_rate": settings.get("tts_rate", 0),
                    "tts_pitch": settings.get("tts_pitch", "normal"),
                    "tts_volume": settings.get("tts_volume", 100)}, ensure_ascii=False) + "\n")
                process.stdin.flush()
    def _read(self, process, generation):
        try:
            for line in process.stdout:
                try:
                    event = json.loads(line.lstrip("\ufeff"))
                    if isinstance(event, dict):
                        self._event(generation, event)
                except ValueError:
                    self._event(generation, {"type": "warning", "message": "Unexpected speech-helper output"})
            self._event(generation, {"type": "exited", "code": process.wait()})
        except (OSError, ValueError) as error:
            self._event(generation, {"type": "error", "message": str(error)})
        finally:
            process.stdout.close()
            with self._lock:
                if self._process is process:
                    self._process = None
            try:
                process.stdin.close()
            except (OSError, ValueError):
                pass
    def _stderr(self, process, generation):
        try:
            for line in process.stderr:
                self._event(generation, {"type": "warning", "message": line.strip()})
        except (OSError, ValueError):
            pass
        finally:
            process.stderr.close()
    @staticmethod
    def _reap(process):
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                process.terminate()
                process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    process.kill()
                except OSError:
                    pass
    def stop(self):
        with self._lock:
            self.generation += 1
            process, self._process = self._process, None
            if process is None:
                return
            with self._write_lock:
                try:
                    process.stdin.write('{"type":"stop"}\n')
                    process.stdin.flush()
                except (OSError, ValueError):
                    pass
        threading.Thread(target=self._reap, args=(process,), daemon=True).start()
