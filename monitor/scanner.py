# SPDX-License-Identifier: GPL-3.0-only
"""Lesende Linux-Hardwareerkennung ohne Administratorrechte.

USB zählt die vom Kernel gemeldeten logischen Hub-Anschlüsse. USB-2/USB-3-
Begleiter können dieselbe physische Buchse repräsentieren. Interne Anschlüsse
sind enthalten; aus fehlenden Daten wird kein freier physischer Port erfunden.
Alle Pfade sind für Tests injizierbar. pactl ist eine optionale Audioquelle.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
import json
import os
import platform
import re
import shutil
import subprocess
import time


@dataclass(frozen=True)
class Port:
    id: str
    group: str
    name: str
    state: str  # connected / empty / unknown / error
    device: str = ''
    details: dict = field(default_factory=dict)


@dataclass
class Snapshot:
    ports: list[Port]
    system: dict
    issues: list[str]
    timestamp: float


def natural_key(value):
    return [int(x) if x.isdigit() else x.casefold() for x in re.split(r'(\d+)', str(value))]


class Scanner:
    def __init__(self, sysroot=Path('/sys'), procroot=Path('/proc'), audio_runner=None):
        self.sys = Path(sysroot)
        self.proc = Path(procroot)
        self.audio_runner = audio_runner or self._audio_command
        self.issues = []
        self._denied_dmi = {}
        from .hardware import Hardware
        self.hardware = Hardware(self)

    def read(self, path, default=''):
        key=str(path)
        if key in self._denied_dmi:
            if self._denied_dmi[key] not in self.issues:self.issues.append(self._denied_dmi[key])
            return default
        try:
            return Path(path).read_text(encoding='utf-8', errors='replace')[:1048576].strip()
        except FileNotFoundError:
            return default
        except OSError as exc:
            issue = f'HM201: {path} ({type(exc).__name__}, errno={exc.errno})'
            if isinstance(exc,PermissionError) and Path(path).parent==self.sys/'class/dmi/id':self._denied_dmi[key]=issue
            if issue not in self.issues:self.issues.append(issue)
            return default

    def reset_access_cache(self):
        self._denied_dmi.clear()

    def entries(self, path):
        try:return sorted(Path(path).iterdir(), key=lambda p:natural_key(p.name))
        except FileNotFoundError:return []
        except OSError as exc:
            self.issues.append(f'HM201: {path} ({type(exc).__name__})')
            return []

    def scan(self):
        self.issues = []
        ports = []
        for group, method in (('usb',self.usb),('display',self.displays),('network',self.network),
                              ('audio',self.audio),('storage',self.storage),('pcie',self.pcie),
                              ('typec',self.typec),('serial',self.serial)):
            try:ports.extend(method())
            except Exception as exc:
                self.issues.append(f'HM200: {group} ({type(exc).__name__})')
                ports.append(Port(group+':error',group,group,'error',details={'source':str(self.sys)}))
        try:ports = self.hardware.collect(ports)
        except Exception as exc:self.issues.append(f'HM204: Hardware ({type(exc).__name__})')
        system = self.system_info()
        system['admin'] = os.geteuid() == 0
        from .diagnostics import Diagnostics
        ports = Diagnostics(self).annotate(ports,system,self.issues)
        return Snapshot(ports, system, self.issues.copy(), time.time())

    def usb(self):
        root = self.sys/'bus/usb/devices'
        devices = self.entries(root)
        byname = {p.name:p for p in devices}
        ports = []
        for hub in devices:
            if ':' in hub.name:continue  # Interfaces sind keine separaten Buchsen.
            maximum = self.read(hub/'maxchild')
            if not maximum.isdigit() or int(maximum)==0:continue
            bus = self.read(hub/'busnum',hub.name.removeprefix('usb'))
            version = self.read(hub/'version')
            prefix = bus+'-' if hub.name.startswith('usb') else hub.name+'.'
            for number in range(1,min(int(maximum),255)+1):
                key = prefix+str(number)
                child = byname.get(key)
                state = 'connected' if child else 'empty'
                info = {'port':key, 'hub':hub.name, 'version':version,
                        'source':str(hub), 'note':'note.usb'}
                device = ''
                if child:
                    device = self.read(child/'product') or self.read(child/'manufacturer')
                    info.update({'manufacturer':self.read(child/'manufacturer'),
                        'product':self.read(child/'product'), 'serial_number':self.read(child/'serial'),
                        'vendor_id':self.read(child/'idVendor'), 'product_id':self.read(child/'idProduct'),
                        'speed':self.read(child/'speed'), 'power':self.read(child/'bMaxPower'),
                        'device_class':self.read(child/'bDeviceClass'),
                        'authorized':self.read(child/'authorized'), 'source':str(child)})
                    if not device:device='USB '+info['vendor_id']+':'+info['product_id']
                ports.append(Port('usb:'+key,'usb','USB '+key,state,device,info))
        return ports

    def displays(self):
        result=[]
        for p in self.entries(self.sys/'class/drm'):
            if not re.match(r'card\d+-.+',p.name):continue
            status=self.read(p/'status','unknown')
            state={'connected':'connected','disconnected':'empty'}.get(status,'unknown')
            modes=self.read(p/'modes').splitlines()
            name=re.sub(r'^card\d+-','',p.name)
            result.append(Port('display:'+p.name,'display',name,state,
                modes[0] if state=='connected' and modes else '',
                {'connector':name,'kernel_status':status,'modes':'\n'.join(modes),
                 'enabled':self.read(p/'enabled'),'source':str(p),'note':'note.display'}))
        return result

    def network(self):
        result=[]
        for p in self.entries(self.sys/'class/net'):
            if p.name=='lo':continue
            # Bridges/Tunnels gehören nicht zu den physischen Anschlüssen.
            if not (p/'device').exists():continue
            carrier=self.read(p/'carrier')
            operating=self.read(p/'operstate','unknown')
            state='connected' if carrier=='1' else ('empty' if carrier=='0' else 'unknown')
            if operating=='down' and carrier!='1':state='unknown'
            wireless=(p/'wireless').exists()
            result.append(Port('network:'+p.name,'network',p.name,state,
                'Wi-Fi' if wireless else 'Ethernet',
                {'interface':p.name,'address':self.read(p/'address'),
                 'kernel_status':operating,'speed':self.read(p/'speed') if carrier=='1' else '',
                 'duplex':self.read(p/'duplex') if carrier=='1' else '', 'rx_bytes':self.read(p/'statistics/rx_bytes'),
                 'tx_bytes':self.read(p/'statistics/tx_bytes'),'source':str(p),'note':'note.network'}))
        return result

    @staticmethod
    def _audio_command():
        if not shutil.which('pactl'):raise FileNotFoundError('pactl')
        result=subprocess.run(['pactl','--format=json','list','cards'],capture_output=True,
                              text=True,timeout=2,check=True)
        return json.loads(result.stdout)

    def audio(self):
        try:cards=self.audio_runner()
        except (OSError,subprocess.SubprocessError,ValueError) as exc:
            cards=[]
            if self.entries(self.sys/'class/sound'):
                self.issues.append(f'HM202: Audio ({type(exc).__name__})')
                return [Port('audio:unavailable','audio','Audio','unknown',details={'note':'note.audio_missing'})]
        result=[]
        for card in cards:
            key=card.get('name',str(card.get('index','audio')))
            properties=card.get('properties',{})
            card_name=properties.get('device.description',key)
            card_ports=card.get('ports',{})
            if isinstance(card_ports,list):card_ports={p.get('name',str(i)):p for i,p in enumerate(card_ports)}
            for name,port in card_ports.items():
                available=str(port.get('availability','unknown')).lower()
                state='connected' if available in ('yes','available','available: yes') else (
                    'empty' if available in ('no','not available','available: no') else 'unknown')
                result.append(Port('audio:'+key+':'+name,'audio',port.get('description',name),state,
                    card_name,{'connector':port.get('type',name),'card':card_name,
                               'kernel_status':available,'source':'pactl','note':'note.audio'}))
        return result

    def storage(self):
        result=[]
        blocks=[p for p in self.entries(self.sys/'class/block')
                if not (p/'partition').exists() and not p.name.startswith(('loop','ram','dm-','zram'))]
        assigned=set()
        for p in self.entries(self.sys/'class/ata_port'):
            # ataX/ata_port/ataX -> ataX; darunter liegen zugehörige SCSI-Geräte.
            physical=p.resolve().parent.parent
            children=[b for b in blocks if b.resolve().is_relative_to(physical)]
            info={'port':p.name,'source':str(p),'note':'note.storage'}
            if children:
                devices=[]
                for b in children:
                    assigned.add(b.name)
                    devices.append(self.read(b/'device/model',b.name))
                info['device_path']=', '.join('/dev/'+b.name for b in children)
                result.append(Port('storage:'+p.name,'storage',p.name.upper(),'connected',', '.join(devices),info))
            else:
                result.append(Port('storage:'+p.name,'storage',p.name.upper(),'empty',details=info))
        for p in blocks:
            if p.name in assigned:continue
            # NVMe-/VirtIO-/USB-Laufwerke sind Gerätepfade, keine erfundenen freien Slots.
            size=self.read(p/'size')
            info={'device_path':'/dev/'+p.name,'model':self.read(p/'device/model'),
                  'capacity':str(int(size)*512) if size.isdigit() else '',
                  'removable':self.read(p/'removable'),'source':str(p),'note':'note.block'}
            result.append(Port('storage:'+p.name,'storage',p.name,'connected',info['model'],info))
        return result

    def pcie(self):
        result=[]
        devices=self.entries(self.sys/'bus/pci/devices')
        for p in self.entries(self.sys/'bus/pci/slots'):
            address=self.read(p/'address')
            matching=[d for d in devices if address and (d.name==address or d.name.startswith(address+'.'))]
            state='connected' if matching else ('empty' if address else 'unknown')
            result.append(Port('pcie:'+p.name,'pcie','PCIe '+p.name,state,
                ', '.join(d.name for d in matching),
                {'address':address,'source':str(p),'note':'note.pcie'}))
        return result

    def typec(self):
        result=[]
        root=self.sys/'class/typec'
        for p in self.entries(root):
            if not re.fullmatch(r'port\d+',p.name):continue
            partner=root/(p.name+'-partner')
            result.append(Port('typec:'+p.name,'typec','USB-C '+p.name,
                'connected' if partner.exists() else 'empty',
                details={'data_role':self.read(p/'data_role'),'power_role':self.read(p/'power_role'),
                         'source':str(p),'note':'note.typec'}))
        for p in self.entries(self.sys/'bus/thunderbolt/devices'):
            if p.name.startswith('domain'):continue
            result.append(Port('thunderbolt:'+p.name,'typec','Thunderbolt '+p.name,'connected',
                self.read(p/'device_name'),{'manufacturer':self.read(p/'vendor_name'),
                'authorized':self.read(p/'authorized'),'source':str(p),'note':'note.thunderbolt'}))
        return result

    def serial(self):
        result=[]
        for p in self.entries(self.sys/'class/tty'):
            if not re.fullmatch(r'tty(?:USB|ACM|S)\d+',p.name):continue
            if not (p/'device').exists():continue
            target=str((p/'device').resolve())
            if p.name.startswith('ttyS') and '/platform/serial8250/' in target:continue
            result.append(Port('serial:'+p.name,'serial',p.name,
                'connected' if p.name.startswith(('ttyUSB','ttyACM')) else 'unknown',
                details={'device_path':'/dev/'+p.name,'source':str(p),'note':'note.serial'}))
        return result

    def system_info(self):
        memory={}
        for line in self.read(self.proc/'meminfo').splitlines():
            parts=line.split()
            if len(parts)>=2 and parts[1].isdigit():memory[parts[0].rstrip(':')]=int(parts[1])*1024
        cpu=''
        for line in self.read(self.proc/'cpuinfo').splitlines():
            if line.startswith('model name'):
                cpu=line.split(':',1)[-1].strip();break
        vendor=self.read(self.sys/'class/dmi/id/sys_vendor')
        model=self.read(self.sys/'class/dmi/id/product_name')
        virtual=any(s in (vendor+' '+model).lower() for s in ('qemu','virtual','vmware','kvm','bochs','xen'))
        sensors=[]
        for hw in self.entries(self.sys/'class/hwmon'):
            for value in sorted(hw.glob('temp*_input')):
                text=self.read(value)
                if re.fullmatch(r'-?\d+',text):
                    temperature=int(text)/1000
                    if -50<=temperature<=200:
                        sensors.append((self.read(hw/'name',hw.name)+' '+self.read(value.with_name(value.name.replace('_input','_label')),value.stem),temperature))
        if not sensors:
            for zone in self.entries(self.sys/'class/thermal'):
                if not zone.name.startswith('thermal_zone'):continue
                value=self.read(zone/'temp')
                if re.fullmatch(r'-?\d+',value) and -50000<=int(value)<=200000:
                    sensors.append((self.read(zone/'type',zone.name),int(value)/1000))
        return {'kernel':platform.release(),'cpu':cpu,'vendor':vendor,'model':model,
                'virtual':virtual,'memory_total':memory.get('MemTotal',0),
                'memory_available':memory.get('MemAvailable',0),'sensors':sensors}
