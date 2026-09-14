"""Kernel-Fixtures: keine Abhängigkeit von realer Hardware und keine Änderungen daran."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from monitor.scanner import Scanner

class ScannerTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.root=Path(self.temp.name)
        self.scanner=Scanner(self.root/'sys',self.root/'proc',audio_runner=lambda:[])
    def tearDown(self):self.temp.cleanup()
    def write(self,name,value):
        p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(value);return p
    def test_usb_ports_and_device_identity(self):
        self.write('sys/bus/usb/devices/usb1/maxchild','3')
        self.write('sys/bus/usb/devices/usb1/busnum','1')
        self.write('sys/bus/usb/devices/usb1/version','2.00')
        self.write('sys/bus/usb/devices/1-2/product','Tastatur')
        self.write('sys/bus/usb/devices/1-2/idVendor','1234')
        ports=self.scanner.usb()
        self.assertEqual([p.state for p in ports],['empty','connected','empty'])
        self.assertEqual(ports[1].id,'usb:1-2')
        self.assertEqual(ports[1].device,'Tastatur')
        # Ausstecken aktualisiert denselben logischen Port, statt ihn zu verlieren.
        import shutil
        shutil.rmtree(self.root/'sys/bus/usb/devices/1-2')
        self.assertEqual(self.scanner.usb()[1].state,'empty')
    def test_external_usb_hub_has_its_own_ports(self):
        self.write('sys/bus/usb/devices/1-2/maxchild','2')
        self.write('sys/bus/usb/devices/1-2/busnum','1')
        self.assertEqual([p.id for p in self.scanner.usb()],['usb:1-2.1','usb:1-2.2'])
    def test_display_unknown_is_not_empty(self):
        self.write('sys/class/drm/card0-HDMI-A-1/status','unknown')
        self.write('sys/class/drm/card0-DP-1/status','disconnected')
        self.assertEqual({p.name:p.state for p in self.scanner.displays()},{'DP-1':'empty','HDMI-A-1':'unknown'})
    def test_network_zero_counters_and_disabled_interface(self):
        self.write('sys/class/net/eth0/device/uevent','')
        self.write('sys/class/net/eth0/carrier','0')
        self.write('sys/class/net/eth0/operstate','down')
        self.write('sys/class/net/eth0/statistics/rx_bytes','0')
        p=self.scanner.network()[0]
        self.assertEqual(p.state,'unknown');self.assertEqual(p.details['rx_bytes'],'0')
        self.write('sys/class/net/eth0/operstate','up')
        self.assertEqual(self.scanner.network()[0].state,'empty')
    def test_audio_availability_is_explicit(self):
        self.scanner.audio_runner=lambda:[{'name':'test','ports':{
            'a':{'availability':'available'},'b':{'availability':'not available'},'c':{'availability':'availability unknown'}}}]
        self.assertEqual([p.state for p in self.scanner.audio()],['connected','empty','unknown'])
    def test_audio_failure_keeps_unknown_record(self):
        self.write('sys/class/sound/card0/uevent','')
        def unavailable():raise FileNotFoundError('pactl')
        self.scanner.audio_runner=unavailable
        self.assertEqual(self.scanner.audio()[0].state,'unknown')
        self.assertIn('HM202',self.scanner.issues[0])
    def test_group_failure_does_not_hide_other_groups(self):
        self.write('sys/class/drm/card0-HDMI-A-1/status','connected')
        self.scanner.usb=lambda:(_ for _ in ()).throw(ValueError('test'))
        snapshot=self.scanner.scan()
        self.assertTrue(any(p.group=='display' and p.state=='connected' for p in snapshot.ports))
        self.assertTrue(any(p.state=='error' for p in snapshot.ports))
    def test_typec_partner(self):
        self.write('sys/class/typec/port0/data_role','host')
        self.assertEqual(self.scanner.typec()[0].state,'empty')
        self.write('sys/class/typec/port0-partner/uevent','')
        self.assertEqual(self.scanner.typec()[0].state,'connected')

    def test_dmi_permission_denial_is_not_retried_until_manual_refresh(self):
        from unittest.mock import patch
        path=self.scanner.sys/'class/dmi/id/product_uuid'
        with patch.object(Path,'read_text',side_effect=PermissionError(13,'Denied')) as read:
            self.scanner.read(path);self.scanner.issues=[];self.scanner.read(path)
            self.assertEqual(read.call_count,1)
            self.assertEqual(len(self.scanner.issues),1)
            self.scanner.reset_access_cache();self.scanner.read(path)
            self.assertEqual(read.call_count,2)

class AdminHelperTests(unittest.TestCase):
    def test_helper_accepts_only_read_scan_and_quit(self):
        import subprocess,sys,json
        from monitor.constants import ROOT
        result=subprocess.run([sys.executable,str(ROOT/'admin_worker.py')],input='invalid\nscan\nquit\n',
                              text=True,capture_output=True,timeout=10,check=True)
        lines=result.stdout.splitlines()
        self.assertEqual(json.loads(lines[0])['error'],'HM203')
        snapshot=json.loads(lines[1])
        self.assertIsInstance(snapshot['ports'],list)
        self.assertEqual(len(lines),2)
    def test_denied_admin_access_falls_back_without_repeated_prompts(self):
        from monitor.admin import AdminScanner
        from monitor.scanner import Snapshot
        from unittest.mock import Mock
        reader=AdminScanner();reader._connect=Mock(side_effect=FileNotFoundError('pkexec'))
        reader.normal.scan=Mock(return_value=Snapshot([],{},[],0))
        self.assertIn('HM203',reader.scan().issues)
        self.assertIn('HM203',reader.scan().issues)
        reader._connect.assert_called_once();reader.close()
