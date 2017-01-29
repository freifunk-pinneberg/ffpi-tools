#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Vergleiche
# dhcp-lease-list --lease /var/lib/dhcp/dhcpd.leases

import sys
import getopt
import re
import datetime

def count_dhcp_leases():
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

def usage():
    print "DHCP leases counter"
    print "Version 1.1"
    print
    print "Options"
    print " -n  numeric output only"
    print

if __name__ == "__main__":

    verbose = True

    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], "nh", ["help"])
    except getopt.GetoptError, err:
        print str(err)
        sys.exit(2)
    for opt, arg in opts:
        if opt in ("-h", "--help"):
            usage()
            sys.exit(1)
        elif opt in ("-n"):
            verbose = False
            break

    if verbose:
        print "%d unique active leases" % count_dhcp_leases()
    else:
        print count_dhcp_leases()
