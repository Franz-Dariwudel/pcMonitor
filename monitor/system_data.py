# SPDX-License-Identifier: GPL-3.0-only
"""Erweiterte Linux-Inventur aus lokalen, ausschließlich lesenden Quellen.

Keine Paketinstallation, aktiven WLAN-Scans, TPM-Schreibbefehle oder Netzwerk-
Verbindungen. Optionale Werkzeuge laufen über den zeitlich begrenzten Runner.
Komplexe Kernel-/Werkzeugdaten behalten ihre originalen technischen Feldnamen.
Testpfade dürfen niemals Daten des Entwicklungsrechners einlesen.
"""
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import re
import shlex


def rows(value):
    return value if isinstance(value,list) else []


def text(value):
    """Null bleibt fehlend; Nullwerte und boolesche Werte bleiben erhalten."""
    if value is None:return ''
    if isinstance(value,(dict,list)):return json.dumps(value,ensure_ascii=False,indent=2)
    return str(value)


def os_release(value):
    data={}
    for line in value.splitlines():
        if '=' not in line or line.startswith('#'):continue
        key,raw=line.split('=',1)
        try:data[key]=' '.join(shlex.split(raw))
        except ValueError:continue
    return data


def cpu_ticks(value):
    result={}
    for line in value.splitlines():
        parts=line.split()
        if not parts or not re.fullmatch(r'cpu\d*',parts[0]):continue
        try:values=[int(v) for v in parts[1:9]]
        except ValueError:continue
        if len(values)<4:continue
        # guest/guest_nice sind bereits in user/nice enthalten und werden nicht addiert.
        result[parts[0]]=(sum(values),values[3]+(values[4] if len(values)>4 else 0))
    return result


def mount_unescape(value):
    return re.sub(r'\\([0-7]{3})',lambda m:chr(int(m[1],8)),value)


def flatten_devices(devices,encrypted=False):
    """Verschlüsselung auf abhängige LVs/Dateisysteme weiterreichen."""
    for device in rows(devices):
        if not isinstance(device,dict):continue
        crypt=encrypted or device.get('type')=='crypt' or device.get('fstype')=='crypto_LUKS'
        yield device,crypt
        yield from flatten_devices(device.get('children'),crypt)


class SystemData:
    def __init__(self,hardware):
        self.h=hardware;self.s=hardware.s
        self.root=Path('/') if self.s.sys==Path('/sys') else self.s.sys.parent

    def command(self,args,ttl=5):return self.h.command(args,ttl=ttl)

    def json(self,args,ttl=5):
        try:return json.loads(self.command(args,ttl))
        except (ValueError,TypeError):return None

    def read(self,path):return self.s.read(path)

    def record(self,group,data,**kw):return self.h.record(group,data,**kw)

    def linux(self):
        release=os_release(self.read(self.root/'etc/os-release') or self.read(self.root/'usr/lib/os-release'))
        stat=self.read(self.s.proc/'stat');boot=re.search(r'^btime (\d+)$',stat,re.M)
        uptime=self.read(self.s.proc/'uptime').split()
        d={'distribution':release.get('PRETTY_NAME',''),'kernel':self.read(self.s.proc/'sys/kernel/osrelease'),
           'hostname':self.read(self.s.proc/'sys/kernel/hostname'),
           'architecture':os.uname().machine if self.root==Path('/') else '',
           'boot_time':datetime.fromtimestamp(int(boot[1]),timezone.utc).isoformat() if boot else '',
           'uptime_seconds':uptime[0] if uptime else '',
           'machine_id':self.read(self.root/'etc/machine-id'),
           'boot_id':self.read(self.s.proc/'sys/kernel/random/boot_id'),
           'source':'/etc/os-release · /proc'}
        return self.record('linux',d)

    def cpu(self,d):
        from .hardware import pairs
        blocks=[pairs(b) for b in self.read(self.s.proc/'cpuinfo').split('\n\n') if b.strip()]
        d['microcode']='\n'.join(dict.fromkeys(b.get('microcode','') for b in blocks if b.get('microcode')))
        d['cpu_flags']='\n'.join(dict.fromkeys(b.get('flags',b.get('Features','')) for b in blocks if b.get('flags',b.get('Features'))))
        frequencies=[]
        for p in self.s.entries(self.s.sys/'devices/system/cpu'):
            if not re.fullmatch(r'cpu\d+',p.name):continue
            policy=p/'cpufreq'
            values={key:self.read(policy/key) for key in ('cpuinfo_cur_freq','scaling_cur_freq','cpuinfo_min_freq','cpuinfo_max_freq','scaling_min_freq','scaling_max_freq','scaling_governor')}
            available=[f'{k}={v}'+(' kHz' if k.endswith('freq') else '') for k,v in values.items() if v]
            if available:frequencies.append(p.name+': '+', '.join(available))
        if not frequencies:
            for b in blocks:
                try:value=float(b['cpu MHz'])*1000
                except (KeyError,ValueError):continue
                frequencies.append('cpu'+b.get('processor','?')+f': /proc/cpuinfo={value:g} kHz')
        d['cpu_frequencies']='\n'.join(frequencies)
        now=cpu_ticks(self.read(self.s.proc/'stat'));before=getattr(self.h,'cpu_sample',{})
        usage=[]
        for name,(total,idle) in now.items():
            if name not in before:continue
            old_total,old_idle=before[name];delta=total-old_total;idle_delta=idle-old_idle
            if delta>0 and 0<=idle_delta<=delta:usage.append(f'{name}: {100*(delta-idle_delta)/delta:.1f} %')
        self.h.cpu_sample=now;d['cpu_usage']='\n'.join(usage) or ('value.wait_sample' if now and not before else '')
        nodes=[]
        for p in self.s.entries(self.s.sys/'devices/system/node'):
            if re.fullmatch(r'node\d+',p.name):
                nodes.append(p.name+'\ncpulist: '+self.read(p/'cpulist')+'\ndistance: '+self.read(p/'distance')+'\n'+self.read(p/'meminfo'))
        d['numa']='\n\n'.join(nodes)

    def network(self,d,name):
        path=self.s.sys/'class/net'/name
        for key in ('mtu','carrier'):d[key]=self.read(path/key)
        d['network_statistics']='\n'.join(p.name+': '+self.read(p) for p in self.s.entries(path/'statistics') if p.is_file())
        from .extended import multiline_pairs
        info=multiline_pairs(self.command(['ethtool',name]))
        d['wake_on_lan']=info.get('Wake-on','');d['wol_supported']=info.get('Supports Wake-on','')
        permanent=self.command(['ethtool','-P',name],60)
        d['permanent_mac']=permanent.partition('Permanent address:')[2].strip()
        nm=self.command(['nmcli','--colors','no','--escape','no','--mode','multiline','--fields','GENERAL,IP4,IP6,DHCP4,DHCP6','device','show',name])
        nm=multiline_pairs(nm)
        d['dns']='\n'.join(v for k,v in nm.items() if k.startswith(('IP4.DNS','IP6.DNS')))
        d['dns_search']='\n'.join(v for k,v in nm.items() if k.startswith(('IP4.DOMAIN','IP6.DOMAIN','IP4.SEARCH','IP6.SEARCH')))
        d['dhcp_lease']='\n'.join(k+': '+v for k,v in nm.items() if k.startswith(('DHCP4.OPTION','DHCP6.OPTION')))
        d['dhcp_status']='value.enabled' if d['dhcp_lease'] else 'value.unavailable'
        # Die Konfigurationsmethode ist kein Beweis für einen aktiven DHCP-Lease.
        connection=nm.get('GENERAL.CON-UUID','')
        d['ip_configuration']=''
        if re.fullmatch(r'[0-9a-fA-F-]{36}',connection):
            d['ip_configuration']=self.command(['nmcli','--colors','no','--fields','ipv4.method,ipv6.method','connection','show','uuid',connection],30).strip()
        methods=multiline_pairs(d['ip_configuration'])
        if not d['dhcp_lease'] and methods.get('ipv4.method') in ('manual','disabled','link-local') and methods.get('ipv6.method') in ('manual','disabled','ignore','link-local'):
            d['dhcp_status']='value.disabled'
        d['routes']='\n'.join(self.command(['ip','-'+family,'route','show','table','all','dev',name]).strip() for family in ('4','6')).strip()
        d['neighbors']=self.command(['ip','neigh','show','dev',name]).strip()
        if (path/'wireless').exists():
            link=self.command(['iw','dev',name,'link'])
            match=re.search(r'Connected to ([0-9a-f:]{17})',link,re.I)
            d['bssid']=match[1] if match else ''
            # Nur bereits bekannte APs lesen, keinen Funk-Scan auslösen.
            wifi=self.command(['nmcli','--colors','no','--mode','multiline','--fields','IN-USE,SSID,BSSID,CHAN,FREQ,RATE,SIGNAL,SECURITY','device','wifi','list','ifname',name,'--rescan','no'])
            current=[]
            for block in re.split(r'(?=^IN-USE(?:\[\d+\])?:)',wifi,flags=re.M):
                if re.search(r'^IN-USE[^:]*:\s*\*',block,re.M):current.append(block.strip())
            d['wifi_connection']='\n'.join(current)
            phy=path/'phy80211'
            d['wifi_standards']=self.command(['iw','phy',phy.resolve().name,'info'],300).strip() if phy.exists() else ''

    def filesystems(self):
        columns='NAME,PATH,TYPE,PKNAME,FSTYPE,LABEL,UUID,PARTUUID,MOUNTPOINTS,SIZE,FSSIZE,FSAVAIL,FSUSED,DISC-MAX'
        data=self.json(['lsblk','--json','--bytes','--tree','--output',columns])
        mount_info=self.read(self.s.proc/'self/mountinfo');mounts={}
        for line in mount_info.splitlines():
            parts=line.split()
            if '-' not in parts or len(parts)<7:continue
            sep=parts.index('-')
            if len(parts)>sep+3:mounts[mount_unescape(parts[4])]=parts[5]+'; '+parts[sep+3]
        sizes={}
        # Lokale Dateisysteme erfassen, ohne Netzwerk-Mounts zu kontaktieren.
        for line in self.command(['df','--local','--block-size=1','--output=target,size,used,avail']).splitlines()[1:]:
            parts=line.rsplit(None,3)
            if len(parts)==4 and all(v.isdigit() for v in parts[1:]):
                sizes[parts[0]]={k:int(v) for k,v in zip(('filesystem_size','filesystem_used','filesystem_free'),parts[1:])}
        result=[];seen=set()
        for node,encrypted in flatten_devices(data.get('blockdevices') if isinstance(data,dict) else []):
            name=node.get('path') or node.get('name')
            if not name or name in seen:continue
            seen.add(name)
            d={key:node.get(src) for key,src in {'device_path':'path','partition_type':'type','filesystem_type':'fstype','filesystem_label':'label','uuid':'uuid','partuuid':'partuuid','capacity':'size','filesystem_size':'fssize','filesystem_free':'fsavail','filesystem_used':'fsused','trim_max':'disc-max'}.items()}
            points=[p for p in rows(node.get('mountpoints')) if isinstance(p,str)]
            d['mountpoints']='\n'.join(points);d['mount_options']='\n'.join(p+': '+mounts.get(p,'') for p in points)
            d['encrypted']='value.enabled' if encrypted else 'value.disabled'
            d['source']='lsblk · /proc/self/mountinfo'
            result.append(self.record('filesystems',d,key='filesystem:'+name,name=name))
        # Auch NFS/tmpfs/Overlay und reine Mounts ohne Blockgerät darstellen.
        known={p for node,_ in flatten_devices(data.get('blockdevices') if isinstance(data,dict) else []) for p in rows(node.get('mountpoints')) if p}
        for line in mount_info.splitlines():
            parts=line.split()
            if '-' not in parts or len(parts)<7:continue
            sep=parts.index('-');point=mount_unescape(parts[4])
            if point in known or len(parts)<=sep+3:continue
            result.append(self.record('filesystems',{'mountpoints':point,'filesystem_type':parts[sep+1],
                'device_path':mount_unescape(parts[sep+2]),'mount_options':mounts.get(point,''),
                **sizes.get(point,{}),'source':'/proc/self/mountinfo · df --local'},key='mount:'+parts[0],name=point))
        return result or [self.record('filesystems',{'availability':'value.unavailable','source':'lsblk · /proc/self/mountinfo'},state='unknown')]

    def kernel(self):
        from .hardware import pairs
        memory=pairs(self.read(self.s.proc/'meminfo'))
        groups=[]
        for p in self.s.entries(self.s.sys/'kernel/iommu_groups'):
            devices=[v.name for v in self.s.entries(p/'devices')]
            if devices:groups.append(p.name+': '+', '.join(devices))
        zram=[]
        for p in self.s.entries(self.s.sys/'block'):
            if p.name.startswith('zram'):
                zram.append(p.name+'\n'+'\n'.join(k+': '+self.read(p/k) for k in ('disksize','mm_stat','io_stat','comp_algorithm')))
        d={'swap_total':memory.get('SwapTotal',''),'swap_free':memory.get('SwapFree',''),
           'swap_devices':self.read(self.s.proc/'swaps'),'zram':'\n\n'.join(zram),
           'kernel_modules':self.read(self.s.proc/'modules'),'boot_parameters':self.read(self.s.proc/'cmdline'),
           'kernel_taints':self.read(self.s.proc/'sys/kernel/tainted'),'interrupts':self.read(self.s.proc/'interrupts'),
           'iommu_groups':'\n'.join(groups),'iommu_status':'value.enabled' if groups else 'value.unavailable',
           'source':'/proc · /sys/kernel/iommu_groups · /sys/block'}
        try:d['swap_used']=str(int(memory['SwapTotal'].split()[0])-int(memory['SwapFree'].split()[0]))+' kB'
        except (KeyError,ValueError,IndexError):d['swap_used']=''
        return self.record('kernel',d)

    def services(self):
        output=self.command(['ss','-H','-lntup'])
        result=[]
        for line in output.splitlines():
            parts=line.split(None,6)
            if len(parts)<6:continue
            proc=parts[6] if len(parts)>6 else ''
            d={'protocol':parts[0],'socket_state':parts[1],'local_address':parts[4],'peer_address':parts[5],
               'process':proc,'process_id':', '.join(re.findall(r'pid=(\d+)',proc)), 'source':'ss -H -lntup'}
            result.append(self.record('services',d,key='socket:'+line,name=parts[0]+' '+parts[4]))
        ok=self.h.command_results.get(('ss','-H','-lntup'),False)
        return result or [self.record('services',{'availability':'value.none' if ok else 'value.unavailable','source':'ss -H -lntup'},state='connected' if ok else 'unknown')]

    def security(self,ports):
        d={'lockdown':self.read(self.s.sys/'kernel/security/lockdown'),
           'secure_boot_details':self.command(['mokutil','--sb-state'],60).strip(),'source':'sysfs · mokutil · tpm2_getcap'}
        if not (self.s.sys/'firmware/efi').exists():d['secure_boot_details']='value.legacy'
        for capability,key in (('properties-fixed','tpm_properties'),('pcrs','tpm_pcrs'),('algorithms','tpm_algorithms')):
            d[key]=''
            if self.read(self.s.sys/'class/tpm/tpm0/tpm_version_major')=='2':
                device='/dev/tpmrm0' if (self.root/'dev/tpmrm0').exists() else '/dev/tpm0'
                d[key]=self.command(['tpm2_getcap','-T','device:'+device,capability],300).strip()
        crypt=[p.name for p in ports if p.group=='filesystems' and p.details.get('encrypted')=='value.enabled']
        d['luks_devices']='\n'.join(crypt) or ('value.none' if any('encrypted' in p.details for p in ports if p.group=='filesystems') else '')
        return self.record('security',d)

    def amd(self,d):
        path=self.s.sys/'bus/pci/devices'/d.get('address','')
        d['gpu_util']=self.read(path/'gpu_busy_percent')
        if d['gpu_util']:d['gpu_util']+=' %'
        d['memory_util']=self.read(path/'mem_busy_percent')
        if d['memory_util']:d['memory_util']+=' %'
        for field,file in (('vram_used','mem_info_vram_used'),('vram','mem_info_vram_total')):
            value=self.read(path/file)
            d[field]=int(value) if value.isdigit() and field=='vram' else ((value+' B') if value else '')
        try:d['vram_free']=str(int(self.read(path/'mem_info_vram_total'))-int(self.read(path/'mem_info_vram_used')))+' B'
        except ValueError:d['vram_free']=''
        for field,file in (('gpu_clock','pp_dpm_sclk'),('memory_clock','pp_dpm_mclk')):
            d[field]='\n'.join(line.strip() for line in self.read(path/file).splitlines() if '*' in line)
        driver=path/'driver/module/version';d['driver_version']=self.read(driver)
        for chip in self.s.entries(path/'hwmon'):
            for p in self.s.entries(chip):
                if not re.fullmatch(r'(temp|fan|power)\d+_(input|average)',p.name):continue
                value=self.read(p)
                try:v=float(value)
                except ValueError:continue
                name=self.read(chip/(p.name.split('_')[0]+'_label')) or p.name
                if p.name.startswith('temp'):
                    d.setdefault('gpu_sensors',[]).append(f'{name}: {v/1000:g} °C')
                elif p.name.startswith('fan'):d['fan_rpm']=f'{v:g} RPM'
                else:d['power_draw']=f'{v/1000000:g} W'
        if isinstance(d.get('gpu_sensors'),list):d['gpu_sensors']='\n'.join(d['gpu_sensors'])

    def bluez(self):
        """BlueZ-Inventar lesen, ohne Adapter zu wählen oder Funkaktivität auszulösen."""
        if self.root!=Path('/'):return {}
        try:
            from gi.repository import Gio,GLib
            bus=Gio.bus_get_sync(Gio.BusType.SYSTEM,None)
            result=bus.call_sync('org.bluez','/','org.freedesktop.DBus.ObjectManager',
                'GetManagedObjects',None,None,Gio.DBusCallFlags.NO_AUTO_START,1000,None)
            return bluez_records(result.unpack()[0])
        except Exception:
            # BlueZ ist optional; fehlende Eigenschaften bleiben sichtbar unbekannt.
            return {}

    def enrich(self,ports):
        result=[]
        bluez=self.bluez() if any(p.id.startswith('bluetooth:') for p in ports) else {}
        for port in ports:
            d=dict(port.details)
            if port.id.startswith('bluetooth:') and port.id!='bluetooth:missing':
                adapter=bluez.get(port.id.split(':',1)[1],{'bluetooth_devices':'','bluetooth_connected':''})
                d.update({k:v for k,v in adapter.items() if v or not d.get(k)})
            if port.group=='cpu':self.cpu(d)
            if port.id=='hardware:ram':
                edac=[]
                for mc in self.s.entries(self.s.sys/'devices/system/edac/mc'):
                    if not re.fullmatch(r'mc\d+',mc.name):continue
                    edac.append(mc.name+'\n'+self.read(mc/'mc_name')+'\nce_count: '+self.read(mc/'ce_count')+'\nue_count: '+self.read(mc/'ue_count'))
                    for dimm in self.s.entries(mc):
                        if dimm.name.startswith('dimm'):edac.append(dimm.name+': '+self.read(dimm/'dimm_edac_mode'))
                d['ecc_runtime']='\n'.join(edac)
            if port.group=='network' and not port.id.startswith('bluetooth:'):self.network(d,port.name)
            if port.group in ('gpu','pcie') and d.get('address'):
                group=self.s.sys/'bus/pci/devices'/d['address']/'iommu_group'
                d['iommu_group']=group.resolve().name if group.exists() else ''
            if port.group=='gpu' and d.get('vendor_id','').lower()=='0x1002':self.amd(d)
            result.append(replace(port,details=d))
        result.extend([self.linux(),self.kernel(),*self.filesystems(),*self.services()])
        result.append(self.security(result))
        return result


def bluez_records(objects):
    result={}
    for path,interfaces in objects.items():
        adapter=interfaces.get('org.bluez.Adapter1')
        if not isinstance(adapter,dict):continue
        name=path.rsplit('/',1)[-1]
        data={'address':text(adapter.get('Address')),
              'bluetooth_powered':('value.enabled' if adapter['Powered'] else 'value.disabled') if 'Powered' in adapter else '',
              'bluetooth_controller':'\n'.join(k+': '+text(adapter[k]) for k in ('Manufacturer','Version','Modalias','UUIDs') if k in adapter)}
        known=[];connected=[]
        for device_interfaces in objects.values():
            device=device_interfaces.get('org.bluez.Device1',{})
            if device.get('Adapter')!=path:continue
            title=text(device.get('Address'))+' · '+text(device.get('Name',device.get('Alias')))
            if device.get('Paired') or device.get('Bonded'):known.append(title)
            if device.get('Connected'):connected.append(title)
        data['bluetooth_devices']='\n'.join(known) or 'value.none'
        data['bluetooth_connected']='\n'.join(connected) or 'value.none'
        result[name]=data
    return result
