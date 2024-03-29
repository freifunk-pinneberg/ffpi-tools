#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Anounce-Daemon für Gateways und Server
inspiriert von ffnord-alfred-announce
Bestandteil der Freifunk ffmap-Werkzeuge

Ein Meßwert wird in Anlehnung an Zabbix als Item bezeichnet.

Die Daten werden regelmäßig und häufig, z.B. einmal je Minute an Alfred
übertragen. Das Datensammeln muß aber nicht für jedes Item so häufig
geschehen.
Zu beachten ist, daß Alfred die Daten nach einer bestimmten Zeit
automatisch vergißt, es muß also rechtzeitig erneuert werden.

Es werden ermittelt:
  - Nodeinfo
  - Statistics

Hinweis(e):
  - https://github.com/ffnord/ffnord-alfred-announce
  - http://www.open-mesh.org/projects/alfred/wiki
  - ifstat ansehen
  - dstat ansehen (Python)
  - Konfigurationsverzeichnis: /etc/alfred
    /etc/alfred/statics.json

TODO
  - Items aus Redis holen
  - Ausgabe von "batctl if" auswerten

Änderungsprotokoll
==================

Version  Datum       Änderung(en)                                           von 
-------- ----------- ------------------------------------------------------ ----
0.1      2015-10-18  Änderungsprotokoll eingebaut                           tho
0.2      2016-08-30  Automatisierung Land des Exit-VPNs                     tho
0.3      2016-12-04  DHCPD-Leases integrieren zur Anzeige der Clientanz.    tho
0.4      2017-02-10  Communityunabhängig durch sitecode als Einstellung     tho
0.5      2022-10-05  Umbau auf python3 für Einsatz unter Debian 11          tho
0.6      2023-01-02  -m bei batctl deprecated: durch meshif ersetzt         tho

"""

import os
import sys
import glob
import platform
import getopt
import signal
import daemon
from collections import defaultdict
from collections.abc import Mapping
import json
import subprocess
import socket
import zlib
import time
import logging
import re
import datetime
import functools

__author__ = "Thomas Hooge"
__copyright__ = "Public Domain"
__version__ = "0.6"
__email__ = "thomas@hoogi.de"
__status__ = "Development"

cfg = {
    'logfile': '/var/log/alfred-announced.log',
    'loglevel': 2,
    'pidfile': '/var/run/alfred-announced.pid',
    'daemon': False,
    'user': '',
    'group': 'zabbix',
    'interface': 'bat0',
    'sitecode': 'ffpi'
}

# Definition der auszulesenden Meßwerte
#  
# TODO Zusätzliche Werte
#   - Wie wird der Traffic ausgeleitet?
#     - direkt über Netzwerkinterface
#     - über VPN-Tunnel und ExitVPN
#   - Status des VPN Tunnels (node.vpn.provider)
#     - Anbieter: None, Mullvad, EarthVPN, oVPN.to, ...
#     - Traffic
#

def call(cmdnargs):
    output =  subprocess.check_output(cmdnargs)
    lines = [line.decode("utf-8") for line in output.splitlines()]
    return lines

def fn_dummy():
    return 'n/a'

def fn_node_hostname():
    # Bei Gateways ist der "Hostname" der beschreibende Freitextname
    # Dieser wird durch die statics.json überschrieben
    return socket.gethostname()

def fn_node_vpn():
    return True

def fn_node_net_mac():
     return open('/sys/class/net/{0}/address'.format(cfg['interface'])).read().strip()

def fn_node_net_mesh_ifaces():
    # TODO!
    # Eigentlich:
    # "network": { "mesh": { "bat0": { "interfaces": { "tunnel": [ ...
    # Die Stelle mit "bat0" müßte dynamisch aufgrund der Interfaces
    # zusammengebaut werden
    return [open('/sys/class/net/' + iface + '/address').read().strip()
            for iface in map(lambda line: line.split(':')[0], call(['batctl', 'meshif', cfg['interface'], 'if']))]

def fn_exitvpn_provider():
    """ 
    Wir arbeiten mit der Standardkonfigurationsdatei von OpenVPN.
    Dort ist immer unser aktuell verwendeter Exit-Tunnel eingetragen.
    Wenn OpenVPN konfiguriert ist, aber kein Tunnel verwendet wird,
    steht in der Konfiguration 'none'. Zur Unterscheidung wird im 
    Fehlerfall 'n/a' zurückgeliefert. Das kommt z.B. vor, wenn 
    gar kein  OpenVPN installiert ist.
    """
    try:
        for line in open('/etc/default/openvpn'):
            if line.startswith('AUTOSTART='):
                k, v = line.split("=")
                return v.strip('"\n')
    except IOError:
        pass
    return 'n/a'

def fn_exitvpn_country():
    """
    ISO 3166 Country Code
    """
    provider = fn_exitvpn_provider()
    if provider in ('none', 'n/a'):
        return 'n/a'
    for line in open('/etc/openvpn/' + provider.lower() + '.conf'):
        if line.startswith('## ExitCountry = '):
            k, v = line.split(" = ")
            return v.strip('\n')
    return '??'

def fn_batman_version():
    return open('/sys/module/batman_adv/version').read().strip()

def fn_fastd_enabled():
    """
    Prüfe, ob das init-script existiert und in rc.d aktiviert ist
    - aktuellen Runlevel ermitteln
    - suche einen passenden Link im RC-Verzeichnis
    - prüfe, ob das Script tatsächlich existiert
    """
    runlevel = int(call(['runlevel'])[0].split(' ')[1])
    #fname = glob.glob("/etc/rc%d.d/S??fastd" % runlevel)
    fname = glob.glob("/etc/rc{:02d}.d/S??fastd".format(runlevel))
    if not fname:
        return False
    return os.path.isfile(fname[0])

def fn_fastd_version():
    return call(['fastd', '-v'])[0].split(' ')[1]

def fn_fastd_port():
    for line in open('/etc/fastd/{0}/fastd.conf'.format(cfg['sitecode'])):
        if line.startswith('bind'):
            return line.split(":")[1].rstrip(";\n")

def fn_firmware_base():
    return call(['lsb_release','-is'])[0]

def fn_firmware_release():
    if fn_firmware_base() == 'Debian':
        return call(['cat','/etc/debian_version'])[0]
    else:
        return call(['lsb_release','-rs'])[0]

def fn_idletime():
    return float(open('/proc/uptime').read().split(' ')[1])

def fn_loadavg():
    return float(open('/proc/loadavg').read().split(' ')[0])

def fn_memory():
    m = dict(
            (key.replace('Mem', '').lower(), int(value.split(' ')[0]))
            for key, value in map(lambda s: map(str.strip, s.split(': ', 1)), open('/proc/meminfo').readlines())
            if key in ('MemTotal', 'MemFree', 'Buffers', 'Cached')
        )
    return m

def fn_processes():
    return dict(zip(('running', 'total'), map(int, open('/proc/loadavg').read().split(' ')[3].split('/'))))

def fn_traffic():
    # Ausgabe von ethtool auswerten für bat0
    traffic = {'tx': {}, 'rx': {}, 'forward': {}, 'mgmt_tx': {} , 'mgmt_rx': {}}
    for data in [line.strip() for line in call(['ethtool', '-S', 'bat0'])[1:]]: 
        key, value = data.split(':')
        if key.split('_')[0] in ['tx', 'rx', 'mgmt', 'forward']:
            if not (key.endswith('_bytes') or key.endswith('_dropped')):
                key += '_packets'
            ix1, ix2 = key.rsplit('_', 1)
            traffic[ix1][ix2] = int(value)
    return traffic

def fn_uptime():
    return float(open('/proc/uptime').read().split(' ')[0])

def fn_hardware_model():
    cpuinfo = call(['cat', '/proc/cpuinfo'])
    for line in cpuinfo:
        try:
            key, value = line.split(':')
        except:
            continue
        if key.strip() == "model name":
            return ' '.join(value.split())
    return ''

def fn_hardware_nproc():
    return call(['nproc'])[0]

def fn_fastd_peers():
    # TODO fastd-Konfiguration auslesen /etc/fastd/<sitecode>/fastd.conf
    # 1. fastd über Socket abfragen
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client.connect('/var/run/fastd/{0}.sock'.format(cfg['sitecode']))
    except socket.error:
        return None
    data = json.loads(client.makefile('r').read())
    client.close()
    # 2. Gateways ermitteln (MACs)
    # deprecated
    #with open('/sys/kernel/debug/batman_adv/{0}/gateways'.format(cfg['interface'])) as f:
    #    lines = f.readlines()
    lines = call(['batctl', 'meshif', cfg['interface'], 'gwl'])
    gw_macs = set([gw[3:20] for gw in lines[1:]])
    # 3. Ergebnis ermitteln
    npeers = 0
    for peer in data['peers'].values():
        if peer['connection']:
            if not set(peer['connection']['mac_addresses']) & gw_macs:
                npeers += 1
    return npeers

def fn_dhcpd_leases():
    regex_leaseblock = re.compile(r"lease (?P<ip>\d+\.\d+\.\d+\.\d+) {(?P<config>[\s\S]+?)\n}")
    regex_properties = re.compile(r"\s+(?P<key>\S+) (?P<value>[\s\S]+?);")
    leases = 0
    with open("/var/lib/dhcp/dhcpd.leases") as lease_file:
        macs = set()
        for match in regex_leaseblock.finditer(lease_file.read()):
             block = match.groupdict()
             properties = {key: value for (key, value) in regex_properties.findall(block['config'])}
             if properties['binding'].split(' ')[1] == 'active' and properties['ends'] != 'never':
                 dt_ends = datetime.datetime.strptime(properties['ends'][2:], "%Y/%m/%d %H:%M:%S")
                 if dt_ends > datetime.datetime.utcnow() and properties['hardware'].startswith('ethernet'):
                     macs.add(properties['hardware'][9:])
        leases = len(macs)
    return leases

# Hinweis: Die durch Punkte getrennten Teilschlüssel müssen gültige 
# PHP-Variablennamen sein.
item = {
    'node.hostname': { 'interval': 3600, 'exec': fn_node_hostname },
    'node.vpn': { 'interval': 3600, 'exec': fn_node_vpn },
    'node.network.mac': { 'interval': 3600, 'exec': fn_node_net_mac },
    'node.network.mesh_interfaces': { 'interval': 3600, 'exec': fn_node_net_mesh_ifaces },
    'node.network.exitvpn.provider': { 'interval': 3600, 'exec': fn_exitvpn_provider },
    'node.network.exitvpn.country': { 'interval': 3600, 'exec': fn_exitvpn_country },
    'node.software.batman_adv.version': { 'interval': 3600, 'exec': fn_batman_version },
    'node.software.fastd.version': { 'interval': 3600, 'exec': fn_fastd_version },
    'node.software.fastd.enabled': { 'interval': 60, 'exec': fn_fastd_enabled },
    'node.software.fastd.port': { 'interval': 3600, 'exec': fn_fastd_port },
    'node.software.firmware.base': { 'interval': 3600, 'exec': fn_firmware_base },
    'node.software.firmware.release': { 'interval': 3600, 'exec': fn_firmware_release },
    'node.hardware.model': { 'interval': 3600, 'exec': fn_hardware_model },
    'node.hardware.nproc': { 'interval': 3600, 'exec': fn_hardware_nproc },
    'statistics.idletime': { 'interval': 60, 'exec': fn_idletime },
    'statistics.loadavg': { 'interval': 60, 'exec': fn_loadavg },
    'statistics.memory': { 'interval': 60, 'exec': fn_memory },
    'statistics.processes': { 'interval': 60, 'exec': fn_processes },
    'statistics.traffic': { 'interval': 60, 'exec': fn_traffic },
    'statistics.uptime': { 'interval': 60, 'exec': fn_uptime },
    'statistics.peers': { 'interval': 60, 'exec': fn_fastd_peers },
    'statistics.leases': { 'interval': 60, 'exec': fn_dhcpd_leases },
}

# Die Meßwerte nach Intervall gruppieren
#items_by_interval = defaultdict(list)
#for k, v  in item.iteritems():
#    items_by_interval[v['interval']].append(k) 
#print(items_by_interval)

#for i in items_by_interval:
#    print(i)

# Datenstruktur zum Übertragen an Alfred.
# Wir nehmen die optimale Variante, ggf. ist das *nicht*
# JSON
def dot_to_json(a):
    output = {}
    for key, value in a.items():
        path = key.split('.')
        if path[0] == 'json':
            path = path[1:]  
        target = functools.reduce(lambda d, k: d.setdefault(k, {}), path[:-1], output)
        target[path[-1]] = value
    return output

def merge_dict(d1, d2):
    """
    Modifies d1 in-place to contain values from d2.  If any value
    in d1 is a dictionary (or dict-like), *and* the corresponding
    value in d2 is also a dictionary, then merge them in-place.
    """
    for k, v2 in d2.items():
        v1 = d1.get(k) # returns None if v1 has no value for this key
        if (isinstance(v1, Mapping) and
            isinstance(v2, Mapping)):
            merge_dict(v1, v2)
        else:
            d1[k] = v2

def set_loglevel(nr):
    # Nummer nach Level umsetzen
    levels = [None, logging.CRITICAL, logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG]
    try:
        level = levels[nr]
    except:
        level = logging.INFO
    return level

def usage():
    print("Alfred Announce Daemon for Gateways")
    print("Version {}".format(__version__))
    print()
    print("Optionen")
    print("  -d Programm als Daemon laufen lassen")
    print()

if __name__ == "__main__":

    # Zeitmessung starten
    t0 = time.time()

    # Kommandozeilenoptionen verarbeiten
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], "dh", ["daemon", "help"])
    except getopt.GetoptError as err:
        print(str(err))
        sys.exit(2)   
    for opt, arg in opts:
        if opt in ("-h", "--help"):
            usage()
            sys.exit(1)
        elif opt in ("-d", "daemon"):
            daemon = true
            break

    # Protokollierung anschalten
    logging.basicConfig(level=logging.ERROR,
                        format='%(asctime)s %(levelname)s %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S',  
                        filename=cfg['logfile'],      
                        filemode='a')
    log = logging.getLogger()
    loglevel = set_loglevel(cfg['loglevel'])
    if loglevel:
        log.setLevel(loglevel)
        log.info("{} started on {}".format(sys.argv[0], socket.gethostname()))
    else:
        log.disabled = True

    # Zugeordnete Funktionen je Item ausführen
    result = {}
    for k, v in item.items():
        result[k] = v['exec']()  

    # Daten für Alfred aufbereiten, wir verwenden gzip
    data = dot_to_json(result)

    # Zumischen der statischen Daten
    try:
        with open('/etc/alfred/statics.json', 'r') as fh:
            statics = json.load(fh)
    except IOError:
        statics = {}
    except ValueError:
        statics = {}
        print("Syntax error in statics file, import failed")
    merge_dict(data, statics)

    # Aufteilen in die jew. Datentypen
    nodeinfo = data['node']
    statistics = data['statistics']
    
    cnodeinfo = zlib.compress(bytes(json.dumps(nodeinfo), 'UTF-8'))
    cstatistics = zlib.compress(bytes(json.dumps(statistics), 'UTF-8'))

    # Knoteninfos übertragen
    alfred = subprocess.Popen(['alfred', '-s', '158'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    streamdata = alfred.communicate(cnodeinfo)[0]
    if alfred.returncode != 0:
        print("Communication error with alfred: {}".format(streamdata))

    # Statistik übertragen
    alfred = subprocess.Popen(['alfred', '-s', '159'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    streamdata = alfred.communicate(cstatistics)[0]
    if alfred.returncode != 0:
        print("Communication error with alfred: {}".format(streamdata))

    # Zeitmessung beenden
    tn = time.time()
    log.info("Benötigte Zeit: {:.2f} Minuten" .format((tn-t0)/60))
