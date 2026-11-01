# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Event-driven popup attachment."""


def attach_window(window, app):
    """Delegate generic popup styling/sizing to required (N) Interface.

    30 Oct 2026 (Claude, phase 2): call Interface through EDMC's plug.invoke by its
    "(N) Interface" name (old "Navigator Interface" as fallback) instead of searching
    sys.modules for its folder, so the planned folder rename cannot break it.
    """
    try:
        from plug import invoke
        if invoke("(N) Interface", "Navigator Interface", "navigator_attach_window", window):
            return
    except ImportError:
        pass
    except Exception as error:
        app.log('Shared window styling unavailable: ' + str(error))
    if not getattr(app, '_interface_notice_shown', False):
        app._interface_notice_shown = True
        app.log('Install or enable (N) Interface (formerly Navigator Interface) for shared window styling and saved positions.')
