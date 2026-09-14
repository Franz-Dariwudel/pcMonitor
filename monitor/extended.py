# SPDX-License-Identifier: GPL-3.0-only
"""Zusätzliche lesende Messwerte; keine Treiber-, Netzwerk- oder Firmwareänderungen.

Werkzeugausgaben werden mit LC_ALL=C erfasst. Dynamische Werte haben keinen
Langzeitcache. Statische Controllerdaten werden vom gemeinsamen Runner gecacht.
Unbekannte Sensoren behalten ihre Kernelbeschriftung, insbesondere Spannungen.
"""
from dataclasses import replace
import json
import os
import re


def tree_values(text):
    """Eingerückte nvidia-smi -q-Ausgabe ohne mehrdeutige Blattnamen zerlegen."""
    result={};stack=[]
    for line in text.splitlines():
        if not line.strip():continue
        indent=len(line)-len(line.lstrip());content=line.strip()
        while stack and stack[-1][0]>=indent:stack.pop()
        if ' : ' in content or re.search(r'\s+:',content):
            key,value=content.split(':',1)
            result[tuple(x[1] for x in stack)+(key.strip(),)]=value.strip()
        else:stack.append((indent,content))
    return result


GPU_FIELDS={
 'vbios':('VBIOS Version',),'gpu_util':('Utilization','Gpu'),
 'memory_util':('Utilization','Memory'),'vram_used':('FB Memory Usage','Used'),
 'vram_free':('FB Memory Usage','Free'),'fan_percent':('Fan Speed',),
 'power_draw':('GPU Power Readings','Instantaneous Power Draw'),
 'power_average':('GPU Power Readings','Average Power Draw'),
 'power_limit':('GPU Power Readings','Current Power Limit'),
 'gpu_clock':('Clocks','Graphics'),'memory_clock':('Clocks','Memory'),
 'pcie_generation':('PCI','GPU Link Info','PCIe Generation','Current'),
 'pcie_generation_max':('PCI','GPU Link Info','PCIe Generation','Max'),
 'pcie_width':('PCI','GPU Link Info','Link Width','Current'),
 'pcie_width_max':('PCI','GPU Link Info','Link Width','Max'),
 'performance_state':('Performance State',),'gpu_uuid':('GPU UUID',),
 'temperature':('Temperature','GPU Current Temp',)}


def usable(value):
    return '' if value in ('N/A','[N/A]','Not Supported') or 'deprecated' in value else value


def nvidia_details(text):
    result={};values=tree_values(text)
    for match in re.finditer(r'^GPU ([0-9a-fA-F]{4,8}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.\d)\s*$',text,re.M):
        name='GPU '+match[1];data={key:usable(values.get((name,*path),'')) for key,path in GPU_FIELDS.items()}
        data['driver_version']=values.get(('Driver Version',),'')
        data['cuda_version']=values.get(('CUDA Version',),'')
        for key,path in {'power_draw':('Power Readings','Power Draw'),'power_limit':('Power Readings','Power Limit')}.items():
            if not data[key]:data[key]=usable(values.get((name,*path),''))
        for key,path in {'vram':('FB Memory Usage','Total'),'serial_number':('Serial Number',)}.items():
            value=usable(values.get((name,*path),''))
            if key=='vram':
                m=re.fullmatch(r'(\d+) MiB',value)
                if m:data[key]=int(m[1])*1024*1024
            elif value:data[key]=value
        result[match[1].lower()[-12:]]=data
    return result


def multiline_pairs(text):
    """Fortsetzungszeilen der von ethtool gemeldeten Linkmodi beibehalten."""
    data={};key=None
    for line in text.splitlines():
        if ':' in line:
            key,value=line.strip().split(':',1);data[key]=value.strip()
        elif key and line[:1].isspace():data[key]+=' '+line.strip()
    return data


class Extended:
    def __init__(self,hardware):self.h=hardware;self.s=hardware.s
    def command(self,args,ttl=0):return self.h.command(args,ttl=ttl)
    def json(self,args,ttl=0):
        try:return json.loads(self.command(args,ttl))
        except (ValueError,TypeError):return None

    def enrich(self,ports):
        nvidia=nvidia_details(self.command(['nvidia-smi','-q'])) if any(p.group=='gpu' and p.details.get('vendor_id')=='0x10de' for p in ports) else {}
        addresses=self.json(['ip','-j','address','show']) if any(p.group=='network' for p in ports) else []
        addresses={d.get('ifname'):d for d in (addresses or []) if isinstance(d,dict)}
        routes={family:self.json(['ip','-j',flag,'route','show','default']) or [] for family,flag in (('ipv4','-4'),('ipv6','-6'))} if addresses else {}
        result=[]
        for port in ports:
            d=dict(port.details)
            if port.group=='gpu' and d.get('vendor_id')=='0x10de':
                d.update({k:'' for k in (*GPU_FIELDS,'driver_version','cuda_version')})
                d.update(nvidia.get(d.get('address','').lower(),{}))
            if port.group=='cpu':
                root=self.s.sys/'devices/system/cpu'
                active=self.s.read(root/'smt/active')
                d['smt_active']={'0':'value.disabled','1':'value.enabled'}.get(active,'')
                d['smt_control']=self.s.read(root/'smt/control');d['online_cpus']=self.s.read(root/'online')
                siblings=self.s.read(root/'cpu0/topology/thread_siblings_list')
                d['thread_siblings']=siblings
            if port.group=='network':
                addr=addresses.get(port.name,{}).get('addr_info',[])
                for family,kind in (('ipv4','inet'),('ipv6','inet6')):
                    d[family]='\n'.join(f"{a['local']}/{a['prefixlen']}" for a in addr if a.get('family')==kind and 'local' in a and 'prefixlen' in a)
                    d['gateway_'+family]='\n'.join(str(r.get('gateway',''))+' · metric '+str(r.get('metric',0)) for r in routes.get(family,[]) if r.get('dev')==port.name)
                info=multiline_pairs(self.command(['ethtool',port.name]))
                for key,source in {'link_modes':'Supported link modes','advertised_modes':'Advertised link modes','partner_modes':'Link partner advertised link modes','autonegotiation':'Auto-negotiation','duplex':'Duplex','link_speed':'Speed'}.items():d[key]=info.get(source,'')
                info=multiline_pairs(self.command(['ethtool','-i',port.name],ttl=60))
                d['driver_version']=info.get('version','');d['network_firmware']=info.get('firmware-version','')
                if (self.s.sys/'class/net'/port.name/'wireless').exists():
                    info=multiline_pairs(self.command(['iw','dev',port.name,'link']))
                    d.update({k:info.get(v,'') for k,v in {'ssid':'SSID','wifi_signal':'signal','wifi_frequency':'freq','wifi_rate':'tx bitrate'}.items()})
                    d['wireless']='value.enabled'
            if port.group in ('gpu','pcie'):
                self.pci_link(d,self.s.sys/'bus/pci/devices'/d.get('address',''))
            if port.group=='storage' and port.name.startswith('nvme'):
                self.nvme(d,port.name)
            if port.group=='bios':self.secure_boot(d)
            result.append(replace(port,details=d))
        # Logische Interfaces sind IP-Träger, keine zusätzlichen physischen Buchsen.
        known={p.name for p in ports if p.group=='network'}
        for name,addr in addresses.items():
            if name in known or name=='lo':continue
            data={'interface_type':'value.logical','source':str(self.s.sys/'class/net'/name)}
            for family,kind in (('ipv4','inet'),('ipv6','inet6')):
                data[family]='\n'.join(f"{a['local']}/{a['prefixlen']}" for a in addr.get('addr_info',[]) if a.get('family')==kind and 'local' in a and 'prefixlen' in a)
                data['gateway_'+family]='\n'.join(str(r.get('gateway','')) for r in routes.get(family,[]) if r.get('dev')==name)
            result.append(self.h.record('network',data,key='logical:'+name,name=name,state='connected' if 'UP' in addr.get('flags',[]) else 'unknown'))
        result.extend(self.sensors());result.extend(self.bluetooth());result.extend(self.tpm())
        return result

    def pci_link(self,d,path):
        for key,name in {'pcie_speed':'current_link_speed','pcie_speed_max':'max_link_speed','pcie_width':'current_link_width','pcie_width_max':'max_link_width'}.items():
            value=self.s.read(path/name)
            if value:d.setdefault(key,value) if d.get(key) else d.update({key:value})

    def sensors(self):
        result=[]
        for chip in self.s.entries(self.s.sys/'class/hwmon'):
            for path in self.s.entries(chip):
                m=re.fullmatch(r'(fan|in|power)(\d+)_(input|average)',path.name)
                if not m:continue
                value=self.s.read(path)
                try:number=float(value)
                except ValueError:continue
                key,scale,unit={'fan':('fan_rpm',1,'RPM'),'in':('voltage',1000,'V'),'power':('sensor_power',1000000,'W')}[m[1]]
                name=self.s.read(chip/'name') or chip.name
                channel=self.s.read(chip/(m[1]+m[2]+'_label')) or m[1]+m[2]
                result.append(self.h.record('temperature',{key:f'{number/scale:g} {unit}','source':str(path)},key='sensor:'+chip.name+':'+path.name,name=name+' · '+channel+' · '+m[3]))
        return result

    def secure_boot(self,d):
        root=self.s.sys/'firmware/efi'
        d['secure_boot']='value.unavailable'
        if not root.exists():d['secure_boot']='value.legacy';return
        for p in self.s.entries(root/'efivars'):
            if not p.name.startswith('SecureBoot-'):continue
            try:
                value=p.read_bytes()
                if len(value)>=5:d['secure_boot']={0:'value.disabled',1:'value.enabled'}.get(value[4],'value.unavailable')
            except OSError:pass
        if d['secure_boot']=='value.unavailable':
            value=self.command(['mokutil','--sb-state'],ttl=60)
            if 'SecureBoot enabled' in value:d['secure_boot']='value.enabled'
            elif 'SecureBoot disabled' in value:d['secure_boot']='value.disabled'

    def tpm(self):
        ports=[]
        root=self.s.sys/'class/tpm'
        for p in self.s.entries(root):
            d={'tpm_version':self.s.read(p/'tpm_version_major'),'description':self.s.read(p/'device/description'),'source':str(p)}
            driver=p/'device/driver';d['driver']=driver.resolve().name if driver.exists() else ''
            ports.append(self.h.record('mainboard',d,key='tpm:'+p.name,name='TPM · '+p.name))
        if not ports:ports.append(self.h.record('mainboard',{'availability':'value.tpm_not_reported','source':str(root)},key='tpm:missing',name='TPM',state='unknown'))
        return ports

    def bluetooth(self):
        ports=[]
        for p in self.s.entries(self.s.sys/'class/bluetooth'):
            if not re.fullmatch(r'hci\d+',p.name):continue
            address=self.s.read(p/'address')
            # Ein fehlendes sysfs-Adressattribut ist bei neueren Kerneln normal.
            info=multiline_pairs(self.command(['bluetoothctl','show',address])) if address else {}
            adapters=[x for x in self.s.entries(self.s.sys/'class/bluetooth') if re.fullmatch(r'hci\d+',x.name)]
            if not address and len(adapters)==1:info=multiline_pairs(self.command(['bluetoothctl','show']))
            driver=p/'device/driver'
            d={'address':address,'driver':driver.resolve().name if driver.exists() else '',
               'bluetooth_powered':{'yes':'value.enabled','no':'value.disabled'}.get(info.get('Powered'),''),
               'model':info.get('Name',''),'source':str(p),'bluetooth':'value.enabled'}
            ports.append(self.h.record('network',d,key='bluetooth:'+p.name,name='Bluetooth · '+p.name))
        if not ports:ports.append(self.h.record('network',{'availability':'value.bluetooth_not_reported','source':str(self.s.sys/'class/bluetooth')},key='bluetooth:missing',name='Bluetooth',state='unknown'))
        return ports

    def nvme(self,d,name):
        controller=re.match(r'(nvme\d+)',name)[1]
        path=self.s.sys/'class/nvme'/controller
        d['nvme_controller']=controller
        for key,filename in {'nvme_transport':'transport','nvme_state':'state','nvme_nqn':'subsysnqn'}.items():d[key]=self.s.read(path/filename)
        self.pci_link(d,path/'device')
        for key in ('nvme_namespaces','nvme_capacity','nvme_critical_warning','nvme_available_spare','nvme_percentage_used','nvme_data_units_read','nvme_data_units_written','nvme_power_cycles','nvme_power_on_hours','nvme_unsafe_shutdowns','nvme_media_errors','nvme_num_err_log_entries'):d[key]=''
        if os.geteuid()!=0:return
        info=self.json(['nvme','id-ctrl','/dev/'+controller,'-o','json'],ttl=300)
        if isinstance(info,dict):
            for key,source in {'model':'mn','serial_number':'sn','firmware':'fr','nvme_version':'ver','nvme_namespaces':'nn','nvme_capacity':'tnvmcap'}.items():
                if source in info:d[key]=str(info[source]).strip()
        info=self.json(['nvme','smart-log','/dev/'+controller,'-o','json'])
        if isinstance(info,dict):
            for key in ('critical_warning','available_spare','percentage_used','data_units_read','data_units_written','power_cycles','power_on_hours','unsafe_shutdowns','media_errors','num_err_log_entries'):
                if key in info:d['nvme_'+key]=str(info[key])
