"""Zusatzdaten: Einheiten, Mehrgeräte-Zuordnung, Nullwerte und Export."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from monitor.extended import Extended,nvidia_details,multiline_pairs
from monitor.scanner import Scanner,Port,Snapshot
from monitor.config import Translator
from monitor.export import report_rows

GPU='''Driver Version : 595.84
CUDA Version : 13.2
GPU 00000000:01:00.0
    VBIOS Version : 95.03.45
    Fan Speed : 0 %
    GPU UUID : GPU-TEST
    FB Memory Usage
        Total : 16376 MiB
        Used : 1360 MiB
        Free : 14553 MiB
    Utilization
        Gpu : 18 %
        Memory : 0 %
    GPU Power Readings
        Instantaneous Power Draw : 21.76 W
        Current Power Limit : 285.00 W
    Clocks
        Graphics : 270 MHz
        Memory : 810 MHz
    Max Clocks
        Graphics : 3120 MHz
    PCI
        GPU Link Info
            PCIe Generation
                Current : 2
                Max : 4
            Link Width
                Current : 8x
                Max : 16x
GPU 00000000:02:00.0
    Fan Speed : N/A
'''
class ExtendedTests(unittest.TestCase):
    def test_nvidia_paths_multigpu_zero(self):
        data=nvidia_details(GPU);d=data['0000:01:00.0']
        self.assertEqual(d['gpu_clock'],'270 MHz');self.assertEqual(d['memory_util'],'0 %')
        self.assertEqual(d['fan_percent'],'0 %');self.assertEqual(d['vram'],16376*1024**2)
        self.assertEqual(d['pcie_width'],'8x');self.assertEqual(d['driver_version'],'595.84')
        self.assertEqual(data['0000:02:00.0']['fan_percent'],'')
        self.assertEqual(nvidia_details('NVIDIA driver communication failed'),{})
    def test_legacy_nvidia_power(self):
        d=nvidia_details('GPU 0000:01:00.0\n    Power Readings\n        Power Draw : 0.00 W\n        Power Limit : 100 W')['0000:01:00.0']
        self.assertEqual(d['power_draw'],'0.00 W')
    def test_ethtool_continuations(self):
        d=multiline_pairs('Settings for eth0:\n\tSupported link modes: 1000baseT/Full\n\t    2500baseT/Full\n\t    10000baseT/Full\n\tSpeed: 1000Mb/s')
        self.assertIn('10000baseT/Full',d['Supported link modes']);self.assertEqual(d['Speed'],'1000Mb/s')
    def setup_scanner(self,tmp):
        scanner=Scanner(Path(tmp)/'sys',Path(tmp)/'proc',audio_runner=lambda:[])
        return scanner,Extended(scanner.hardware)
    def write(self,s,path,value):
        p=s.sys/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(value)
    def test_sensor_units_and_smt_zero(self):
        with TemporaryDirectory() as tmp:
            s,e=self.setup_scanner(tmp)
            for path,val in {'class/hwmon/hwmon0/name':'chip','class/hwmon/hwmon0/in0_input':'950','class/hwmon/hwmon0/fan1_input':'0','class/hwmon/hwmon0/power1_input':'5000','devices/system/cpu/smt/active':'0'}.items():self.write(s,path,val)
            ports=e.enrich([Port('cpu','cpu','CPU','connected')]);d=ports[0].details
            self.assertEqual(d['smt_active'],'value.disabled')
            details=[p.details for p in ports];self.assertTrue(any(d.get('fan_rpm')=='0 RPM' for d in details));self.assertTrue(any(d.get('voltage')=='0.95 V' for d in details));self.assertTrue(any(d.get('sensor_power')=='0.005 W' for d in details))
    def test_secure_boot_efi_binary_and_tpm(self):
        with TemporaryDirectory() as tmp:
            s,e=self.setup_scanner(tmp);p=s.sys/'firmware/efi/efivars/SecureBoot-test';p.parent.mkdir(parents=True);p.write_bytes(b'\x07\0\0\0\0')
            d={};e.secure_boot(d);self.assertEqual(d['secure_boot'],'value.disabled')
            self.write(s,'class/tpm/tpm0/tpm_version_major','2');self.assertEqual(e.tpm()[0].details['tpm_version'],'2')
    def test_network_multiple_addresses_and_route_interfaces(self):
        with TemporaryDirectory() as tmp:
            s,e=self.setup_scanner(tmp)
            def cmd(args,ttl=0):
                if args==['ip','-j','address','show']:return '[{"ifname":"eth0","addr_info":[{"family":"inet","local":"192.0.2.2","prefixlen":24},{"family":"inet6","local":"2001:db8::2","prefixlen":64}]}]'
                if args==['ip','-j','-4','route','show','default']:return '[{"dev":"eth0","gateway":"192.0.2.1","metric":10},{"dev":"eth1","gateway":"198.51.100.1"}]'
                return ''
            e.command=cmd;d=e.enrich([Port('net:eth0','network','eth0','connected')])[0].details
            self.assertEqual(d['ipv4'],'192.0.2.2/24');self.assertEqual(d['ipv6'],'2001:db8::2/64');self.assertNotIn('198.51',d['gateway_ipv4'])
    def test_nvme_zero_counters(self):
        with TemporaryDirectory() as tmp:
            s,e=self.setup_scanner(tmp);e.json=lambda args,ttl=0: {'mn':' Test ','nn':2} if 'id-ctrl' in args else {'media_errors':0,'power_cycles':1}
            with patch('monitor.extended.os.geteuid',return_value=0):
                d={};e.nvme(d,'nvme0n1')
            self.assertEqual(d['model'],'Test');self.assertEqual(d['nvme_media_errors'],'0')
    def test_nvidia_fields_in_report(self):
        from monitor.constants import ROOT
        d=nvidia_details(GPU)['0000:01:00.0'];snap=Snapshot([Port('g','gpu','GPU','connected',details=d)],{},[],0)
        rows=report_rows(snap,None,Translator('de'))
        self.assertTrue(any(r[-2:] == ['GPU-Lüfter (%, keine RPM)','0 %'] for r in rows))
        self.assertFalse(any(r[-2].startswith('field.') for r in rows))

    def test_bluetooth_uses_dedicated_category(self):
        with TemporaryDirectory() as tmp:
            s,e=self.setup_scanner(tmp)
            self.assertEqual(e.bluetooth()[0].group,'bluetooth')
            self.write(s,'class/bluetooth/hci0/address','00:11:22:33:44:55')
            self.assertEqual(e.bluetooth()[0].group,'bluetooth')
            self.assertEqual(e.bluetooth()[0].id,'bluetooth:hci0')
