"""Grafikstart ohne GPU-Zugriff und nachvollziehbare frühe Fehler."""
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch
from monitor import configure_rendering
from launcher import preflight

class StartupTests(unittest.TestCase):
    def test_default_disables_gl_before_gtk(self):
        env={};configure_rendering(env)
        self.assertEqual(env['GSK_RENDERER'],'cairo')
        self.assertEqual(set(env['GDK_DEBUG'].split(':')),{'gl-disable','vulkan-disable'})
        configure_rendering(env)
        self.assertEqual(env['GDK_DEBUG'].count('gl-disable'),1)
    def test_preserves_other_debug_options_and_explicit_renderer(self):
        env={'GDK_DEBUG':'events'};configure_rendering(env)
        self.assertIn('events',env['GDK_DEBUG'])
        env={'GSK_RENDERER':'ngl'};configure_rendering(env)
        self.assertNotIn('GDK_DEBUG',env)
    def test_missing_source_is_reported_before_import(self):
        with TemporaryDirectory() as folder:
            self.assertIn('HM003',preflight(Path(folder)))
    def test_missing_gtk_has_actionable_error(self):
        from monitor.constants import ROOT
        with patch('launcher.subprocess.run') as run:
            run.return_value.returncode=1
            run.return_value.stderr='ModuleNotFoundError: gi'
            result=preflight(ROOT)
        self.assertIn('HM002',result)
        self.assertIn('python3-gi',result)
