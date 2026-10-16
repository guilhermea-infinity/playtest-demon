"""The frozen service must re-exec its receiver, never treat its own executable as Python."""
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'mac'))
spec=importlib.util.spec_from_file_location('qa_desk',Path(__file__).resolve().parents[1]/'mac/qa-desk.py')
desk=importlib.util.module_from_spec(spec);spec.loader.exec_module(desk)


class NativePackageTests(unittest.TestCase):
    def test_frozen_receiver_uses_executable_mode(self):
        fake=MagicMock();fake.stdout=[]
        with patch.object(sys,'frozen',True,create=True),patch.object(sys,'executable','/App/service'),patch.object(desk,'port_busy',return_value=False),patch.object(desk.subprocess,'Popen',return_value=fake) as start:
            desk.start_inbox(Path('/tmp/synthetic-inbox'))
            self.assertEqual(start.call_args.args[0],['/App/service','--receiver','--inbox','/tmp/synthetic-inbox'])
            self.assertTrue(start.call_args.kwargs['start_new_session'])
            self.assertEqual(start.call_args.kwargs['env']['PLAYTEST_DEMON_DESK_PID'], str(desk.os.getpid()))

    def test_source_receiver_keeps_python_script_mode(self):
        fake=MagicMock();fake.stdout=[]
        with patch.object(sys,'frozen',False,create=True),patch.object(desk,'port_busy',return_value=False),patch.object(desk.subprocess,'Popen',return_value=fake) as start:
            desk.start_inbox(Path('/tmp/synthetic-inbox'))
            args=start.call_args.args[0]
            self.assertEqual(args[:2],[sys.executable,'-u'])
            self.assertTrue(args[2].endswith('qa-inbox.py'))

if __name__=='__main__':unittest.main()
