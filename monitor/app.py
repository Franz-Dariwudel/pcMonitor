# SPDX-License-Identifier: GPL-3.0-only
"""GTK-4-Oberfläche mit getrenntem Scanner-Thread und stabiler Auswahl.

GTK wird ausschließlich im Hauptthread verwendet. Das Ausblenden unbelegter
Ports beeinflusst nur die Anzeige, niemals Erkennung oder Geräte. Neue
Sprachdateien werden in den Einstellungen erneut eingelesen.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
import logging
from pathlib import Path
import platform
import sys
import time
import gi
gi.require_version('Gtk','4.0')
gi.require_version('Gdk','4.0')
from gi.repository import Gtk, Gdk, Gio, GLib
from .constants import ROOT, VERSION, APP_ID, APP_NAME, AUTHOR, WEBSITE
from .config import Translator, load_settings, save_settings, setup_logs
from .scanner import Scanner, Snapshot

GROUPS=('cpu','ram','mainboard','bios','gpu','storage','network','usb','display','pcie','temperature','identity','audio','typec','serial')
STATES=('connected','empty','unknown','error')


def margins(widget,size):
    for side in ('top','bottom','start','end'):getattr(widget,'set_margin_'+side)(size)


def label(text,style=None):
    w=Gtk.Label(label=str(text),xalign=0,wrap=True)
    if style:w.add_css_class(style)
    return w


def clear(box):
    child=box.get_first_child()
    while child:
        following=child.get_next_sibling();box.remove(child);child=following


def bytes_text(value):
    try:number=float(value)
    except (ValueError,TypeError):return str(value)
    for unit in ('B','KiB','MiB','GiB','TiB'):
        if abs(number)<1024 or unit=='TiB':return f'{number:.1f} {unit}'
        number/=1024


def filtered_ports(ports,show_empty,query=''):
    parts=query.casefold().split()
    return [p for p in ports if (show_empty or p.state!='empty') and
            all(part in f'{p.name} {p.device} {p.group}'.casefold() for part in parts)]


class MonitorWindow(Gtk.ApplicationWindow):
    def __init__(self,application=None,scanner=None,autostart=True,config_path=None):
        super().__init__(application=application,title=APP_NAME)
        self.config_path=config_path
        self.settings,issues=load_settings(config_path)
        self.tr=Translator(self.settings['language'])
        self.settings['language']=self.tr.language
        self.scanner=scanner or Scanner()
        self.snapshot=None
        self.selected_group=None
        self._signature=None
        self._building=False
        self._busy=False
        self._closed=False
        self._last_issues=set()
        self._future=None
        self._csv_chooser=None
        self._timer=0
        self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='hardware-reader')
        self.set_default_size(1160,780)
        self.set_size_request(850,560)
        self.set_icon_name(APP_ID)
        self.connect('close-request',self._closing)
        self.build()
        if issues or self.tr.problems:
            self.status.set_text(' · '.join(issues+self.tr.problems))
        if autostart:self.start_polling()

    def build(self):
        self._building=True
        t=self.tr
        outer=Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.append(self.menu())
        self.paned=Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.paned.set_position(0)
        self.paned.set_resize_start_child(False)
        self.paned.set_shrink_start_child(False)
        self.paned.set_wide_handle(True)
        self.paned.set_vexpand(True)
        outer.append(self.paned)
        left=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
        margins(left,16)
        heading=Gtk.Box(spacing=12)
        title=label(t('ports'),'title-2');title.set_hexpand(True)
        heading.append(title)
        overview=Gtk.Button(tooltip_text=t('overview'))
        overview.set_child(self.icon('overview',28))
        overview.connect('clicked',self.show_overview)
        heading.append(overview)
        left.append(heading)
        switch_row=Gtk.Box(spacing=12)
        caption=label(t('show_occupied'));caption.set_max_width_chars(18);caption.set_hexpand(True)
        switch_row.append(caption)
        self.empty_switch=Gtk.Switch(active=self.settings['show_empty'])
        self.empty_switch.set_valign(Gtk.Align.CENTER)
        self.empty_switch.set_tooltip_text(t('show_empty_tip'))
        self.empty_switch.connect('notify::active',self._toggle_empty)
        switch_row.append(self.empty_switch)
        all_ports=label(t('show_empty'));all_ports.set_max_width_chars(14)
        switch_row.append(all_ports)
        left.append(switch_row)
        hint=label(t('unknown_hint'),'dim-label');hint.set_max_width_chars(28);left.append(hint)
        self.search=Gtk.SearchEntry(placeholder_text=t('search'))
        self.search.connect('search-changed',lambda *_:self.render(force=True))
        left.append(self.search)
        self.count=label('','dim-label');left.append(self.count)
        self.list=Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.list.add_css_class('navigation-sidebar')
        self.list.connect('row-selected',self.select_port)
        scroll=Gtk.ScrolledWindow(vexpand=True)
        scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(self.list)
        left.append(scroll)
        refresh=Gtk.Button(label=t('refresh'),halign=Gtk.Align.START)
        refresh.connect('clicked',self.request_scan)
        left.append(refresh)
        self.refresh_button=refresh
        self.paned.set_start_child(left)
        self.right=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=18)
        margins(self.right,24)
        self.right_scroll=Gtk.ScrolledWindow(vexpand=True,hexpand=True)
        self.right_scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        self.right_scroll.set_child(self.right)
        right_panel=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
        actions=Gtk.Box(spacing=8);margins(actions,12)
        self.export_scope=Gtk.ComboBoxText()
        self.export_scope.append('selected',t('export.selected'))
        self.export_scope.append('all',t('export.all'))
        self.export_scope.set_active_id('selected')
        self.export_scope.connect('changed',lambda *_:self.update_export_actions())
        actions.append(self.export_scope)
        self.print_button=Gtk.Button(label=t('export.print'));self.print_button.connect('clicked',self.export_print)
        self.csv_button=Gtk.Button(label=t('export.csv'));self.csv_button.connect('clicked',self.export_csv)
        actions.append(self.print_button);actions.append(self.csv_button)
        frame=Gtk.Frame();frame.set_child(self.right_scroll);frame.add_css_class('hardware-output')
        margins(frame,12)
        if not hasattr(self,'_frame_css'):
            self._frame_css=Gtk.CssProvider()
            self._frame_css.load_from_data(b'.hardware-output { border: 2px solid alpha(currentColor, 0.25); border-top-color: alpha(currentColor, 0.12); border-left-color: alpha(currentColor, 0.12); border-radius: 8px; box-shadow: 3px 4px 5px alpha(currentColor, 0.18), inset 1px 1px 2px alpha(currentColor, 0.06); }')
            Gtk.StyleContext.add_provider_for_display(self.get_display(),self._frame_css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.issues_box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL);margins(self.issues_box,12)
        self._issues_signature=None
        right_panel.append(actions);right_panel.append(frame);right_panel.append(self.issues_box)
        self.paned.set_end_child(right_panel)
        self.update_export_actions()
        self.status=label(t('scanning'),'dim-label');margins(self.status,9)
        outer.append(self.status)
        self.set_child(outer)
        self._building=False
        self._signature=None
        self.render(force=True)

    def menu(self):
        menu=Gio.Menu();t=self.tr
        for title,entries in (
            (t('menu.file'),[(t('menu.quit'),'quit',lambda *_:self.close())]),
            (t('menu.edit'),[(t('menu.settings'),'settings',self.show_settings)]),
            (t('menu.hardware'),[(t('overview'),'overview',self.show_overview),
                *[(t('group.'+group),'hardware-'+group,lambda *_,g=group:self.choose_group(g)) for group in GROUPS]]),
            (t('menu.help'),[(t('menu.receive'),'help',self.show_help),(t('menu.about'),'about',self.show_about),(t('menu.info'),'info',self.show_info)])):
            submenu=Gio.Menu()
            for caption,key,callback in entries:
                action=Gio.SimpleAction.new(key,None);action.connect('activate',callback)
                self.add_action(action);submenu.append(caption,'win.'+key)
            menu.append_submenu(title,submenu)
        bar=Gtk.PopoverMenuBar.new_from_model(menu)
        if not hasattr(self,'_menu_css'):
            self._menu_css=Gtk.CssProvider()
            # Auch ein unsichtbarer Scrollbalken geht in die Mindesthöhe ein.
            # Nur diese Menüs korrigieren; bei langen Menüs bleibt Scrollen aktiv.
            self._menu_css.load_from_data(b'''
                popover.hardware-menubar-menu scrollbar.vertical,
                popover.hardware-menubar-menu scrollbar.vertical range,
                popover.hardware-menubar-menu scrollbar.vertical trough,
                popover.hardware-menubar-menu scrollbar.vertical slider { min-height: 0; }
            ''')
            Gtk.StyleContext.add_provider_for_display(self.get_display(),self._menu_css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        # GTK teilt den Menü-Stack: keine Höhe des größten Untermenüs erzwingen.
        def compact(widget):
            if isinstance(widget,Gtk.PopoverMenu):widget.add_css_class('hardware-menubar-menu')
            if isinstance(widget,Gtk.Stack):widget.set_vhomogeneous(False)
            child=widget.get_first_child()
            while child:
                compact(child);child=child.get_next_sibling()
        compact(bar);bar.connect('map',lambda *_:compact(bar))
        return bar

    def choose_group(self,group):
        self.selected_group=group
        self.search.set_text('')
        self.render(force=True)
        self.right_scroll.get_vadjustment().set_value(0)

    def update_export_actions(self):
        enabled=bool(self.snapshot and (self.selected_group or self.export_scope.get_active_id()=='all'))
        self.print_button.set_sensitive(enabled);self.csv_button.set_sensitive(enabled)

    def export_content(self):
        from .export import report_rows
        group=self.selected_group if self.export_scope.get_active_id()=='selected' else None
        title=APP_NAME+' – '+(self.tr('group.'+group) if group else self.tr('export.all'))
        return report_rows(self.snapshot,group,self.tr),title,self.snapshot.timestamp

    def export_csv(self,*_):
        if self._csv_chooser is not None:
            self._csv_chooser.show();return
        from .export import csv_data
        rows,title,timestamp=self.export_content()
        content=csv_data(rows,self.tr)
        chooser=Gtk.FileChooserNative.new(self.tr('export.csv'),self,Gtk.FileChooserAction.SAVE,self.tr('save'),self.tr('cancel'))
        # NativeDialog hält sich beim Anzeigen nicht selbst am Leben.
        # Referenz bis zur Antwort behalten, sonst bricht die Ordnerabfrage ab.
        self._csv_chooser=chooser
        chooser.set_current_folder(Gio.File.new_for_path(str(ROOT)))
        chooser.set_current_name('pcMonitor-'+datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d-%H%M%S')+'.csv')
        def saved(dialog,response):
            if response==Gtk.ResponseType.ACCEPT:
                try:
                    target=dialog.get_file()
                    if target is None:raise ValueError('No destination')
                    target.replace_contents(content,None,False,Gio.FileCreateFlags.REPLACE_DESTINATION,None)
                    self.status.set_text(self.tr('export.saved'))
                except (GLib.Error,OSError,ValueError) as exc:
                    logging.getLogger('monitor').error('HM301: CSV (%s)',type(exc).__name__)
                    self.message(self.tr('export.csv'),self.tr('export.csv_error'))
            dialog.destroy()
            if self._csv_chooser is dialog:self._csv_chooser=None
        chooser.connect('response',saved);chooser.show()

    def export_print(self,*_):
        from .export import print_report
        rows,title,timestamp=self.export_content()
        try:
            result=print_report(self,rows,title,timestamp,self.tr)
            if result==Gtk.PrintOperationResult.ERROR:raise RuntimeError('GTK print error')
        except (GLib.Error,RuntimeError,ImportError) as exc:
            logging.getLogger('monitor').error('HM302: Print (%s)',type(exc).__name__)
            self.message(self.tr('export.print'),self.tr('export.print_error'))

    def start_polling(self):
        if self._timer:GLib.source_remove(self._timer)
        self._timer=0
        if self.settings['interval']:
            self._timer=GLib.timeout_add_seconds(self.settings['interval'],self.request_scan)
        if self.snapshot is None:self.request_scan()
        elif not self.settings['interval']:self.status.set_text(self.tr('settings.paused'))

    def request_scan(self,*_):
        if self._closed:return False
        if self._busy:return True
        if _ and hasattr(self.scanner,'reset_access_cache'):self.scanner.reset_access_cache()
        self._busy=True
        self.refresh_button.set_sensitive(False)
        self.status.set_text(self.tr('admin.wait') if hasattr(self.scanner,'active') and not self.scanner.active and not self.scanner.failed else self.tr('scanning'))
        self._future=self.executor.submit(self.scanner.scan)
        def finished(future):
            try:
                result=future.result()
            except Exception as exc:
                logging.getLogger('monitor').error('HM200: %s',type(exc).__name__)
                result=Snapshot([],{},['HM200'],time.time())
            GLib.idle_add(self.accept_snapshot,result)
        self._future.add_done_callback(finished)
        return True

    def accept_snapshot(self,snapshot):
        if self._closed:return False
        self._busy=False
        self.refresh_button.set_sensitive(True)
        self.snapshot=snapshot
        issues=set(snapshot.issues)
        for issue in issues-self._last_issues:logging.getLogger('monitor').warning(issue)
        self._last_issues=issues
        self.render()
        return False

    def _save(self):
        try:save_settings(self.settings,self.config_path)
        except OSError as exc:
            logging.getLogger('monitor').error('HM104: %s',type(exc).__name__)
            self.message(self.tr('menu.settings'),self.tr('settings.error'))

    def _toggle_empty(self,*_):
        if self._building:return
        self.settings['show_empty']=self.empty_switch.get_active()
        self._save();self.render(force=True)

    def render(self,force=False):
        t=self.tr
        if not self.snapshot:
            clear(self.right)
            self.right.append(label(APP_NAME,'title-1'))
            self.right.append(label(t('scanning')))
            return
        query=self.search.get_text().casefold().split()
        ports=[p for p in filtered_ports(self.snapshot.ports,self.settings['show_empty'])
               if all(q in f"{self.display_name(p.name)} {p.device} {t('group.'+p.group)} {p.group}".casefold() for q in query)]
        signature=[(p.id,p.group,p.name,p.state,p.device) for p in ports]
        if force or signature!=self._signature:
            self._building=True
            clear(self.list)
            target=None
            for group in GROUPS:
                members=[p for p in ports if p.group==group]
                if query and not members:continue
                row=Gtk.ListBoxRow();row.group_id=group
                heading=Gtk.Box(spacing=10);margins(heading,7)
                heading.append(self.icon(group,48))
                caption=label(t('group.'+group),'heading');caption.set_wrap(False);caption.set_hexpand(True)
                heading.append(caption)
                heading.append(label(str(len(members)),'dim-label'))
                row.set_child(heading);self.list.append(row)
                if group==self.selected_group:target=row
            if not ports and query:
                row=Gtk.ListBoxRow(selectable=False,activatable=False)
                b=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);margins(b,12)
                b.append(label(t('no_results'),'heading'));b.append(label(t('no_results_help')))
                row.set_child(b);self.list.append(row)
            self.list.select_row(target)
            if target is None:self.selected_group=None
            self._building=False
            self._signature=signature
        self.count.set_text(t('count',shown=len(ports),total=len(self.snapshot.ports)))
        self.status.set_text(t('updated',time=datetime.fromtimestamp(self.snapshot.timestamp).strftime('%H:%M:%S')) + (' · '+t('admin.active') if self.snapshot.system.get('admin') else ''))
        position=self.right_scroll.get_vadjustment().get_value()
        self.render_details()
        self.right_scroll.get_vadjustment().set_value(position)

    def icon(self,group,size):
        asset={'audio':'pcie','typec':'usb','serial':'network'}.get(group,group)
        path=ROOT/'resources'/f'{asset}-3d.png'
        image=Gtk.Image.new_from_file(str(path))
        image.set_pixel_size(size)
        return image

    def select_port(self,_list,row):
        if self._building:return
        self.selected_group=getattr(row,'group_id',None)
        self.render_details()
        self.right_scroll.get_vadjustment().set_value(0)

    def show_overview(self,*_):
        self.selected_group=None
        self.list.unselect_all()
        self.render_details()

    def display_name(self,name):
        return self.tr(name[1:]) if name.startswith('@') else name

    def detail_row(self,key,value):
        if value is None or value=='':value=self.tr('not_available')
        if isinstance(value,str) and value.startswith('value.'):value=self.tr(value)
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4)
        box.append(label(self.tr('field.'+key),'dim-label'))
        value_label=label(value);value_label.set_selectable(True)
        box.append(value_label)
        self.right.append(box)

    def render_details(self):
        clear(self.right)
        self.update_export_actions()
        if not self.snapshot:return
        t=self.tr
        if self.selected_group:
            group=self.selected_group
            header=Gtk.Box(spacing=16)
            header.append(self.icon(group,62))
            title=label(t('group.'+group),'title-1');title.set_hexpand(True)
            header.append(title);self.right.append(header)
            query=self.search.get_text().casefold().split()
            members=[p for p in filtered_ports(self.snapshot.ports,self.settings['show_empty'])
                     if p.group==group and all(q in f"{self.display_name(p.name)} {p.device} {t('group.'+p.group)} {p.group}".casefold() for q in query)]
            if not members:
                self.right.append(label(t('no_results'),'heading'))
                self.right.append(label(t('no_results_help'),'dim-label'))
            for port in members:
                self.right.append(Gtk.Separator())
                self.right.append(label(self.display_name(port.name),'title-2'))
                self.right.append(label(t(port.state),'dim-label'))
                if port.device:self.right.append(label(port.device,'title-3'))
                if port.details.get('note'):self.right.append(label(t(port.details['note']),'dim-label'))
                from .diagnostics import diagnostic_lines
                for heading,text in diagnostic_lines(port.details.get('diagnostics',[]),t):
                    self.right.append(label(heading,'heading'))
                    item=label(text);item.set_selectable(True);self.right.append(item)
                for key,value in port.details.items():
                    if key in ('note','diagnostics'):continue
                    if key=='serials':
                        self.right.append(label(t('field.serials'),'title-3'))
                        if not value:self.right.append(label(t('not_available')))
                        for item in value:
                            self.right.append(label(t('group.'+item['group'])+' · '+self.display_name(item['name']),'heading'))
                            serial=label(item['serial_number']);serial.set_selectable(True);self.right.append(serial)
                        continue
                    if key in ('rx_bytes','tx_bytes','capacity','vram','memory_total','memory_used','memory_available','memory_free') and value not in ('',None):value=bytes_text(value)
                    self.detail_row(key,value)
        else:
            self.right.append(label(APP_NAME,'title-1'))
            self.right.append(label(t('app.subtitle'),'title-3'))
            summary=Gtk.Box(spacing=20)
            for state in STATES:
                count=sum(p.state==state for p in self.snapshot.ports)
                tile=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4)
                tile.append(label(str(count),'title-1'));tile.append(label(t(state),'dim-label'))
                summary.append(tile)
            self.right.append(summary)
            self.right.append(label(t('no_selection')))
            affected=[p for p in self.snapshot.ports if p.details.get('diagnostics')]
            if affected:
                self.right.append(label(t('diagnosis.overview',count=len(affected)),'heading'))
                for group in GROUPS:
                    if any(p.group==group for p in affected):
                        button=Gtk.Button(label=t('group.'+group),halign=Gtk.Align.START)
                        button.connect('clicked',lambda *_ ,g=group:self.choose_group(g));self.right.append(button)
            if self.snapshot.system.get('virtual'):
                note=label(t('vm'));note.add_css_class('warning');self.right.append(note)
            self.right.append(label(t('limitation'),'dim-label'))
            self.right.append(Gtk.Separator())
            self.right.append(label(t('system'),'title-3'))
            for key in ('vendor','model','kernel','cpu'):self.detail_row(key,self.snapshot.system.get(key,''))
            total=self.snapshot.system.get('memory_total',0)
            available=self.snapshot.system.get('memory_available',0)
            self.right.append(label(t('memory'),'heading'))
            self.right.append(label(f'{bytes_text(max(0,total-available))} / {bytes_text(total)}'))
            if total:
                bar=Gtk.ProgressBar();bar.set_fraction(max(0,min(1,(total-available)/total)));self.right.append(bar)
            self.right.append(label(t('temperatures'),'heading'))
            sensors=self.snapshot.system.get('sensors',[])
            for name,value in sensors:self.right.append(label(f'{name}: {value:.1f} °C'))
            if not sensors:self.right.append(label(t('no_sensors'),'dim-label'))
        signature=(self.tr.language,tuple(self.snapshot.issues))
        if signature!=self._issues_signature:
            opened=False
            previous=self.issues_box.get_first_child()
            if isinstance(previous,Gtk.Expander):opened=previous.get_expanded()
            clear(self.issues_box)
            if self.snapshot.issues:
                expander=Gtk.Expander(label=t('issues',count=len(self.snapshot.issues)))
                descriptions=[]
                for issue in self.snapshot.issues:
                    if issue=='HM203':descriptions.append(t('admin.failed'))
                    elif issue.startswith('HM201:') and 'PermissionError' in issue:
                        path=issue.split('HM201: ',1)[1].split(' (',1)[0]
                        descriptions.append(t('issue.access',name=Path(path).name))
                    else:descriptions.append(issue)
                content=label('\n'.join(descriptions));content.set_selectable(True)
                expander.set_child(content);expander.set_expanded(opened);self.issues_box.append(expander)
            self._issues_signature=signature

    def message(self,title,text):
        dialog=Gtk.Dialog(title=title,transient_for=self,modal=True)
        dialog.add_button(self.tr('close'),Gtk.ResponseType.CLOSE)
        box=dialog.get_content_area();margins(box,20)
        content=label(text);content.set_max_width_chars(70);box.append(content)
        dialog.connect('response',lambda d,*_:d.destroy());dialog.present()

    def show_settings(self,*_):
        previous=self.tr.language
        self.tr.reload()
        if self.tr.language!=previous:
            self.settings['language']=self.tr.language;self._save();self.build()
        dialog=Gtk.Dialog(title=self.tr('menu.settings'),transient_for=self,modal=True)
        dialog.add_button(self.tr('cancel'),Gtk.ResponseType.CANCEL)
        dialog.add_button(self.tr('save'),Gtk.ResponseType.OK)
        dialog.set_default_size(580, 650)
        scroll=Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        dialog.get_content_area().append(scroll)
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12);margins(box,20)
        scroll.set_child(box)
        codes=list(self.tr.catalogs)
        language=Gtk.ComboBoxText()
        language_label=label(self.tr('settings.language'));box.append(language_label)
        box.append(language)
        single=label('');box.append(single)
        def refresh_languages():
            selected=language.get_active_id() or self.tr.language
            self.tr.reload()
            codes[:]=list(self.tr.catalogs)
            language.remove_all()
            for code in codes:language.append(code,self.tr.catalogs[code].get('language.name',code))
            language.set_active_id(selected if selected in codes else self.tr.language)
            language.set_visible(len(codes)>1);language_label.set_visible(len(codes)>1)
            single.set_visible(len(codes)==1)
            single.set_text(self.tr('settings.single',name=self.tr('language.name')))
        refresh_languages()
        box.append(label(self.tr('settings.interval')))
        interval=Gtk.ComboBoxText()
        interval.append('0',self.tr('settings.off'))
        for value in (2,3,5,10):interval.append(str(value),self.tr('settings.seconds',value=value))
        interval.set_active_id(str(self.settings['interval']));box.append(interval)
        box.append(label(self.tr('settings.reload'),'dim-label'))
        for problem in self.tr.problems:box.append(label(problem,'warning'))
        from .language_dialog import add_installer
        server=add_installer(self,dialog,box,refresh_languages)
        def done(d,response):
            if response==Gtk.ResponseType.OK:
                self.settings['language']=language.get_active_id() if len(codes)>1 else self.tr.language
                self.settings['language_server']=server.get_text().strip()
                self.settings['interval']=int(interval.get_active_id())
                self.tr.language=self.settings['language'];self._save();self.build();self.start_polling()
            d.destroy()
        dialog.connect('response',done);dialog.present()

    def show_help(self,*_):
        # Hilfe folgt ausschließlich der eingestellten Programmsprache.
        target=ROOT/'help'/f'{self.tr.language}.html'
        self._launch_help(target if target.is_file() else None)

    def _launch_help(self,path):
        try:
            if path is None:raise FileNotFoundError()
            text=path.read_text(encoding='utf-8')
            if '<html' not in text.lower():raise ValueError('HTML')
            context=self.get_display().get_app_launch_context()
            browser=Gio.AppInfo.get_default_for_uri_scheme('https') or Gio.AppInfo.get_default_for_uri_scheme('http')
            launched=browser.launch_uris([path.as_uri()],context) if browser else Gio.AppInfo.launch_default_for_uri(path.as_uri(),context)
            if not launched:raise RuntimeError('Browser')
        except Exception as exc:
            logging.getLogger('monitor').error('HM105: %s',type(exc).__name__)
            self.message(self.tr('menu.help'),self.tr('help.error'))

    def show_about(self,*_):
        dialog=Gtk.AboutDialog(title=self.tr('about.title'),transient_for=self,modal=True)
        dialog.set_program_name(self.tr('about.title'));dialog.set_version(VERSION)
        dialog.set_authors([AUTHOR]);dialog.set_comments(self.tr('about.description'))
        dialog.set_website(WEBSITE);dialog.set_website_label('dogtruck.eu')
        dialog.set_license_type(Gtk.License.GPL_3_0_ONLY)
        try:dialog.set_logo(Gdk.Texture.new_from_filename(str(ROOT/'resources/hardware-monitor.png')))
        except GLib.Error:logging.getLogger('monitor').warning('HM106: resources/hardware-monitor.png')
        dialog.present()

    def _pactl_version(self):
        import subprocess
        try:
            output=subprocess.run(['pactl','--version'],capture_output=True,text=True,timeout=2,check=True).stdout.strip()
            return output+' — PulseAudio Team'
        except (OSError,subprocess.SubprocessError):
            return 'pactl — '+self.tr('not_installed')

    def _inventory_versions(self):
        import subprocess
        import shutil
        for tool,args,team in (
                ('lscpu',['--version'],'util-linux'),('lspci',['--version'],'pciutils'),
                ('dmidecode',['--version'],'dmidecode'),('smartctl',['--version'],'smartmontools'),
                ('nvidia-smi',['--version'],'NVIDIA'),
                ('ip',['-V'],'iproute2'),('ethtool',['--version'],'ethtool'),
                ('iw',['--version'],'Linux Wireless'),('bluetoothctl',['--version'],'BlueZ'),
                ('nvme',['version'],'nvme-cli'),('mokutil',['--version'],'mokutil')):
            executable=shutil.which(tool,path='/usr/sbin:/usr/bin:/sbin:/bin')
            version=self.tr('not_installed')
            if tool=='nvidia-smi' and not executable and self.snapshot:
                vendors=[p.details.get('vendor_id','') for p in self.snapshot.ports if p.group=='gpu']
                if vendors and all(v and v.lower() not in ('0x10de','10de') for v in vendors):version=self.tr('info.nvidia_unneeded')
            if executable:
                try:
                    r=subprocess.run([executable,*args],capture_output=True,text=True,timeout=1)
                    lines=(r.stdout or r.stderr).strip().splitlines()
                    version=lines[0] if lines else self.tr('not_available')
                except (OSError,subprocess.SubprocessError):version=self.tr('not_available')
            yield f'{tool}: {version} — {team}'

    def show_info(self,*_):
        dialog=Gtk.Dialog(title=self.tr('info.title'),transient_for=self,modal=True)
        dialog.add_button(self.tr('close'),Gtk.ResponseType.CLOSE)
        body=Gtk.Box(spacing=18);margins(body,22)
        icon=Gtk.Image.new_from_file(str(ROOT/'resources/info-3d.png'));icon.set_pixel_size(52);icon.set_valign(Gtk.Align.START)
        body.append(icon)
        lines=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10)
        lines.append(label(self.tr('info.title'),'title-2'))
        for text in (f'{APP_NAME} {VERSION} — {AUTHOR}',
                     f'Python {platform.python_version()} — Python Software Foundation',
                     f'GTK {Gtk.get_major_version()}.{Gtk.get_minor_version()}.{Gtk.get_micro_version()} — GTK Team',
                     f'PyGObject {gi.__version__} — PyGObject Team',
                     f'Linux {platform.release()} — Linux kernel community',
                     'sysfs / procfs — Linux kernel',
                     self._pactl_version(), *self._inventory_versions()):
            item=label(text);item.set_selectable(True);lines.append(item)
        body.append(lines);dialog.get_content_area().append(body)
        dialog.connect('response',lambda d,*_:d.destroy());dialog.present()

    def _closing(self,*_):
        if not self._closed:
            self._closed=True
            if self._csv_chooser is not None:
                self._csv_chooser.destroy();self._csv_chooser=None
            if self._timer:GLib.source_remove(self._timer);self._timer=0
            if hasattr(self.scanner,'close'):self.scanner.close()
            self.executor.shutdown(wait=False,cancel_futures=True)
        return False


class Application(Gtk.Application):
    def __init__(self,admin=False):
        super().__init__(application_id=APP_ID,flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.admin=admin
        self.window=None
    def do_activate(self):
        if self.window is None:
            Gtk.IconTheme.get_for_display(Gdk.Display.get_default()).add_search_path(str(ROOT/'resources'))
            if self.admin:
                from .admin import AdminScanner
                self.window=MonitorWindow(self,scanner=AdminScanner())
            else:
                self.window=MonitorWindow(self)
        self.window.present()


def main(argv=None):
    parser=argparse.ArgumentParser(description='pcMonitor – Linux ports / Linux-Anschlüsse')
    parser.add_argument('--version',action='version',version=VERSION)
    parser.add_argument('--check',action='store_true',help='Ressourcen prüfen / check resources')
    parser.add_argument('--admin',action='store_true',help='Administrator-Lesehelfer starten / administrator read helper')
    parser.add_argument('--scan',action='store_true',help='Einmal lesen, JSON ausgeben / one read-only JSON scan')
    args=parser.parse_args(argv)
    logger=setup_logs()
    def unhandled(kind,value,tb):
        logger.error('HM199: %s',kind.__name__)
        sys.__excepthook__(kind,value,tb)
    sys.excepthook=unhandled
    if args.check:
        translator=Translator()
        problems=translator.problems.copy()
        assets={'audio':'pcie','typec':'usb','serial':'network'}
        for name in ('hardware-monitor.png','info-3d.png','overview-3d.png',*[assets.get(g,g)+'-3d.png' for g in GROUPS]):
            if not (ROOT/'resources'/name).is_file():problems.append('HM106: '+name)
        for code in ('de','en'):
            path=ROOT/'help'/f'{code}.html'
            try:
                if '<html' not in path.read_text(encoding='utf-8').lower():raise ValueError('HTML')
            except (OSError,ValueError,UnicodeError):problems.append('HM105: '+str(path))
        print('\n'.join(problems) if problems else f'{APP_NAME} {VERSION}: OK')
        return 1 if problems else 0
    if args.scan:
        from dataclasses import asdict
        if args.admin:
            from .admin import AdminScanner
            reader=AdminScanner()
            try:snapshot=reader.scan()
            finally:reader.close()
        else:snapshot=Scanner().scan()
        print(json.dumps(asdict(snapshot),ensure_ascii=False,indent=2))
        if 'HM203' in snapshot.issues:return 1
        return 0
    try:return Application(admin=args.admin).run([sys.argv[0]])
    except Exception as exc:
        logger.error('HM199: %s',type(exc).__name__)
        print('HM199: '+str(exc),file=sys.stderr);return 1
