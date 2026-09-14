# SPDX-License-Identifier: GPL-3.0-only
"""Vollständige Bereichsberichte, CSV und paginierter GTK-Druck.

Ein Bericht friert den aktuellen Scan ein. CSV ist UTF-8 mit BOM und Semikolon;
mehrzeilige Werte werden korrekt zitiert und Formeleingaben neutralisiert.
"""
import csv
import io
from datetime import datetime


def report_rows(snapshot,group,tr):
    rows=[]
    for port in snapshot.ports:
        if group is not None and port.group!=group:continue
        name=tr(port.name[1:]) if port.name.startswith('@') else port.name
        base=[tr('group.'+port.group),name,tr(port.state)]
        if port.device:rows.append(base+[tr('field.product'),port.device])
        for key,value in port.details.items():
            if key=='diagnostics':
                from .diagnostics import diagnostic_lines
                for title,text in diagnostic_lines(value,tr):rows.append(base+[title,text])
                continue
            if key=='serials':
                for item in value:
                    title=tr(item['name'][1:]) if item['name'].startswith('@') else item['name']
                    rows.append(base+[tr('field.serial_number')+' · '+title,item['serial_number']])
                continue
            if key=='note':value=tr(value)
            if value is None or value=='':value=tr('not_available')
            elif isinstance(value,str) and value.startswith('value.'):value=tr(value)
            if key in ('rx_bytes','tx_bytes','capacity','vram','memory_total','memory_used','memory_available','memory_free') and (isinstance(value,(int,float)) or str(value).isdigit()):
                value=str(value)+' B'
            rows.append(base+[tr('field.'+key),str(value)])
        if not port.details and not port.device:rows.append(base+[tr('details'),tr('not_available')])
    for issue in snapshot.issues:
        rows.append([tr('export.notice'),'','',tr('export.notice'),tr('admin.failed') if issue=='HM203' else issue])
    return rows


def csv_data(rows,tr):
    stream=io.StringIO(newline='');writer=csv.writer(stream,delimiter=';')
    writer.writerow([tr('export.category'),tr('export.device'),tr('export.state'),tr('export.field'),tr('export.value')])
    for row in rows:
        writer.writerow(["'"+v if v.lstrip().startswith(('=','+','-','@')) else v for item in row for v in [str(item)]])
    return stream.getvalue().encode('utf-8-sig')


def print_report(parent,rows,title,timestamp,tr,export_filename=None):
    """GTK-Druckdialog; Tests können dieselbe Seitenerzeugung als PDF ausgeben."""
    import gi
    gi.require_version('Gtk','4.0')
    from gi.repository import Gtk,Pango,PangoCairo
    operation=Gtk.PrintOperation();operation.set_job_name(title)
    operation.set_unit(Gtk.Unit.POINTS)
    operation.set_use_full_page(False)
    blocks=[title,datetime.fromtimestamp(timestamp).strftime('%d.%m.%Y %H:%M:%S'),'']
    previous=None
    for category,device,state,field,value in rows:
        identity=(category,device,state)
        if identity!=previous:
            blocks.extend(['',f'{category} · {device} · {state}']);previous=identity
        blocks.append(f'{field}: {value}')
    pages=[]
    def begin(op,context):
        layout=context.create_pango_layout();layout.set_font_description(Pango.FontDescription('Sans 10'))
        layout.set_width(int(context.get_width()*Pango.SCALE));layout.set_wrap(Pango.WrapMode.WORD_CHAR)
        page=[];height=0;limit=context.get_height()-24
        for block in blocks:
            layout.set_text(block,-1)
            # Jede umbrochene Zeile ist ein eigener Seitenbaustein; auch EDID passt.
            encoded=block.encode('utf-8')
            for line in layout.get_lines_readonly():
                text=encoded[line.start_index:line.start_index+line.length].decode('utf-8')
                lineheight=max(14,line.get_extents()[1].height/Pango.SCALE+2)
                if page and height+lineheight>limit:pages.append(page);page=[];height=0
                page.append((text,height));height+=lineheight
        pages.append(page);op.set_n_pages(len(pages))
    def draw(op,context,number):
        cr=context.get_cairo_context();layout=context.create_pango_layout()
        layout.set_font_description(Pango.FontDescription('Sans 10'))
        for text,y in pages[number]:
            layout.set_text(text,-1);cr.move_to(0,y);PangoCairo.show_layout(cr,layout)
        layout.set_text(f'{number+1} / {len(pages)}',-1)
        cr.move_to(0,context.get_height()-16);PangoCairo.show_layout(cr,layout)
    operation.connect('begin-print',begin);operation.connect('draw-page',draw)
    if export_filename:
        operation.set_export_filename(str(export_filename));action=Gtk.PrintOperationAction.EXPORT
    else:action=Gtk.PrintOperationAction.PRINT_DIALOG
    return operation.run(action,parent)
