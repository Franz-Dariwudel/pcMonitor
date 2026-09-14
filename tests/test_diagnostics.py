"""Diagnose unterscheidet belegbare Ursachen und vermeidet falsche Installationshinweise."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from monitor.scanner import Scanner,Port,Snapshot
from monitor.diagnostics import Diagnostics
from monitor.config import Translator
from monitor.export import report_rows

class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.root=Path(self.temp.name)
        self.scanner=Scanner(self.root/'sys',self.root/'proc',audio_runner=lambda:[])
    def tearDown(self):self.temp.cleanup()
    def write(self,path,text):
        p=self.scanner.sys/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text);return p
    def run_diagnosis(self,ports,missing=(),admin=False,virtual=False,issues=()):
        return Diagnostics(self.scanner,lambda tool:tool not in missing,admin).annotate(ports,{'virtual':virtual},list(issues))
    def notes(self,port):return port.details.get('diagnostics',[])
    def test_missing_tool_and_permission_are_separate(self):
        p=Port('hardware:ram:modules','ram','Modules','unknown',details={'availability':'value.admin'})
        result=self.run_diagnosis([p],missing=['dmidecode'])[0]
        self.assertEqual({n['code'] for n in self.notes(result)},{'HM401','HM403'})
        self.assertEqual(self.notes(result)[0]['args']['package'],'dmidecode')
        self.assertNotIn('availability',result.details)
    def test_installed_tool_failure_never_suggests_installation(self):
        p=Port('disk:sda','storage','sda','connected',details={'smart_health':'value.unavailable','availability':'value.smart_missing'})
        result=self.run_diagnosis([p],admin=True)[0]
        self.assertEqual([n['code'] for n in self.notes(result)],['HM405'])
    def test_vm_disk_and_sensors_do_not_recommend_packages_or_admin(self):
        ports=[Port('disk:vda','storage','vda','connected',details={'smart_health':'value.unavailable','availability':'value.admin'}),
               Port('temp','temperature','Temperatures','unknown')]
        for p in self.run_diagnosis(ports,missing=['smartctl'],virtual=True):
            self.assertEqual([n['code'] for n in self.notes(p)],['HM404'])
    def test_driver_binding_accepts_builtin_driver_without_module(self):
        device=self.write('bus/pci/devices/0000:01:00.0/class','0x030000').parent
        driver=self.scanner.sys/'bus/pci/drivers/builtin';driver.mkdir(parents=True)
        (device/'driver').symlink_to(driver,target_is_directory=True)
        p=Port('pci:a','pcie','GPU','connected',details={'source':str(device)})
        self.assertFalse(self.notes(self.run_diagnosis([p])[0]))
        (device/'driver').unlink()
        self.assertEqual(self.notes(self.run_diagnosis([p])[0])[0]['code'],'HM402')
    def test_unbound_bridge_is_not_a_missing_driver_warning(self):
        device=self.write('bus/pci/devices/0000:00:00.0/class','0x060000').parent
        p=Port('pci:a','pcie','Bridge','connected',details={'source':str(device)})
        self.assertFalse(self.notes(self.run_diagnosis([p])[0]))
    def test_usb_interface_and_nvidia_are_specific(self):
        source=self.write('bus/usb/devices/1-2/product','Device').parent
        self.write('bus/usb/devices/1-2:1.0/bInterfaceClass','ff')
        usb=Port('usb:1-2','usb','USB','connected',details={'source':str(source)})
        gpu=Port('gpu:a','gpu','GPU','connected',details={'vendor_id':'0x1af4'})
        results=self.run_diagnosis([usb,gpu],missing=['nvidia-smi'])
        self.assertEqual(self.notes(results[0])[0]['code'],'HM402')
        self.assertFalse(self.notes(results[1]))
        gpu.details['vendor_id']='0x10de'
        self.assertEqual(self.notes(self.run_diagnosis([gpu],missing=['nvidia-smi'])[0])[0]['message'],'diagnosis.nvidia_tool')
    def test_dmi_denial_applies_only_to_related_category(self):
        root=self.scanner.sys/'class/dmi/id'
        ports=[Port('board','mainboard','Board','connected',details={'source':str(root)}),
               Port('id','identity','Identity','connected',details={'source':str(root)})]
        results=self.run_diagnosis(ports,issues=[f'HM201: {root}/product_uuid (PermissionError, errno=13)'])
        self.assertFalse(self.notes(results[0]));self.assertEqual(self.notes(results[1])[0]['code'],'HM403')
    def test_csv_contains_localized_diagnostics_and_update_removes_missing_tool(self):
        p=Port('cpu','cpu','CPU','connected')
        diagnosed=self.run_diagnosis([p],missing=['lscpu'])
        for lang in ('de','en'):
            rows=report_rows(Snapshot(diagnosed,{},[],0),None,Translator(lang))
            self.assertTrue(any('sudo apt install util-linux' in row[-1] for row in rows))
            self.assertFalse(any('diagnosis.' in row[-1] for row in rows))
        self.assertFalse(self.notes(self.run_diagnosis(diagnosed)[0]))
