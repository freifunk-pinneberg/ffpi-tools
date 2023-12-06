#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Informationen aus dem fastd-Socket anzeigen.
Voraussetzung ist natürlich, daß dieser über die fastd-Konfiguration
eingeschaltet ist.
Programm von Freifunk Pinneberg / Havelock

TODO Mehr automatisieren
- pidof fastd liefert Liste mit laufenden Prozessen (Trennung mit Leerzeichen)
- /proc/<pid>/cmdline liefert Kommando mit Konfigurationsdatei
- dann Konfigurationsdatei auswerten

Änderungsprotokoll
==================

Version  Datum       Änderung(en)                                           von
-------- ----------- ------------------------------------------------------ ----
0.1      2015-09-27  Änderungsprotokoll eingebaut                           tho
0.2      2023-01-08  Umstellung auf Python 3                                tho
0.3      2023-12-06  Zugriff auf debugfs für GW-Interfaces entfernt         tho

"""

import os
import sys
import socket
import json
import subprocess

__author__ = "Thomas Hooge"
__copyright__ = "Public Domain"
__version__ = "0.3"
__email__ = "thomas@hoogi.de"
__status__ = "Development"

def call(cmdnargs):
    output =  subprocess.check_output(cmdnargs)
    lines = [line.decode("utf-8") for line in output.splitlines()]
    return lines

def get_fastd_data(sockfile):
    # fastd-Socket auslesen, liefert ein JSON-Objekt
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client.connect(sockfile)
    except socket.error as msg:
        print(msg, file=sys.stderr)
        sys.exit(1)
    data = json.loads(client.makefile('r').read())
    client.close()
    return data

def get_gate_macs():
    # Ermitteln der (sichtbaren) Gateways
    lines = call(['batctl', 'meshif', 'bat0', 'gwl'])
    return set([gw[3:20] for gw in lines[1:]])

def main():
    data = get_fastd_data("/var/run/fastd/ffpi.sock")
    gw_macs = get_gate_macs()
    npeers = 0
    ngates = 0
    for key, peer in data['peers'].items():
        if peer['connection']:
            if set(peer['connection']['mac_addresses']) & gw_macs:
                print("Gate %s (%s) connected as %s..." % (peer['name'], peer['connection']['mac_addresses'][0], key[:16]))
                ngates += 1
            else:
                try:
                    peer_mac = peer['connection']['mac_addresses'][0]
                except:
                    peer_mac = '*no mac*'
                print("Peer %s (%s) connected as %s..." % (peer['name'], peer_mac, key[:16]))
                npeers += 1
    print("%d peers total, %d gateways and %d peers currently connected" % (len(data['peers']), ngates, npeers))

if __name__ == '__main__':
    main()
