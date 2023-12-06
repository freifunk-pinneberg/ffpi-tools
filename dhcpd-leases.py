#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Zähle aktive DHCP-Leases

Vergleiche dazu:
  dhcp-lease-list --lease /var/lib/dhcp/dhcpd.leases

Änderungsprotokoll
==================

Version  Datum       Änderung(en)                                           von
-------- ----------- ------------------------------------------------------ ----
1.0      ?
1.1      2017-01-29                                                         tho
2.0      2023-12-06  Umstellung auf Python 3                                tho

"""

import sys
import getopt
import re
import datetime

__author__ = "Thomas Hooge"
__copyright__ = "Public Domain"
__version__ = "2.0"
__email__ = "thomas@hoogi.de"
__status__ = "Development"

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
    print("DHCP leases counter")
    print("Version {}".format(__version__))
    print()
    print("Options")
    print(" -h  show this help")
    print(" -n  numeric output only")
    print()

if __name__ == "__main__":

    verbose = True

    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], "nh", ["help"])
    except getopt.GetoptError as err:
        print(str(err))
        sys.exit(2)
    for opt, arg in opts:
        if opt in ("-h", "--help"):
            usage()
            sys.exit(1)
        elif opt in ("-n"):
            verbose = False
            break

    if verbose:
        print("%d unique active leases" % count_dhcp_leases())
    else:
        print(count_dhcp_leases())
