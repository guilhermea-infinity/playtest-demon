"""A receiver owned by a desk must release its port even if the desk is killed."""
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.request import urlopen

RECEIVER = Path(__file__).resolve().parents[1] / 'mac/qa-inbox.py'


def listening(port):
    with socket.socket() as s:
        s.settimeout(.2)
        return s.connect_ex(('127.0.0.1',port)) == 0


def until(predicate, timeout=8):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if predicate():return True
        time.sleep(.05)
    return False


class ReceiverLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        with socket.socket() as s:s.bind(('127.0.0.1',0));self.port=s.getsockname()[1]
        self.args=[sys.executable,'-u',str(RECEIVER),'--inbox',str(root/'clips'),'--devices',str(root/'devices.json'),'--port',str(self.port),'--no-usb','--no-bonjour']

    def test_managed_receiver_exits_when_its_desk_dies_without_cleanup(self):
        script='import os,subprocess,sys,time; env=dict(os.environ); env["PLAYTEST_DEMON_DESK_PID"]=str(os.getpid()); child=subprocess.Popen(sys.argv[1:],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); print(child.pid,flush=True); time.sleep(60)'
        parent=subprocess.Popen([sys.executable,'-c',script,*self.args],stdout=subprocess.PIPE,text=True)
        receiver_pid=None
        try:
            receiver_pid=int(parent.stdout.readline())
            self.assertTrue(until(lambda:listening(self.port)),'receiver did not start')
            parent.kill();parent.wait(timeout=3) # SIGKILL prevents the desk doing cleanup.
            self.assertTrue(until(lambda:not listening(self.port),timeout=4),'orphan receiver kept the port after its desk was killed')
        finally:
            if parent.poll() is None:parent.kill();parent.wait(timeout=3)
            parent.stdout.close()
            if receiver_pid:
                try:os.kill(receiver_pid,signal.SIGTERM)
                except ProcessLookupError:pass

    def test_standalone_receiver_still_runs_without_a_desk_owner(self):
        env=dict(os.environ);env.pop('PLAYTEST_DEMON_DESK_PID',None);env.pop('PLAYTEST_DEMON_APP_PID',None)
        p=subprocess.Popen(self.args,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            self.assertTrue(until(lambda:listening(self.port)))
            time.sleep(1.3)
            with urlopen(f'http://127.0.0.1:{self.port}/identity',timeout=2) as response:self.assertIn('id',json.load(response))
            self.assertIsNone(p.poll())
        finally:
            p.terminate();p.wait(timeout=3)
