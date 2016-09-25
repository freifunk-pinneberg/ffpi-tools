#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Informationen aus dem fastd-Socket anzeigen.
Voraussetzung ist natürlich, daß dieser über die fastd-Konfiguration
eingeschaltet ist.
Programm von Freifunk Pinneberg / Havelock
"""

import os  
import sys   
import socket
import json

def get_fastd_data(sockfile):
    # fastd-Socket auslesen, liefert ein JSON-Objekt
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client.connect(sockfile)
    except socket.error, msg:  
        print >>sys.stderr, msg
        sys.exit(1)
    data = json.loads(client.makefile('r').read())
    client.close()
    return data

def get_gate_macs():
    # Ermitteln der (sichtbaten) Gateways
    with open('/sys/kernel/debug/batman_adv/bat0/gateways') as f:
       lines = f.readlines()
    return set([gw[3:20] for gw in lines[1:]])

def main():
    data = get_fastd_data("/var/run/fastd/ffpi.sock")
    gw_macs = get_gate_macs()
    npeers = 0
    ngates = 0
    for key, peer in data['peers'].iteritems():
        if peer['connection']:
            if set(peer['connection']['mac_addresses']) & gw_macs:
                print "Gate %s (%s) connected as %s..." % (peer['name'], peer['connection']['mac_addresses'][0], key[:16])
                ngates += 1
            else:
                print "Peer %s (%s) connected as %s..." % (peer['name'], peer['connection']['mac_addresses'][0], key[:16])
                npeers += 1
    print "%d peers total, %d gateways and %d peers currently connected" % (len(data['peers']), ngates, npeers)

if __name__ == '__main__':
    main()
