# SPDX-License-Identifier: GPL-3.0-only
"""pcMonitor – zuverlässige GTK-Ausgabe auch ohne DRI3/GPU-Zugriff.

Die Portübersicht benötigt kein OpenGL. Cairo zeichnet auf CPU und folgt
weiterhin dem Systemthema. Die Einstellung muss vor jedem GTK/GDK-Import
erfolgen, damit auch CLI-, Desktop- und Adminstarts gleich reagieren.
"""
import os


def configure_rendering(environment=None):
    environment = os.environ if environment is None else environment
    environment.setdefault('GSK_RENDERER','cairo')
    if environment['GSK_RENDERER']=='cairo':
        flags=environment.get('GDK_DEBUG','').replace(' ',':').split(':')
        for flag in ('gl-disable','vulkan-disable'):
            if flag not in flags:flags.append(flag)
        environment['GDK_DEBUG']=':'.join(flag for flag in flags if flag)


configure_rendering()
