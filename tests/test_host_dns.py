import socket
import unittest
from unittest.mock import patch
from tools.check_host_dns import check


class HostDNSTests(unittest.TestCase):
    def answer(self, addresses):
        return [(socket.AF_INET6 if ':' in address else socket.AF_INET, socket.SOCK_STREAM,
                 6, '', (address, 80)) for address in addresses]

    def test_current_server_passes(self):
        with patch('socket.getaddrinfo', return_value=self.answer(['154.16.170.86'])):
            self.assertTrue(check('afribulkhub.com', ['154.16.170.86'])['ready'])

    def test_old_server_and_mixed_dns_fail(self):
        for values in [['181.214.149.146'], ['154.16.170.86', '181.214.149.146'],
                       ['154.16.170.86', '2001:db8::1']]:
            with patch('socket.getaddrinfo', return_value=self.answer(values)):
                self.assertFalse(check('afribulkhub.com', ['154.16.170.86'])['ready'])

    def test_resolution_failure_is_not_ready(self):
        with patch('socket.getaddrinfo', side_effect=socket.gaierror()):
            self.assertFalse(check('afribulkhub.com', ['154.16.170.86'])['ready'])
