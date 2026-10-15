"""Two colleagues on one LAN must never accept one another's addressed clips."""
import importlib.util
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'mac'))
spec = importlib.util.spec_from_file_location('pair_inbox', Path(__file__).resolve().parents[1] / 'mac/qa-inbox.py')
inbox = importlib.util.module_from_spec(spec); spec.loader.exec_module(inbox)

class PairingTests(unittest.TestCase):
    def test_two_approved_macs_reject_cross_delivery_and_legacy_requests(self):
        with tempfile.TemporaryDirectory() as temp:
            servers=[]
            try:
                for name in ('Alice','Bob'):
                    root=Path(temp)/name;root.mkdir()
                    devices=inbox.Devices(root/'devices.json')
                    # The phone had previously been approved on BOTH computers.
                    devices.data['a'*32]={'status':'approved','name':'Test phone'}
                    server=ThreadingHTTPServer(('127.0.0.1',0),inbox.make_handler(root,devices,"MacBook Pro"))
                    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
                    servers.append((root,devices,server,worker))
                for target_id in ('b'*32, ''):
                    for root,devices,server,worker in servers:
                        base=f'http://127.0.0.1:{server.server_port}'
                        for route,data in [('/ping',None),('/games',b'{"games":["Wrong game"]}'),('/clip',b'wrong footage')]:
                            headers={'X-QA-Key':'a'*32,'X-QA-Mac':target_id,'X-QA-Name':'clip.mp4','Content-Type':'application/json'}
                            with self.subTest(mac=root.name,route=route,target=target_id):
                                with self.assertRaises(HTTPError) as caught: urlopen(Request(base+route,data=data,headers=headers))
                                self.assertEqual(caught.exception.code,409);caught.exception.close()
                        self.assertFalse((root/'inbox.jsonl').exists());self.assertFalse((root/'games.json').exists())
                root,devices,server,_=servers[0]
                with urlopen(f'http://127.0.0.1:{server.server_port}/identity') as response: identity=json.load(response)
                with urlopen(Request(f'http://127.0.0.1:{server.server_port}/ping',headers={'X-QA-Key':'a'*32,'X-QA-Mac':identity['id']})) as response:
                    self.assertEqual(json.load(response)['status'],'approved')
                self.assertNotEqual(servers[0][1].identity['id'],servers[1][1].identity['id'])
                from urllib.parse import quote_plus
                headers={'X-QA-Key':'a'*32,'X-QA-Mac':devices.identity['id'],
                         'X-QA-Meta':quote_plus(json.dumps({'receiverId':servers[1][1].identity['id']}))}
                with self.assertRaises(HTTPError) as caught:
                    urlopen(Request(f'http://127.0.0.1:{server.server_port}/clip',data=b'wrong saved clip',headers=headers))
                self.assertEqual(caught.exception.code,409);caught.exception.close()
                self.assertFalse((root/'inbox.jsonl').exists())
                self.assertEqual(inbox.Devices(root/'devices.json').identity,devices.identity)
            finally:
                for _,_,server,worker in servers:server.shutdown();server.server_close();worker.join()

if __name__=='__main__':unittest.main()
