from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from monitor.app import Gtk,MonitorWindow,filtered_ports,bytes_text
from monitor.scanner import Port,Snapshot

PORTS=[Port('usb:1','usb','USB 1','connected','Keyboard'),Port('usb:2','usb','USB 2','empty'),
       Port('audio:1','audio','Audio','unknown'),Port('error','network','Ethernet','error')]
class FilterTests(unittest.TestCase):
    def test_hide_only_empty_ports(self):
        self.assertEqual([p.id for p in filtered_ports(PORTS,False)],['usb:1','audio:1','error'])
        self.assertEqual(len(filtered_ports(PORTS,True)),4)
    def test_search_and_zero_values(self):
        self.assertEqual([p.id for p in filtered_ports(PORTS,True,'keyboard')],['usb:1'])
        self.assertEqual(bytes_text('0'),'0.0 B')

class UiTests(unittest.TestCase):
    def setUp(self):
        if not Gtk.init_check():raise unittest.SkipTest('No display')
        self.temp=TemporaryDirectory()
        self.path=Path(self.temp.name)/'settings.json'
        self.window=MonitorWindow(autostart=False,config_path=self.path)
        self.window.accept_snapshot(Snapshot(PORTS,{},[],0))
    def tearDown(self):
        self.window._closing();self.window.destroy();self.temp.cleanup()
    def test_toggle_is_persistent_and_does_not_change_scanned_ports(self):
        self.window.empty_switch.set_active(True)
        self.assertTrue(self.path.exists())
        self.assertEqual(len(self.window._signature),4)
        self.window.empty_switch.set_active(False)
        self.assertEqual(len(self.window._signature),3)
        self.assertEqual(len(self.window.snapshot.ports),4)
    def test_selection_survives_refresh_and_disconnection(self):
        self.window.selected_group='usb';self.window.render(force=True)
        self.window.accept_snapshot(Snapshot(PORTS,{},[],1))
        self.assertEqual(self.window.selected_group,'usb')
        disconnected=[Port('usb:1','usb','USB 1','empty'),*PORTS[1:]]
        self.window.accept_snapshot(Snapshot(disconnected,{},[],2))
        self.assertEqual(self.window.selected_group,'usb')
    def test_english_rebuild_and_details(self):
        self.window.tr.language='en';self.window.build()
        self.assertEqual(self.window.count.get_text(),'3 of 4 entries')
        self.window.selected_group='audio';self.window.render_details()
        self.assertIsNotNone(self.window.right.get_first_child())

    def test_one_row_per_group_and_all_matching_devices_on_right(self):
        self.window.empty_switch.set_active(True)
        rows=[];row=self.window.list.get_first_child()
        while row:
            if getattr(row,'group_id',None)=='usb':rows.append(row)
            row=row.get_next_sibling()
        self.assertEqual(len(rows),1)
        self.window.list.select_row(rows[0])
        def texts(widget):
            result=[widget.get_text()] if isinstance(widget,Gtk.Label) else []
            child=widget.get_first_child()
            while child:
                result.extend(texts(child));child=child.get_next_sibling()
            return result
        self.assertIn('USB 1',texts(self.window.right))
        self.assertIn('USB 2',texts(self.window.right))
        self.window.empty_switch.set_active(False)
        self.assertIn('USB 1',texts(self.window.right))
        self.assertNotIn('USB 2',texts(self.window.right))

    def test_hardware_menu_selects_category(self):
        self.window.search.set_text('nothing')
        self.window.lookup_action('hardware-ram').activate(None)
        self.assertEqual(self.window.selected_group,'ram')
        self.assertEqual(self.window.search.get_text(),'')

    def test_disabled_polling_keeps_snapshot_without_new_scan(self):
        from unittest.mock import Mock
        self.window.request_scan=Mock()
        self.window.settings['interval']=3;self.window.start_polling()
        self.assertNotEqual(self.window._timer,0)
        self.window.settings['interval']=0;self.window.start_polling()
        self.assertEqual(self.window._timer,0)
        self.window.request_scan.assert_not_called()

    def test_unchanged_issue_widget_survives_refresh(self):
        issue='HM201: /sys/class/dmi/id/product_uuid (PermissionError, errno=13)'
        self.window.accept_snapshot(Snapshot(PORTS,{},[issue],1))
        expander=self.window.issues_box.get_first_child();expander.set_expanded(True)
        self.window.accept_snapshot(Snapshot(PORTS,{},[issue],2))
        self.assertEqual(self.window.issues_box.get_first_child(),expander)
        self.assertTrue(expander.get_expanded())

    def test_single_item_native_menus_have_no_empty_scrollbar_space(self):
        from gi.repository import GLib
        def descendants(widget):
            yield widget
            child=widget.get_first_child()
            while child:
                yield from descendants(child);child=child.get_next_sibling()
        bar=self.window.get_child().get_first_child()
        self.assertIsInstance(bar,Gtk.PopoverMenuBar)
        menus=[x for x in descendants(bar) if isinstance(x,Gtk.PopoverMenu)]
        self.window.present()
        for menu in menus[:2]:
            menu.popup()
            loop=GLib.MainLoop()
            GLib.timeout_add(120,lambda:(loop.quit(),False)[1]);loop.run()
            scroll=next(x for x in descendants(menu) if isinstance(x,Gtk.ScrolledWindow))
            needed=scroll.get_child().measure(Gtk.Orientation.VERTICAL,-1)[1]
            self.assertLessEqual(scroll.get_height(),needed+2)
            menu.popdown()

    def test_help_uses_app_language_without_picker_or_english_fallback(self):
        from unittest.mock import Mock
        from monitor.constants import ROOT
        self.window._launch_help=Mock()
        for code in ('de','en'):
            self.window.tr.language=code;self.window.show_help()
            self.window._launch_help.assert_called_with(ROOT/'help'/f'{code}.html')
        self.window.tr.language='missing-language';self.window.show_help()
        self.window._launch_help.assert_called_with(None)

    def test_native_csv_dialog_survives_gc_and_cancel(self):
        import gc,weakref
        self.window.selected_group='usb'
        self.window.export_csv()
        reference=weakref.ref(self.window._csv_chooser)
        gc.collect()
        self.assertIsNotNone(reference())
        self.window.export_csv()
        self.assertIs(self.window._csv_chooser,reference())
        reference().emit('response',Gtk.ResponseType.CANCEL)
        self.assertIsNone(self.window._csv_chooser)

    def test_csv_save_writes_frozen_snapshot_and_releases_dialog(self):
        from unittest.mock import Mock,patch
        from gi.repository import Gio
        import csv,io
        self.window.selected_group='usb'
        target=Path(self.temp.name)/'hardware.csv'
        dialog=Mock();dialog.get_file.return_value=Gio.File.new_for_path(str(target))
        with patch.object(Gtk.FileChooserNative,'new',return_value=dialog):
            self.window.export_csv()
            callback=dialog.connect.call_args.args[1]
            self.window.snapshot=Snapshot([],{},[],1)
            callback(dialog,Gtk.ResponseType.ACCEPT)
        rows=list(csv.reader(io.StringIO(target.read_text(encoding='utf-8-sig')),delimiter=';'))
        self.assertTrue(any('Keyboard' in row for row in rows))
        self.assertEqual(self.window.status.get_text(),self.window.tr('export.saved'))
        self.assertIsNone(self.window._csv_chooser)
        dialog.destroy.assert_called_once()

    def test_csv_write_failure_is_reported_without_success(self):
        from unittest.mock import Mock,patch
        from gi.repository import GLib
        self.window.selected_group='usb'
        dialog=Mock();dialog.get_file.return_value.replace_contents.side_effect=GLib.Error('write denied')
        self.window.message=Mock()
        before=self.window.status.get_text()
        with patch.object(Gtk.FileChooserNative,'new',return_value=dialog):
            self.window.export_csv()
            dialog.connect.call_args.args[1](dialog,Gtk.ResponseType.ACCEPT)
        self.window.message.assert_called_once()
        self.assertEqual(self.window.status.get_text(),before)
        self.assertIsNone(self.window._csv_chooser)

    def test_window_close_releases_active_csv_dialog(self):
        from unittest.mock import Mock
        dialog=Mock();self.window._csv_chooser=dialog
        self.window._closing()
        dialog.destroy.assert_called_once()
        self.assertIsNone(self.window._csv_chooser)
