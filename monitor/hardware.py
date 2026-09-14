# SPDX-License-Identifier: GPL-3.0-only
"""Hardwareinventar: ausschließlich lesende sysfs/procfs- und Werkzeugabfragen.

Externe Programme sind optional, zeitlich begrenzt und bei Testpfaden deaktiviert.
Teure Abfragen werden zwischengespeichert. Seriennummern verlassen den Rechner
nur bei einem ausdrücklich aufgerufenen JSON-Export; sie gehören nicht ins Log.
"""
from dataclasses import replace
from pathlib import Path
import json
import os
import platform
import re
import shutil
import subprocess
import time


def pairs(text):
    return {k.strip():v.strip() for line in text.splitlines() if ':' in line
            for k,v in [line.split(':',1)]}


def clean(value):
    value=str(value).strip()
    return '' if value.lower() in ('unknown','not specified','not provided','none','to be filled by o.e.m.','default string') else value


def memory_modules(text):
    """SMBIOS-Typ 17; leere Slots nicht als bestückte Module ausgeben."""
    modules=[]
    for block in re.split(r'\n\s*\n',text):
        if not re.search(r'^Memory Device\s*$',block,re.M):continue
        data=pairs(block)
        if data.get('Size','').lower() in ('no module installed','not installed','0 mb','0 gb'):continue
        modules.append({key:clean(data.get(source,'')) for key,source in {
            'slot':'Locator','bank':'Bank Locator','module_capacity':'Size',
            'manufacturer':'Manufacturer','model':'Part Number','serial_number':'Serial Number',
            'memory_type':'Type','clock':'Speed','configured_clock':'Configured Memory Speed',
            'form_factor':'Form Factor'}.items()})
    return modules


def edid_info(raw):
    """Nur validierte EDID-Basisblöcke auswerten; Rohdaten bleiben separat lesbar."""
    result={'manufacturer':'','model':'','serial_number':'','preferred_mode':'',
            'edid':raw.hex(' ') if raw else '', 'edid_status':'value.unavailable'}
    if not raw:return result
    if len(raw)<128 or raw[:8]!=b'\x00\xff\xff\xff\xff\xff\xff\x00' or sum(raw[:128])%256:
        result['edid_status']='value.invalid';return result
    result['edid_status']='value.valid'
    code=int.from_bytes(raw[8:10],'big')
    result['manufacturer']=''.join(chr(64+((code>>shift)&31)) for shift in (10,5,0))
    result['model']=f'{int.from_bytes(raw[10:12],"little"):04X}'
    serial=int.from_bytes(raw[12:16],'little')
    result['serial_number']=str(serial) if serial else ''
    for start in (54,72,90,108):
        d=raw[start:start+18]
        if d[:3]==b'\x00\x00\x00':
            text=d[5:18].decode('ascii',errors='replace').strip('\x00\n ')
            if d[3]==0xfc and text:result['model']=text
            if d[3]==0xff and text:result['serial_number']=text
        elif not result['preferred_mode'] and (d[0] or d[1]):
            w=d[2]+((d[4]&0xf0)<<4);h=d[5]+((d[7]&0xf0)<<4)
            result['preferred_mode']=f'{w} × {h}'
    return result


def smart_info(data):
    """SMART-Fehlerbits bedeuten nicht, dass die JSON-Nutzdaten unbrauchbar sind."""
    result={}
    for source,target in [('model_name','model'),('serial_number','serial_number'),('firmware_version','firmware')]:
        if data.get(source):result[target]=str(data[source])
    health=data.get('smart_status',{}).get('passed')
    result['smart_health']='value.passed' if health is True else ('value.failed' if health is False else 'value.unavailable')
    temp=data.get('temperature',{}).get('current')
    hours=data.get('power_on_time',{}).get('hours')
    nvme=data.get('nvme_smart_health_information_log',{})
    if temp is None:temp=nvme.get('temperature')
    if hours is None:hours=nvme.get('power_on_hours')
    if temp is not None:result['temperature']=f'{temp} °C'
    if hours is not None:result['power_on_hours']=str(hours)
    if 'percentage_used' in nvme:result['wear']=str(nvme['percentage_used'])+' %'
    rows=[]
    for row in data.get('ata_smart_attributes',{}).get('table',[]):
        rows.append(f"{row.get('id','')} {row.get('name','')}: {row.get('raw',{}).get('string',row.get('raw',{}).get('value',''))}")
    if rows:result['smart_attributes']='\n'.join(rows)
    result['smart_messages']='\n'.join(str(m.get('string','')) for m in data.get('smartctl',{}).get('messages',[]))
    return result


class Hardware:
    def __init__(self,scanner):
        self.s=scanner;self.cache={};self.deadline=0

    def command(self,args,ttl=60):
        """Höchstens sechs Sekunden Zusatzarbeit je Scan, nie Shell-Kommandos."""
        if self.s.sys!=Path('/sys') or self.s.proc!=Path('/proc'):return ''
        key=tuple(args);now=time.monotonic()
        if key in self.cache and now-self.cache[key][0]<ttl:return self.cache[key][1]
        remaining=self.deadline-now
        if remaining<=0:return ''
        executable=shutil.which(args[0],path='/usr/sbin:/usr/bin:/sbin:/bin')
        if not executable:return ''
        try:
            r=subprocess.run([executable,*args[1:]],capture_output=True,text=True,errors='replace',
                             timeout=min(2,remaining),env={**os.environ,'LC_ALL':'C'})
            output=r.stdout
        except (OSError,subprocess.SubprocessError):output=''
        self.cache[key]=(now,output)
        return output

    def record(self,group,details,device='',key=None,name=None,state='connected'):
        from .scanner import Port
        return Port(key or 'hardware:'+group,group,name or '@group.'+group,state,device,details)

    def pci_names(self):
        text=self.command(['lspci','-D','-vmm'])
        return {d['Slot']:d for b in text.split('\n\n') if (d:=pairs(b)).get('Slot')}

    def pci_details(self,p):
        d=self.names.get(p.name,{})
        driver=p/'driver'
        return {'manufacturer':d.get('Vendor',''),'model':d.get('Device',''),
                'vendor_id':self.s.read(p/'vendor'),'product_id':self.s.read(p/'device'),
                'pci_class':d.get('Class',self.s.read(p/'class')),
                'driver':driver.resolve().name if driver.exists() else '', 'address':p.name,
                'serial_number':self.s.read(p/'serial'),'source':str(p)}

    def cpu(self):
        text=self.s.read(self.s.proc/'cpuinfo');blocks=[pairs(b) for b in text.split('\n\n') if b.strip()]
        first=blocks[0] if blocks else {}
        data=pairs(self.command(['lscpu']))
        cores={(b.get('physical id','0'),b['core id']) for b in blocks if 'core id' in b}
        details={'manufacturer':data.get('Vendor ID',first.get('vendor_id','')),
                 'model':data.get('Model name',first.get('model name','')),
                 'cores':str(int(data['Core(s) per socket'])*int(data['Socket(s)'])) if data.get('Core(s) per socket','').isdigit() and data.get('Socket(s)','').isdigit() else (str(len(cores)) if cores else ''),
                 'threads':data.get('CPU(s)',str(len(blocks)) if blocks else ''),
                 'architecture':data.get('Architecture',platform.machine() if self.s.proc==Path('/proc') else ''),
                 'clock':first.get('cpu MHz','')+' MHz' if first.get('cpu MHz') else '',
                 'cache':'\n'.join(k+': '+v for k,v in data.items() if 'cache' in k) or first.get('cache size',''),
                 'virtualization':data.get('Virtualization','') or ' '.join(x for x in ('vmx','svm') if x in first.get('flags','').split()),
                 'serial_number':clean(first.get('Serial','')),'source':'/proc/cpuinfo · lscpu'}
        return self.record('cpu',details,details['model'])

    def ram(self):
        memory=pairs(self.s.read(self.s.proc/'meminfo'))
        def size(key):
            v=memory.get(key,'').split()
            return int(v[0])*1024 if v and v[0].isdigit() else None
        total,available,free=size('MemTotal'),size('MemAvailable'),size('MemFree')
        result=[self.record('ram',{'memory_total':total,'memory_used':total-available if total is not None and available is not None else None,
                    'memory_available':available,'memory_free':free,'source':'/proc/meminfo'})]
        text=self.command(['dmidecode','--type','17'],ttl=300) if os.geteuid()==0 else ''
        modules=memory_modules(text)
        if not modules:
            result.append(self.record('ram',{'availability':'value.admin' if os.geteuid()!=0 else 'value.dmi_missing',
                'note':'note.modules'},key='hardware:ram:modules',name='@ram.modules',state='unknown'))
        for i,d in enumerate(modules):
            d.update(source='dmidecode · SMBIOS 17',note='note.modules')
            result.append(self.record('ram',d,d['model'],key=f"hardware:ram:{d['bank']}:{d['slot']}:{i}",name=d['slot'] or f'DIMM {i+1}'))
        return result

    def dmi(self,group,fields):
        root=self.s.sys/'class/dmi/id'
        data={k:clean(self.s.read(root/v)) for k,v in fields.items()}
        data.update(source=str(root),note='note.dmi')
        if group=='bios':data['boot_mode']='UEFI' if (self.s.sys/'firmware/efi').exists() else ('Legacy' if (self.s.sys/'firmware').exists() else '')
        return self.record(group,data,data.get('model',data.get('firmware','')))

    def storage(self):
        result=[]
        for p in self.s.entries(self.s.sys/'class/block'):
            if (p/'partition').exists() or p.name.startswith(('loop','ram','dm-','zram','sr','fd')):continue
            n=self.s.read(p/'size')
            device=p/'device'
            serial=self.s.read(device/'serial') or self.s.read(p/'serial')
            info={'device_path':'/dev/'+p.name,'manufacturer':self.s.read(device/'vendor'),
                  'model':self.s.read(device/'model'),'serial_number':serial,
                  'firmware':self.s.read(device/'firmware_rev') or self.s.read(device/'rev'),
                  'capacity':int(n)*512 if n.isdigit() else None,
                  'drive_type':'NVMe' if p.name.startswith('nvme') else ({'1':'HDD','0':'SSD / Flash'}.get(self.s.read(p/'queue/rotational'),'')),
                  'smart_health':'value.unavailable','temperature':'','power_on_hours':'',
                  'source':str(p),'note':'note.disk'}
            if os.geteuid()==0:
                raw=self.command(['smartctl','--json','--all','--nocheck=standby','/dev/'+p.name])
                try:info.update(smart_info(json.loads(raw)))
                except (ValueError,TypeError,AttributeError):info['availability']='value.smart_missing'
            else:info['availability']='value.admin'
            result.append(self.record('storage',info,info['model'],key='disk:'+p.name,name=p.name))
        return result

    def collect(self,ports):
        self.deadline=time.monotonic()+6
        self.names=self.pci_names()
        additions=[self.cpu(),*self.ram(),
            self.dmi('mainboard',{'manufacturer':'board_vendor','model':'board_name','revision':'board_version','serial_number':'board_serial'}),
            self.dmi('bios',{'manufacturer':'bios_vendor','firmware':'bios_version','date':'bios_date'}),
            *self.storage()]
        for p in self.s.entries(self.s.sys/'bus/pci/devices'):
            info=self.pci_details(p)
            additions.append(self.record('pcie',info,info['model'],key='pci:'+p.name,name=p.name))
            if self.s.read(p/'class').startswith('0x03'):
                gpu=dict(info,vram=self.s.read(p/'mem_info_vram_total'),note='note.gpu')
                additions.append(self.record('gpu',gpu,info['model'],key='gpu:'+p.name,name=info['model'] or p.name))
        if not any(p.group=='gpu' for p in additions):
            additions.append(self.record('gpu',{'availability':'value.unavailable'},state='unknown'))
        sensors=self.s.system_info()['sensors']
        for i,(name,temp) in enumerate(sensors):
            additions.append(self.record('temperature',{'temperature':f'{temp:.1f} °C','source':'sysfs hwmon'},key='temperature:'+name,name=name))
        for device in list(additions):
            if device.group in ('storage','gpu') and device.details.get('temperature'):
                additions.append(self.record('temperature',{'temperature':device.details['temperature'],'source':device.details['source']},key='temperature:'+device.id,name=device.name))
        if not any(p.group=='temperature' for p in additions):additions.append(self.record('temperature',{'availability':'value.no_sensors'},state='unknown'))
        enriched=[]
        # SATA-Anschlüsse bleiben als leere Slots verfügbar; belegte Laufwerke stehen einzeln oben.
        for port in ports:
            if port.group=='storage' and port.state!='empty':continue
            details=dict(port.details)
            if port.group=='network':
                path=self.s.sys/'class/net'/port.name/'device'
                pci=self.pci_details(path.resolve())
                for k in ('manufacturer','model','driver','vendor_id','product_id'):details[k]=pci[k]
            if port.group=='display' and port.state=='connected':
                path=Path(details['source'])/'edid'
                try:raw=path.read_bytes()[:32768]
                except OSError:raw=b''
                details.update(edid_info(raw))
            enriched.append(replace(port,details=details))
        ports=enriched+additions
        identity=self.dmi('identity',{'uuid':'product_uuid','serial_number':'product_serial','chassis_serial':'chassis_serial'})
        identifiers=[]
        for port in ports:
            serial=port.details.get('serial_number')
            if serial:identifiers.append({'name':port.name,'group':port.group,'serial_number':serial})
        identity.details['serials']=identifiers
        from .extended import Extended
        return Extended(self).enrich(ports+[identity])
