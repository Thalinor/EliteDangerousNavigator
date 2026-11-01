# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Ship Radio audio engine: a hidden helper using Windows' own players.

Windows Media Player's control (WMPlayer.OCX) plays internet streams and music
files; System.Speech reads Galnet aloud. Both ship with Windows, so nothing is
installed. The helper is a windowless PowerShell process that takes one JSON
command per line on stdin and reports state as JSON lines on stdout.

Only the main (Tk) thread calls Engine methods. A reader thread moves stdout
lines into a queue; load.py drains it from its Tk timer.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import queue
import subprocess
import sys
import threading

try:
    from .streaming import StreamRelay
except ImportError:
    from streaming import StreamRelay

logger = logging.getLogger(__name__)

HELPER_SCRIPT = r"""
$ErrorActionPreference = 'Continue'
$utf8 = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = $utf8
function Say($o) { [Console]::Out.WriteLine(($o | ConvertTo-Json -Compress)); [Console]::Out.Flush() }

# Console.In.ReadLineAsync can block synchronously on redirected console input.
# Keep pipe reads off the media player's STA thread so network playback and COM
# messages continue while the user is not pressing buttons.
Add-Type -AssemblyName System.Windows.Forms
Add-Type -TypeDefinition @'
using System;
using System.Collections.Concurrent;
using System.Threading;
public static class ShipRadioInput {
    private static readonly BlockingCollection<string> Lines = new BlockingCollection<string>();
    public static void Start() {
        Thread reader = new Thread(() => {
            try {
                string line;
                while ((line = Console.In.ReadLine()) != null) Lines.Add(line);
            } finally { Lines.Add("{\"cmd\":\"quit\"}"); }
        });
        reader.IsBackground = true;
        reader.Start();
    }
    public static bool TryRead(out string line) { return Lines.TryTake(out line, 50); }
}
'@
[ShipRadioInput]::Start()

$wmp = $null; $voice = $null
try { $wmp = New-Object -ComObject WMPlayer.OCX; $wmp.settings.autoStart = $false }
catch { Say @{ ev = 'error'; what = 'player'; msg = $_.Exception.Message } }
try { Add-Type -AssemblyName System.Speech; $voice = New-Object System.Speech.Synthesis.SpeechSynthesizer }
catch { Say @{ ev = 'error'; what = 'voice'; msg = $_.Exception.Message } }
$defaultVoice = if ($voice) { $voice.Voice.Name } else { '' }
Say @{ ev = 'ready'; player = ($wmp -ne $null); voice = ($voice -ne $null) }

$mode = ''; $userStop = $true; $lastKey = ''; $lastPos = -1; $wasActive = $false
$running = $true
while ($running) {
  [System.Windows.Forms.Application]::DoEvents()
  $line = $null
  if ([ShipRadioInput]::TryRead([ref]$line)) {
    try { $c = $line | ConvertFrom-Json } catch { continue }
    try {
      switch ([string]$c.cmd) {
        'play' {
          if ($voice) { if ($voice.State -eq 'Paused') { $voice.Resume() }; $voice.SpeakAsyncCancelAll() }
          $mode = 'media'; $userStop = $false; $wasActive = $false
          $wmp.URL = [string]$c.url
          $wmp.controls.play()
        }
        'speak' {
          if ($wmp) { $wmp.controls.stop() }
          if ($voice.State -eq 'Paused') { $voice.Resume() }
          $voice.SpeakAsyncCancelAll()
          $mode = 'voice'; $userStop = $false; $wasActive = $false
          $voice.SelectVoice($defaultVoice)
          if ($c.voice) {
            try { $voice.SelectVoice([string]$c.voice) }
            catch { Say @{ ev = 'notice'; msg = 'Selected voice unavailable; using Windows default.' } }
          }
          $voice.Rate = [Math]::Max(-10, [Math]::Min(10, [int]$c.rate))
          if ($null -ne $c.volume) { $voice.Volume = [Math]::Max(0,[Math]::Min(100,[int]$c.volume)) }
          $pitch = [Math]::Max(-50,[Math]::Min(50,[int]$c.pitch))
          if ($pitch -eq 0) { [void]$voice.SpeakAsync([string]$c.text) }
          else {
            $escaped = [System.Security.SecurityElement]::Escape([string]$c.text)
            $lang = $voice.Voice.Culture.Name
            $value = if ($pitch -gt 0) { '+' + $pitch + '%' } else { '' + $pitch + '%' }
            $ssml = '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="' + $lang + '"><prosody pitch="' + $value + '">' + $escaped + '</prosody></speak>'
            try { [void]$voice.SpeakSsmlAsync($ssml) }
            catch {
              Say @{ ev = 'notice'; msg = 'Pitch unavailable for this voice; using normal pitch.' }
              [void]$voice.SpeakAsync([string]$c.text)
            }
          }
        }
        'voices' {
          $names = @($voice.GetInstalledVoices() | Where-Object { $_.Enabled } | ForEach-Object { $_.VoiceInfo.Name })
          Say @{ ev = 'voices'; names = $names; default = $defaultVoice }
        }
        'pause' {
          if ($mode -eq 'voice') { if ($voice.State -eq 'Speaking') { $voice.Pause() } }
          elseif ($wmp) { $wmp.controls.pause() }
        }
        'resume' {
          if ($mode -eq 'voice') { if ($voice.State -eq 'Paused') { $voice.Resume() } }
          elseif ($wmp) { $wmp.controls.play() }
        }
        'stop' {
          $userStop = $true
          if ($voice) { if ($voice.State -eq 'Paused') { $voice.Resume() }; $voice.SpeakAsyncCancelAll() }
          if ($wmp) { $wmp.controls.stop() }
          $mode = ''
        }
        'seek' { if ($wmp) { $wmp.controls.currentPosition = [double]$c.pos } }
        'volume' {
          $v = [Math]::Max(0, [Math]::Min(100, [int]$c.value))
          if ($wmp) { $wmp.settings.volume = $v }
          if ($voice) { $voice.Volume = if ($null -ne $c.voice_value) { [Math]::Max(0,[Math]::Min(100,[int]$c.voice_value)) } else { $v } }
        }
        'voice_volume' { if ($voice) { $voice.Volume = [Math]::Max(0,[Math]::Min(100,[int]$c.value)) } }
        'quit' { $running = $false }
      }
    } catch { Say @{ ev = 'error'; what = [string]$c.cmd; msg = $_.Exception.Message } }
  }

  $state = 'stopped'; $title = ''; $pos = 0; $dur = 0
  if ($mode -eq 'voice' -and $voice) {
    $vs = [string]$voice.State
    if ($vs -eq 'Speaking') { $state = 'playing'; $wasActive = $true }
    elseif ($vs -eq 'Paused') { $state = 'paused' }
    elseif ($wasActive -and -not $userStop) { $state = 'ended'; $mode = ''; $wasActive = $false }
  } elseif ($mode -eq 'media' -and $wmp) {
    $ps = [int]$wmp.playState
    if ($ps -eq 3) { $state = 'playing'; $wasActive = $true }
    elseif ($ps -eq 2) { $state = 'paused' }
    elseif ($ps -eq 6 -or $ps -eq 7 -or $ps -eq 9 -or $ps -eq 10 -or $ps -eq 11) { $state = 'loading' }
    elseif (($ps -eq 8 -or $ps -eq 1) -and $wasActive -and -not $userStop) { $state = 'ended'; $mode = ''; $wasActive = $false }
    elseif ($ps -eq 1 -and -not $userStop) { $state = 'loading' }
    try {
      if ($wmp.currentMedia) {
        $title = [string]$wmp.currentMedia.getItemInfo('Title')
        $dur = [double]$wmp.currentMedia.duration
      }
      $pos = [double]$wmp.controls.currentPosition
    } catch { }
    if ($wmp.error.errorCount -gt 0) {
      $msg = [string]$wmp.error.item(0).errorDescription
      $wmp.error.clearErrorQueue()
      $userStop = $true; $mode = ''; $wasActive = $false
      Say @{ ev = 'error'; what = 'media'; msg = $msg }
      $state = 'stopped'
    }
  }
  $key = "$state|$title"
  $whole = [int][Math]::Floor($pos)
  if ($key -ne $lastKey -or ($state -eq 'playing' -and $whole -ne $lastPos)) {
    $lastKey = $key; $lastPos = $whole
    Say @{ ev = 'state'; state = $state; title = $title; pos = $pos; dur = $dur }
  }
}
if ($voice) { $voice.SpeakAsyncCancelAll(); $voice.Dispose() }
if ($wmp) { $wmp.controls.stop(); $wmp.close() }
"""

CREATE_NO_WINDOW = 0x08000000


def powershell_path() -> str:
    root = os.environ.get("SystemRoot", r"C:\Windows")
    path = os.path.join(root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    return path if os.path.isfile(path) else "powershell.exe"


class Engine:
    """Start lazily, talk JSON, never block the Tk thread."""

    def __init__(self) -> None:
        self.process: subprocess.Popen | None = None
        self.events: queue.Queue = queue.Queue()
        self.failed = ""
        self._relay = None

    @staticmethod
    def available() -> bool:
        return sys.platform == "win32"

    def command(self) -> list[str]:
        encoded = base64.b64encode(HELPER_SCRIPT.encode("utf-16-le")).decode("ascii")
        return [powershell_path(), "-NoLogo", "-NoProfile", "-NonInteractive", "-STA",
                "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded]

    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(self) -> bool:
        if self.running():
            return True
        flags = CREATE_NO_WINDOW if sys.platform == "win32" else 0
        try:
            self.process = subprocess.Popen(
                self.command(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, creationflags=flags)
        except OSError as error:
            self.failed = str(error)
            logger.warning("Ship Radio: could not start the audio helper: %s", error)
            self.process = None
            return False
        threading.Thread(target=self._read, args=(self.process,), name="ShipRadioEngine", daemon=True).start()
        return True

    def _read(self, process: subprocess.Popen) -> None:
        stream = process.stdout
        if stream is None:
            return
        for raw in iter(stream.readline, b""):
            line = raw.decode("utf-8", errors="replace").strip().lstrip("\ufeff")
            if not line.startswith("{"):
                continue
            try:
                event = json.loads(line)
                relay = self._relay
                if event.get('ev') == 'state' and relay is not None and relay.url:
                    event['title'] = ''  # the player's local stream token is not a track title
                self.events.put(event)
            except ValueError:
                continue
        self.events.put({"ev": "exit"})

    def send(self, cmd: str, **values) -> bool:
        if not self.start():
            return False
        if cmd in ('play', 'stop', 'speak') and self._relay is not None:
            self._relay.stop()
        if cmd == 'play' and str(values.get('url', '')).lower().startswith(('http://', 'https://')):
            try:
                if self._relay is None:
                    self._relay = StreamRelay(self.events)
                values['url'] = self._relay.select(values['url'])
            except OSError:
                self.events.put({'ev': 'error', 'what': 'media', 'msg': 'Could not start internet playback.'})
                return False
        line = json.dumps({"cmd": cmd, **values}, ensure_ascii=True) + "\n"
        try:
            assert self.process is not None and self.process.stdin is not None
            self.process.stdin.write(line.encode("ascii"))
            self.process.stdin.flush()
            return True
        except (OSError, ValueError, AssertionError):
            logger.warning("Ship Radio: the audio helper stopped; it will restart on the next command")
            self.process = None
            return False

    def drain(self) -> list[dict]:
        items = []
        while True:
            try:
                event = self.events.get_nowait()
                token = event.pop('stream_token', None)
                if token is None or (self._relay is not None and token == self._relay.token):
                    items.append(event)
            except queue.Empty:
                return items

    def close(self) -> None:
        if self._relay is not None:
            self._relay.close()
            self._relay = None
        process, self.process = self.process, None
        if process is None or process.poll() is not None:
            return
        try:
            assert process.stdin is not None
            process.stdin.write(b'{"cmd": "quit"}\n')
            process.stdin.flush()
            process.stdin.close()
            process.wait(timeout=1.5)
        except Exception:
            pass
        if process.poll() is None:
            try:
                process.kill()
            except OSError:
                pass
