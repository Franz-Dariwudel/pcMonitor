"""Inventar-Fixtures für fehlende Werte, Identitäten und SMART-Warnungen."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from monitor.hardware import memory_modules,edid_info,smart_info,Hardware
from monitor.scanner import Scanner

class ParserTests(unittest.TestCase):
    def test_memory_modules_skip_empty_and_preserve_units(self):
        data='''Handle 0x001, DMI type 17, 40 bytes
Memory Device
\tSize: 16 GB
\tLocator: DIMM_A1
\tManufacturer: Kingston
\tPart Number: ABC
\tSerial Number: 12345
\tSpeed: 3200 MT/s
\tConfigured Memory Speed: 2666 MT/s

Handle 0x002, DMI type 17, 40 bytes
Memory Device
\tSize: No Module Installed
\tLocator: DIMM_A2
'''
        rows=memory_modules(data)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['serial_number'],'12345')
        self.assertEqual(rows[0]['clock'],'3200 MT/s')
        self.assertEqual(rows[0]['configured_clock'],'2666 MT/s')
    def test_smart_failure_and_zero_values_are_retained(self):
        data={'smart_status':{'passed':False},'temperature':{'current':0},
              'power_on_time':{'hours':0},'serial_number':'SERIAL',
              'smartctl':{'exit_status':8},'ata_smart_attributes':{'table':[{'id':5,'name':'Reallocated','raw':{'value':4}}]}}
        result=smart_info(data)
        self.assertEqual(result['smart_health'],'value.failed')
        self.assertEqual(result['temperature'],'0 °C')
        self.assertEqual(result['power_on_hours'],'0')
        self.assertIn('4',result['smart_attributes'])
        self.assertEqual(smart_info({})['smart_health'],'value.unavailable')
    def test_edid_identity_validation(self):
        raw=bytearray(128);raw[:8]=b'\x00\xff\xff\xff\xff\xff\xff\x00'
        raw[8:10]=((4<<10)|(5<<5)|12).to_bytes(2,'big')
        raw[54:72]=b'\x00\x00\x00\xfc\x00'+b'Test display\n '
        raw[72:90]=b'\x00\x00\x00\xff\x00'+b'SN12345\n     '
        raw[127]=(-sum(raw[:127]))%256
        info=edid_info(bytes(raw))
        self.assertEqual(info['manufacturer'],'DEL')
        self.assertEqual(info['model'],'Test display')
        self.assertEqual(info['serial_number'],'SN12345')
        raw[20]+=1
        self.assertEqual(edid_info(bytes(raw))['serial_number'],'')
        self.assertEqual(edid_info(b'bad')['edid_status'],'value.invalid')

class HardwareTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.root=Path(self.temp.name)
        self.s=Scanner(self.root/'sys',self.root/'proc',audio_runner=lambda:[])
    def tearDown(self):self.temp.cleanup()
    def write(self,path,value):
        p=self.root/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(value);return p
    def test_memory_available_is_not_free(self):
        self.write('proc/meminfo','MemTotal: 1000 kB\nMemAvailable: 400 kB\nMemFree: 100 kB')
        d=self.s.hardware.ram()[0].details
        self.assertEqual(d['memory_used'],600*1024)
        self.assertEqual(d['memory_free'],100*1024)
    def test_missing_memory_is_unknown_not_zero(self):
        d=self.s.hardware.ram()[0].details
        self.assertIsNone(d['memory_total']);self.assertIsNone(d['memory_used'])
    def test_inventory_disks_pci_identity_and_no_external_commands(self):
        for k,v in {'size':'2048','device/model':'Drive','device/serial':'SN1','queue/rotational':'0'}.items():
            self.write('sys/class/block/sda/'+k,v)
        self.write('sys/class/block/sda1/partition','1')
        self.write('sys/bus/pci/devices/0000:00:01.0/class','0x030000')
        self.write('sys/class/dmi/id/product_uuid','UUID1')
        with patch('monitor.hardware.subprocess.run',side_effect=AssertionError('Host command in fixture')):
            snapshot=self.s.scan()
        self.assertFalse(any(x.startswith('HM204') for x in snapshot.issues))
        disks=[p for p in snapshot.ports if p.id.startswith('disk:')]
        self.assertEqual(len(disks),1);self.assertEqual(disks[0].details['capacity'],1048576)
        self.assertEqual(disks[0].details['serial_number'],'SN1')
        self.assertTrue(any(p.group=='gpu' for p in snapshot.ports))
        identity=next(p for p in snapshot.ports if p.group=='identity')
        self.assertEqual(identity.details['uuid'],'UUID1')
        self.assertEqual(identity.details['serials'][0]['serial_number'],'SN1')
    def test_command_cache_and_timeout(self):
        from types import SimpleNamespace
        import time
        h=Hardware(Scanner());h.deadline=time.monotonic()+6
        with patch('monitor.hardware.shutil.which',return_value='/usr/sbin/smartctl'),patch('monitor.hardware.subprocess.run',return_value=SimpleNamespace(stdout='{}')) as run:
            self.assertEqual(h.command(['smartctl','--json']), '{}')
            self.assertEqual(h.command(['smartctl','--json']), '{}')
            run.assert_called_once()
            self.assertLessEqual(run.call_args.kwargs['timeout'],2)
