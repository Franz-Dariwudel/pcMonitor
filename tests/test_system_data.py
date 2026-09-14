"""Linux-Inventur: echte Werte, fehlende Daten und korrekte Gerätezuordnung."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import unittest
from monitor.scanner import Scanner,Port,Snapshot
from monitor.system_data import SystemData,bluez_records,cpu_ticks
from monitor.hardware import memory_modules,smart_info
from monitor.export import report_rows
from monitor.config import Translator


class SystemDataTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.root=Path(self.tmp.name)
        self.s=Scanner(self.root/'sys',self.root/'proc',audio_runner=lambda:[])
        self.data=SystemData(self.s.hardware)
    def tearDown(self):self.tmp.cleanup()
    def write(self,name,value):
        p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(value);return p
    def test_system_uses_fixture_not_host_and_keeps_zero_uptime(self):
        self.write('etc/os-release','PRETTY_NAME="Linux Mint Test"\nBAD="unterminated\n')
        self.write('proc/uptime','0.00 0.00')
        self.write('proc/stat','btime 0\n')
        self.write('etc/machine-id','test-machine')
        d=self.data.linux().details
        self.assertEqual(d['distribution'],'Linux Mint Test');self.assertEqual(d['uptime_seconds'],'0.00')
        self.assertEqual(d['boot_time'],'1970-01-01T00:00:00+00:00')
        self.assertEqual(d['hostname'],'');self.assertEqual(d['architecture'],'')
    def test_cpu_requires_two_samples_and_does_not_double_count_guest(self):
        self.write('proc/stat','cpu 100 0 0 100 0 0 0 0 50 0\ncpu0 100 0 0 100 0 0 0 0 50 0')
        d={};self.data.cpu(d);self.assertEqual(d['cpu_usage'],'value.wait_sample')
        self.write('proc/stat','cpu 150 0 0 150 0 0 0 0 70 0\ncpu0 150 0 0 150 0 0 0 0 70 0')
        self.data.cpu(d);self.assertEqual(d['cpu_usage'],'cpu: 50.0 %\ncpu0: 50.0 %')
        self.write('proc/stat','cpu 1 0 0 1 0 0 0 0')
        self.data.cpu(d);self.assertEqual(d['cpu_usage'],'')
    def test_frequency_sources_are_named_and_microcode_flags_kept(self):
        self.write('sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq','2200000')
        self.write('sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_cur_freq','2000000')
        self.write('sys/devices/system/cpu/cpu0/cpufreq/scaling_governor','schedutil')
        self.write('proc/cpuinfo','processor: 0\nmicrocode: 0x123\nflags: alpha beta gamma')
        d={};self.data.cpu(d)
        self.assertIn('cpuinfo_cur_freq=2000000 kHz',d['cpu_frequencies'])
        self.assertIn('scaling_governor=schedutil',d['cpu_frequencies'])
        self.assertEqual(d['cpu_flags'],'alpha beta gamma')
    def test_partition_encryption_inherited_and_zero_space_kept(self):
        devices={'blockdevices':[{'name':'sda','path':'/dev/sda','type':'disk','children':[
            {'name':'sda1','path':'/dev/sda1','type':'part','fstype':'crypto_LUKS','children':[
                {'name':'crypt','path':'/dev/mapper/crypt','type':'crypt','children':[
                    {'name':'vg-root','path':'/dev/mapper/root','type':'lvm','fstype':'ext4','fsavail':0,'fsused':100,'mountpoints':['/a b']}]}]}]}]}
        self.data.json=lambda *a:devices
        self.write('proc/self/mountinfo','1 0 254:0 / /a\\040b rw,noatime - ext4 /dev/mapper/root rw\n')
        ports=self.data.filesystems();d=ports[-1].details
        self.assertEqual(d['encrypted'],'value.enabled');self.assertEqual(d['filesystem_free'],0)
        self.assertEqual(d['mountpoints'],'/a b');self.assertIn('noatime',d['mount_options'])
        self.assertEqual(ports[0].details['encrypted'],'value.disabled')
    def test_bad_lsblk_keeps_mounts_and_missing_is_not_disabled(self):
        self.data.json=lambda *a:[]
        self.write('proc/self/mountinfo','2 0 0:1 / /run rw - tmpfs tmpfs rw\n')
        p=self.data.filesystems()[0]
        self.assertEqual(p.details['filesystem_type'],'tmpfs');self.assertNotIn('encrypted',p.details)
        self.assertEqual(self.data.kernel().details['iommu_status'],'value.unavailable')
    def test_network_is_scoped_and_does_not_request_secrets_or_rescan(self):
        calls=[]
        self.write('sys/class/net/wlan0/wireless/present','1')
        self.write('sys/class/net/wlan0/mtu','1500');self.write('sys/class/net/wlan0/statistics/rx_errors','0')
        def command(args,ttl=0):
            calls.append(args)
            if 'show' in args and args[-1]=='wlan0' and args[0]=='nmcli':
                return 'IP4.DNS[1]: 192.0.2.53\nIP4.DOMAIN[1]: example.test\nDHCP4.OPTION[1]: dhcp_lease_time = 3600'
            if args[0]=='iw':return 'Connected to aa:bb:cc:dd:ee:ff (on wlan0)\nSSID: Test'
            if 'wifi' in args:return 'IN-USE: *\nSSID: Test\nSECURITY: WPA3\n'
            return ''
        self.data.command=command;d={};self.data.network(d,'wlan0')
        self.assertEqual(d['dns'],'192.0.2.53');self.assertEqual(d['dhcp_status'],'value.enabled')
        self.assertEqual(d['bssid'],'aa:bb:cc:dd:ee:ff');self.assertIn('rx_errors: 0',d['network_statistics'])
        self.assertTrue(any('table' in c and c[-2:]==['dev','wlan0'] for c in calls))
        self.assertTrue(any(c[-2:]==['--rescan','no'] for c in calls));self.assertFalse(any('--show-secrets' in c for c in calls))
    def test_services_ipv6_and_absent_pid(self):
        self.data.command=lambda *a:'tcp LISTEN 0 128 [::1]:1234 [::]:* users:(("worker",pid=42,fd=3))\nudp UNCONN 0 0 0.0.0.0:53 0.0.0.0:*\n'
        a,b=self.data.services()
        self.assertEqual(a.details['local_address'],'[::1]:1234');self.assertEqual(a.details['process_id'],'42')
        self.assertEqual(b.details['process_id'],'')
    def test_empty_successful_services_are_not_query_failure(self):
        self.data.command=lambda *a:''
        self.s.hardware.command_results[('ss','-H','-lntup')]=True
        self.assertEqual(self.data.services()[0].details['availability'],'value.none')
        self.s.hardware.command_results[('ss','-H','-lntup')]=False
        self.assertEqual(self.data.services()[0].details['availability'],'value.unavailable')
    def test_bluetooth_devices_never_cross_adapters(self):
        objects={'/a/hci0':{'org.bluez.Adapter1':{'Address':'AA','Powered':False}},
                 '/a/hci1':{'org.bluez.Adapter1':{'Address':'BB','Powered':True}},
                 '/a/hci0/dev1':{'org.bluez.Device1':{'Adapter':'/a/hci0','Address':'11','Name':'Device A','Paired':True}},
                 '/a/hci1/dev2':{'org.bluez.Device1':{'Adapter':'/a/hci1','Address':'22','Name':'Device B','Connected':True}}}
        data=bluez_records(objects)
        self.assertEqual(data['hci0']['bluetooth_powered'],'value.disabled')
        self.assertIn('Device A',data['hci0']['bluetooth_devices']);self.assertNotIn('Device B',data['hci0']['bluetooth_devices'])
        self.assertEqual(data['hci0']['bluetooth_connected'],'value.none')
    def test_smartctl_nvme_fallback_and_zero_counters(self):
        d=smart_info({'nvme_smart_health_information_log':{'media_errors':0,'available_spare_threshold':10,'data_units_read':100},'power_cycle_count':0})
        self.assertEqual(d['nvme_media_errors'],'0');self.assertEqual(d['power_cycles'],'0')
        from monitor.extended import Extended
        e=Extended(self.s.hardware);e.json=lambda *a,**k:None
        with patch('monitor.extended.os.geteuid',return_value=0):e.nvme(d,'nvme0n1')
        self.assertEqual(d['nvme_data_units_read'],'100')
    def test_memory_voltage_and_reported_ecc_not_inferred(self):
        data='''Handle 0x0010, DMI type 16
Physical Memory Array
 Error Correction Type: Multi-bit ECC

Memory Device
 Size: 32 GB
 Array Handle: 0x0010
 Configured Voltage: 1.1 V
 Total Width: 72 bits
 Data Width: 64 bits
'''
        d=memory_modules(data)[0]
        self.assertEqual(d['ecc_type'],'Multi-bit ECC');self.assertEqual(d['configured_voltage'],'1.1 V')
        self.assertNotIn('ecc_active',d)
    def test_new_data_have_translated_export_labels(self):
        with patch('monitor.hardware.subprocess.run',side_effect=AssertionError('Host command')):
            ports=self.data.enrich([Port('cpu','cpu','CPU','connected')])
        for lang in ('de','en'):
            report=report_rows(Snapshot(ports,{},[],0),None,Translator(lang))
            self.assertFalse(any(r[0].startswith('group.') or r[-2].startswith('field.') for r in report))

    def test_local_mount_space_includes_zero_and_paths_with_spaces(self):
        self.data.json=lambda *a:None
        self.data.command=lambda *a:'Mounted on 1B-blocks Used Avail\n/a b 100 100 0\n'
        self.write('proc/self/mountinfo','2 0 0:1 / /a\\040b rw - tmpfs tmpfs rw\n')
        d=self.data.filesystems()[0].details
        self.assertEqual(d['filesystem_free'],0)
        self.assertEqual(d['filesystem_size'],100)

    def test_amd_vram_units_zero_and_labeled_sensors(self):
        for name,value in {'gpu_busy_percent':'0','mem_busy_percent':'12',
                           'mem_info_vram_total':'1024','mem_info_vram_used':'0',
                           'hwmon/hwmon0/temp1_input':'42500','hwmon/hwmon0/temp1_label':'junction',
                           'hwmon/hwmon0/fan1_input':'0'}.items():
            self.write('sys/bus/pci/devices/0000:01:00.0/'+name,value)
        d={'address':'0000:01:00.0'};self.data.amd(d)
        self.assertEqual(d['vram'],1024);self.assertEqual(d['vram_free'],'1024 B')
        self.assertEqual(d['gpu_util'],'0 %');self.assertEqual(d['fan_rpm'],'0 RPM')
        self.assertIn('junction: 42.5 °C',d['gpu_sensors'])

    def test_tpm_capability_queries_are_only_reads_and_version_scoped(self):
        self.write('sys/class/tpm/tpm0/tpm_version_major','2')
        self.write('dev/tpmrm0','')
        calls=[]
        def command(args,ttl=0):
            calls.append(args);return 'TPM data'
        self.data.command=command
        self.data.security([])
        self.assertEqual([c[-1] for c in calls if c[0]=='tpm2_getcap'],['properties-fixed','pcrs','algorithms'])
        self.assertTrue(all('device:/dev/tpmrm0' in c for c in calls if c[0]=='tpm2_getcap'))
        calls.clear();self.write('sys/class/tpm/tpm0/tpm_version_major','1')
        self.data.security([])
        self.assertFalse(any(c[0]=='tpm2_getcap' for c in calls))
