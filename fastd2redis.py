#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Dieses Programm sollte auf einem Gateway laufen
# Es liefert Informationen über die Tunnel nach Redis

import os  
import sys   
import socket
import json
import subprocess
import datetime

from rediscluster import StrictRedisCluster

def get_gate_nodeid():
    # Die ID kann statisch angegeben werden, falls das nicht
    # der Fall ist, wird der Hostname angenommen
    try:
        with open('/etc/alfred/statics.json', 'r') as fh:
            statics = json.load(fh)
    except (IOError, ValueError):
        return socket.gethostname()
    try:
        nodeid = statics['node']['node_id']
    except:
        nodeid = socket.gethostname()
    return nodeid


def main(rc):

    # fastd-Socket auslesen, liefert ein JSON-Objekt
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client.connect("/var/run/fastd/ffpi.sock")
    except socket.error, msg:  
        print >>sys.stderr, msg
        sys.exit(1)
    data = json.loads(client.makefile('r').read())
    client.close()
    # Ermittelte Daten aufbereiten und nach Redis schreiben
    gate_id = get_gate_nodeid()
    now = datetime.datetime.now().replace(microsecond=0).isoformat()
    peers = {}
    for key, peer in data['peers'].iteritems():
        if peer['connection']:
            try:
                tunnel_id = peer['connection']['mac_addresses'][0].replace(':', '')
            except IndexError:
                continue
            rckey = "fastd:tunnel:%s" % tunnel_id
            rc.hset(rckey, 'key', key)
            rc.hset(rckey, 'last_seen', now)
            rc.hset(rckey, 'last_gate', gate_id)

if __name__ == '__main__':
    startup_nodes = [{"host": "127.0.0.1", "port": "7000"}]
    try:
        rc = StrictRedisCluster(startup_nodes=startup_nodes, decode_responses=True)
    except ConnectionError:
        # Kann z.B. bei lokalen Netzwerkproblemen auftreten
        sys.exit(1)
    main(rc)
