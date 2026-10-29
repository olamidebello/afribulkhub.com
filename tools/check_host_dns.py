#!/usr/bin/env python3
"""Check resolved domain addresses before this host attempts HTTP-01 issuance."""
import argparse
import ipaddress
import json
import socket


def check(domain, local):
    allowed = {str(ipaddress.ip_address(value)) for value in local}
    try:
        resolved = {str(ipaddress.ip_address(item[4][0]))
                    for item in socket.getaddrinfo(domain, 80, type=socket.SOCK_STREAM)}
    except socket.gaierror:
        resolved = set()
    unexpected = resolved-allowed
    return {'domain': domain, 'resolved': sorted(resolved), 'server_addresses': sorted(allowed),
            'unexpected': sorted(unexpected), 'ready': bool(resolved) and not unexpected}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--domain', required=True)
    parser.add_argument('--local', required=True, help='JSON array of this server interface addresses')
    args = parser.parse_args()
    print(json.dumps(check(args.domain, json.loads(args.local))))
