import importlib.util,json,socket,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('hub_port_selector',Path(__file__).resolve().parents[1]/'tools/select_port.py');selector=importlib.util.module_from_spec(spec);spec.loader.exec_module(selector)
class PortSelectionTests(unittest.TestCase):
    def test_foreign_listener_is_preserved_and_automatic_port_skips_it(self):
        with socket.socket() as foreign:
            foreign.bind(('127.0.0.1',0));foreign.listen();port=foreign.getsockname()[1]
            with patch.object(selector,'owned',return_value=False):
                with self.assertRaisesRegex(ValueError,'another service'):selector.choose(preferred=port)
                chosen=selector.choose(start=port,end=min(port+20,65535));self.assertNotEqual(chosen,port)
            self.assertEqual(foreign.getsockname()[1],port);self.assertFalse(selector.available(port))
    def test_saved_healthy_hub_port_is_reused(self):
        with tempfile.TemporaryDirectory() as d:
            saved=Path(d)/'listen-port.json';saved.write_text(json.dumps({'port':18780}))
            with patch.object(selector,'available',return_value=False),patch.object(selector,'owned',side_effect=lambda p:p==18780):self.assertEqual(selector.choose(saved=saved),18780)
    def test_existing_tls_vhost_port_is_preserved_when_free(self):
        with tempfile.TemporaryDirectory() as d:
            vhost=Path(d)/'site.conf';vhost.write_text('server { listen 443 ssl; server_name afribulkhub.com; ssl_certificate /keep.pem; location / { proxy_pass http://127.0.0.1:18791; } }')
            before=vhost.read_bytes()
            with patch.object(selector,'available',return_value=True):self.assertEqual(selector.choose(vhost=vhost),18791)
            self.assertEqual(vhost.read_bytes(),before)
    def test_foreign_vhost_is_never_adopted(self):
        with tempfile.TemporaryDirectory() as d:
            vhost=Path(d)/'site.conf';vhost.write_text('server_name africaatona.africandroid.world; proxy_pass http://127.0.0.1:8097;')
            with self.assertRaisesRegex(ValueError,'different domain'):selector.choose(vhost=vhost)
    def test_occupied_stale_saved_port_moves_to_free_candidate(self):
        with tempfile.TemporaryDirectory() as d:
            saved=Path(d)/'listen-port.json';saved.write_text('{"port":8097}')
            with patch.object(selector,'available',side_effect=lambda p:p==18771),patch.object(selector,'owned',return_value=False):self.assertEqual(selector.choose(saved=saved),18771)
if __name__=='__main__':unittest.main()
