# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""EDMC entrypoint; isolate all modules in a unique package namespace."""
from pathlib import Path
import importlib
import importlib.util
import sys

_NAME = "_edmc_voice_navigator"
_FOLDER = Path(__file__).resolve().parent
if _NAME not in sys.modules:
    _spec = importlib.util.spec_from_file_location(
        _NAME, _FOLDER / "__init__.py", submodule_search_locations=[str(_FOLDER)])
    _package = importlib.util.module_from_spec(_spec)
    sys.modules[_NAME] = _package
    _spec.loader.exec_module(_package)

_app = importlib.import_module(_NAME + ".app")
plugin_start3 = _app.plugin_start3
plugin_app = _app.plugin_app
plugin_stop = _app.plugin_stop
plugin_prefs = _app.plugin_prefs
prefs_changed = _app.prefs_changed
journal_entry = _app.journal_entry
dashboard_entry = _app.dashboard_entry
cmdr_data = _app.cmdr_data
