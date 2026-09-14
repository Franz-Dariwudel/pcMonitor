from pathlib import Path
from tempfile import TemporaryDirectory
import csv,io,unittest
from monitor.scanner import Port,Snapshot
from monitor.config import Translator
from monitor.export import report_rows,csv_data,print_report
from monitor.app import Gtk

class ExportTests(unittest.TestCase):
    def setUp(self):
        self.tr=Translator('de')
        self.snapshot=Snapshot([Port('a','cpu','CPU','connected',details={'model':'=1+1','serial_number':'AB;CD\n123'}),
                                Port('b','usb','USB 1','empty',details={'speed':0})],{},[],0)
    def test_scope_and_csv_roundtrip(self):
        selected=report_rows(self.snapshot,'cpu',self.tr)
        self.assertTrue(all(row[0]=='CPU' for row in selected))
        allrows=report_rows(self.snapshot,None,self.tr)
        self.assertTrue(any(row[1]=='USB 1' for row in allrows))
        rows=list(csv.reader(io.StringIO(csv_data(allrows,self.tr).decode('utf-8-sig')),delimiter=';'))
        self.assertTrue(any(row[-1]=='AB;CD\n123' for row in rows))
        self.assertTrue(any(row[-1]=="'=1+1" for row in rows))
        self.assertTrue(any(row[-1]=='0' for row in rows))
    def test_paginated_print_to_pdf(self):
        if not Gtk.init_check():self.skipTest('No display')
        with TemporaryDirectory() as folder:
            path=Path(folder)/'report.pdf'
            rows=[['CPU','CPU','Erkannt','Angabe',('ÄÖÜ lange Daten '+str(i)+' ')*15] for i in range(150)]
            result=print_report(None,rows,'Testbericht',0,self.tr,path)
            self.assertEqual(result,Gtk.PrintOperationResult.APPLY)
            self.assertTrue(path.read_bytes().startswith(b'%PDF'))
            self.assertGreater(path.stat().st_size,2000)
