# SPDX-License-Identifier: GPL-3.0-only
"""Belegbare Diagnosehinweise statt pauschaler Installationsaufforderungen.

Keine Installation und kein Laden von Kernelmodulen. Ein gebundener Treiber
ist auch ohne Eintrag in /proc/modules gültig (z.B. fest im Kernel eingebaut).
Fehlende Treiberbindung beweist weder ein fehlendes Modul noch ein Paket.
"""
from dataclasses import replace
from pathlib import Path
import os
import shutil

PACKAGES={'lscpu':'util-linux','lspci':'pciutils','dmidecode':'dmidecode',
          'smartctl':'smartmontools','pactl':'pulseaudio-utils',
          'ip':'iproute2','ethtool':'ethtool','iw':'iw','bluetoothctl':'bluez','nvme':'nvme-cli','mokutil':'mokutil'}


def diagnostic_lines(items,tr):
    return [(item['code']+' · '+tr('diagnosis.'+item['kind']),tr(item['message'],**item.get('args',{}))) for item in items]


class Diagnostics:
    def __init__(self,scanner,tool_available=None,privileged=None):
        self.s=scanner
        self.privileged=os.geteuid()==0 if privileged is None else privileged
        self.available=tool_available or (lambda tool: bool(shutil.which(tool,path='/usr/sbin:/usr/bin:/sbin:/bin')) if scanner.sys==Path('/sys') else True)

    def annotate(self,ports,system,issues):
        tools={name:self.available(name) for name in (*PACKAGES,'nvidia-smi')}
        result=[]
        for port in ports:
            data=dict(port.details);notes=[]
            def add(kind,key,**args):
                code={'tool':'HM401','driver':'HM402','access':'HM403','data':'HM404','query':'HM405'}[kind]
                item={'code':code,'kind':kind,'message':'diagnosis.'+key,'args':args}
                if item not in notes:notes.append(item)
            def require(tool):
                if not tools[tool]:
                    add('tool','missing_tool',tool=tool,package=PACKAGES[tool]);return False
                return True
            if port.state!='empty':
                if port.group=='cpu':require('lscpu')
                if port.group=='network' and not port.id.startswith('bluetooth:'):
                    require('ip')
                    if not port.id.startswith('logical:'):require('ethtool')
                    if data.get('wireless'):require('iw')
                if port.id.startswith('bluetooth:') and port.id!='bluetooth:missing':require('bluetoothctl')
                if port.group=='bios' and data.get('secure_boot')=='value.unavailable' and (self.s.sys/'firmware/efi').exists():require('mokutil')
                if port.group=='storage' and port.name.startswith('nvme'):
                    present=require('nvme')
                    if present and self.privileged and not data.get('nvme_namespaces'):add('query','extended_query',tool='nvme')
                if port.group=='gpu' and data.get('vendor_id','').lower() in ('0x10de','10de') and tools['nvidia-smi'] and not data.get('driver_version'):
                    add('query','extended_query',tool='nvidia-smi')
                if port.group in ('pcie','gpu') or (port.group=='network' and not port.id.startswith(('logical:','bluetooth:'))):require('lspci')
                if port.group=='ram' and port.id=='hardware:ram:modules':
                    present=require('dmidecode')
                    if not self.privileged:add('access','admin')
                    elif present:add('query','dmi_data')
                if port.group=='storage' and port.id.startswith('disk:'):
                    virtual_disk=port.name.startswith('vd') or '/virtio' in str((self.s.sys/'class/block'/port.name).resolve())
                    if virtual_disk and data.get('smart_health')=='value.unavailable':
                        add('data','virtual_disk')
                    else:
                        present=require('smartctl')
                        if not self.privileged:add('access','admin')
                        elif present and data.get('smart_health')=='value.unavailable':add('query','smart_query')
                if port.group=='audio':
                    present=require('pactl')
                    if present and data.get('note')=='note.audio_missing':add('query','audio_query')
                    elif present and port.state=='unknown':add('data','jack')
                if port.group=='serial' and port.state=='unknown':add('data','serial')
                if port.group=='temperature' and port.state=='unknown':
                    add('data','vm_sensors' if system.get('virtual') else 'sensors')
                if port.group=='display' and port.state=='connected' and not data.get('edid'):
                    add('data','edid')
                if port.group=='gpu' and data.get('vendor_id','').lower() in ('0x10de','10de') and not tools['nvidia-smi']:
                    add('tool','nvidia_tool')
                source=Path(data['source']) if data.get('source') else None
                if source and source.parent==self.s.sys/'bus/pci/devices':
                    cls=self.s.read(source/'class')
                    # Bridges und Hilfsfunktionen benötigen häufig keinen eigenen Treiber.
                    if cls.startswith(('0x01','0x02','0x03','0x04','0x0c03')) and not (source/'driver').exists():
                        add('driver','unbound',device=source.name)
                if port.group=='usb' and source:
                    for interface in self.s.entries(self.s.sys/'bus/usb/devices'):
                        if interface.name.startswith(source.name+':') and not (interface/'driver').exists():
                            add('driver','usb_unbound',device=interface.name)
                if source and source==self.s.sys/'class/dmi/id':
                    denied=[issue for issue in issues if 'PermissionError' in issue and str(source)+'/' in issue]
                    fields={'mainboard':('board_',),'bios':('bios_',),'identity':('product_','chassis_')}.get(port.group,())
                    if any(any('/'+prefix in issue for prefix in fields) for issue in denied):add('access','admin')
                    elif any(k in data and not data[k] for k in ('serial_number','uuid','firmware','model')):
                        add('data','firmware_data')
            # Frühere Sammelmeldungen ohne eindeutige Ursache ersetzen.
            if data.get('availability') in ('value.admin','value.dmi_missing','value.smart_missing') and notes:
                data.pop('availability',None)
            if notes:data['diagnostics']=notes
            else:data.pop('diagnostics',None)
            result.append(replace(port,details=data))
        return result
