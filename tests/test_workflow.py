import io
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'mac'))
from desk_store import Store, write_json
from desk_runs import Runs, command
from desk_import import import_recording


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.store = Store(self.root / 'inbox')
        self.runner = Runs(self.store, threading.Event())
        self.repo = {'path': str(self.root), 'github': 'test/game', 'base': 'main', 'testCommand': 'python3 check.py',
                     'provider': 'codex', 'model': '', 'effort': '', 'autoMerge': False}
        write_json(self.store.root / 'repositories.json', {'Game': self.repo})
        (self.store.inbox / 'Game').mkdir()
        (self.store.inbox / 'Game/clip.mp4').write_bytes(b'synthetic evidence')
        self.store.set_clip('Game/clip.mp4', status='done', meta={'game': 'Game'}, tickets=['GA-001'])
        self.ticket()

    def ticket(self, tid='GA-001', status='approved', title='Reward should become disabled'):
        t = {'id': tid, 'game': 'Game', 'clip': 'Game/clip.mp4', 'title': title, 'status': status,
             'kind': 'bug', 'priority': 'normal', 'where': 'Reward button', 'now': 'Always enabled', 'want': 'Disable after use',
             'done_when': 'Second click is disabled', 'shots': [], 'steps': [], 'moment': {}, 'order': 1, 'approvedAt': 'earlier approval'}
        self.store.save_ticket(t); return t

    def test_duplicate_evidence_is_reversible_and_scoped(self):
        self.ticket('GA-002', 'draft', 'Reward should be disabled')
        self.assertEqual(self.store.duplicate_candidates('GA-002')[0]['id'], 'GA-001')
        self.store.link_duplicate('GA-002', 'GA-001')
        self.assertEqual(len(self.store.trays()[0]['ids']), 1)
        self.assertEqual(self.store.tickets['GA-002']['now'], 'Always enabled')
        self.store.unlink_duplicate('GA-002')
        self.assertEqual(self.store.tickets['GA-002']['status'], 'draft')
        other = self.ticket('XX-001'); other['game'] = 'Other'; self.store.save_ticket(other)
        with self.assertRaises(ValueError): self.store.link_duplicate('GA-002', 'XX-001')

    def test_trash_restores_tickets_and_does_not_reimport(self):
        self.store.trash_clip('Game/clip.mp4')
        self.assertFalse(self.store.state()['clips']); self.assertFalse(self.store.trays())
        self.assertTrue((self.store.inbox / 'Game/clip.mp4').exists())
        with (self.store.inbox / 'inbox.jsonl').open('w') as f: f.write(json.dumps({'file': 'Game/clip.mp4'})+'\n')
        self.assertEqual(self.store.sync_inbox(), 0)
        self.store.trash_clip('Game/clip.mp4', True)
        self.assertEqual(self.store.tickets['GA-001']['status'], 'approved')

    def test_no_redraft_without_correction_or_approval_of_empty_request(self):
        self.assertFalse(self.store.retry_clip('Game/clip.mp4'))
        self.ticket('GA-002', 'draft'); self.store.update_ticket('GA-002', {'want': ''})
        self.assertIsNone(self.store.set_status('GA-002', 'approved'))
        self.assertEqual(self.store.tickets['GA-002']['status'], 'draft')

    def test_double_submit_reserves_one_batch_and_freezes_tickets(self):
        results=[]
        def submit():
            try: results.append(self.runner.submit('Game', ['GA-001']))
            except ValueError: results.append(None)
        threads=[threading.Thread(target=submit) for _ in range(2)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(len(self.runner.items()), 1)
        self.assertEqual(self.store.tickets['GA-001']['status'], 'fixing')
        self.assertIsNone(self.store.update_ticket('GA-001', {'title': 'Altered'}))
        self.assertIsNone(self.store.set_status('GA-001', 'draft'))
        with self.assertRaises(ValueError): self.store.trash_clip('Game/clip.mp4')
        self.assertFalse(self.store.retry_clip('Game/clip.mp4', 'hint'))
        saved=self.runner.items()[0]
        self.assertEqual(saved['snapshot'][0]['title'], 'Reward should become disabled')

    def test_restart_is_interrupted_and_cancel_returns_to_batch(self):
        r=self.runner.submit('Game', ['GA-001'])
        restarted=Runs(self.store, threading.Event())
        self.assertEqual(restarted.items()[0]['status'], 'interrupted')
        restarted.cancel(r['id'])
        self.assertEqual(self.store.tickets['GA-001']['status'], 'approved')
        self.assertNotIn('runId', self.store.tickets['GA-001'])

    def prepare_remote(self):
        source=self.root/'source'; source.mkdir()
        command(['git','init','-b','main'],source)
        (source/'game.py').write_text('def reward():\n    return 2\n')
        (source/'check.py').write_text('from game import reward\nassert reward() == 3\n')
        (source/'.gitignore').write_text('__pycache__/\n')
        command(['git','add','.'],source)
        command(['git','-c','user.name=Test','-c','user.email=test@example.com','commit','-m','fixture'],source)
        remote=self.root/'remote.git'; command(['git','clone','--bare',str(source),str(remote)])
        return source,remote

    def full_run(self, fix=True, existing=False):
        source,remote=self.prepare_remote(); r=self.runner.submit('Game',['GA-001'])
        real_execute=self.runner.execute
        def execute(rid,args,cwd,**kw):
            if args[0]=='git' and 'clone' in args:
                args=[*args[:-2],str(remote),args[-1]]
            return real_execute(rid,args,cwd,**kw)
        def agent(rid,clone,prompt,config):
            self.assertIn('GA-001',prompt)
            self.assertTrue((clone/'.playtest-evidence/GA-001-recording.mp4').exists())
            if fix: (clone/'game.py').write_text('def reward():\n    return 3\n')
            write_json(clone/'.playtest-result.json',{'summary':'Fixed reward','addressed':['GA-001'],'unaddressed':[],'notes':'Regression check included'})
        calls=[]
        def cmds(args,*a,**kw):
            if args[0]=='gh':
                calls.append(args)
                if args[1:3]==['pr','list']: return json.dumps([{'url':'https://github.com/test/game/pull/1'}] if existing else [])
                return 'https://github.com/test/game/pull/1'
            return command(args,*a,**kw)
        with patch.object(self.runner,'execute',side_effect=execute),patch.object(self.runner,'agent',side_effect=agent),patch('desk_runs.command',side_effect=cmds):
            self.runner.perform(r)
        self.assertIn('return 2',(source/'game.py').read_text())
        return self.runner.items()[0],calls

    def test_isolated_fix_test_commit_push_and_pr(self):
        r,calls=self.full_run()
        self.assertEqual(r['status'],'pr_ready',r.get('error'))
        self.assertTrue(r['testsPassed']); self.assertTrue(r['headSha'])
        self.assertEqual(len([c for c in calls if c[1:3]==['pr','create']]),1)
        self.assertFalse((self.runner.root/r['id']/'repo/.playtest-evidence').exists())
        self.assertTrue((self.runner.root/r['id']/'run.log').is_file())

    def test_failed_tests_never_publish_or_mark_fixed(self):
        r,calls=self.full_run(False)
        self.assertEqual(r['status'],'failed')
        self.assertFalse(calls)
        self.assertEqual(self.store.tickets['GA-001']['status'],'fixing')

    def test_failed_checks_retry_saved_code_without_another_agent_or_clone(self):
        r,_=self.full_run(False);rid=r['id'];clone=self.runner.root/rid/'repo'
        self.assertEqual(r['status'],'failed')
        (clone/'game.py').write_text('def reward():\n    return 3\n# corrected after failed checks\n')
        retry=self.runner.retry_checks(rid)
        self.assertEqual(retry['id'],rid);self.assertEqual(retry['status'],'retesting')
        self.assertEqual(self.runner.retry_checks(rid)['verificationAttempts'],1)
        with patch.object(self.runner,'agent') as agent,patch.object(self.runner,'publish') as publish,patch.object(self.runner,'execute',wraps=self.runner.execute) as execute:
            self.runner.perform(retry)
        agent.assert_not_called();publish.assert_called_once()
        self.assertTrue(self.runner.items()[0]['testsPassed'])
        self.assertFalse(any('clone' in call.args[1] for call in execute.call_args_list))
        self.assertEqual(self.store.tickets['GA-001']['runId'],rid)

    def test_retry_checks_requires_complete_result_and_unchanged_reservation(self):
        r=self.clarification_run()
        with self.assertRaises(ValueError):self.runner.retry_checks(r['id'])
        self.runner.update(r['id'],status='failed',result={'summary':'Done','addressed':r['tickets'],'unaddressed':[],'notes':''})
        self.store.tickets['GA-001'].pop('runId')
        with self.assertRaises(ValueError):self.runner.retry_checks(r['id'])

    def test_verification_does_not_traverse_other_projects_browser_cache(self):
        r=self.runner.submit('Game',['GA-001'])
        output=self.root/'environment.txt'
        script='import os;from pathlib import Path;Path('+repr(str(output))+').write_text(os.getenv("PLAYWRIGHT_SKIP_BROWSER_GC","unset"))'
        with patch('desk_runs.child_env',return_value={}):
            self.runner.execute(r['id'],[sys.executable,'-c',script],self.root,verification=True)
            self.assertEqual(output.read_text(),'1')
            self.runner.execute(r['id'],[sys.executable,'-c',script],self.root)
            self.assertEqual(output.read_text(),'unset')

    def test_existing_pr_is_reused_after_publication_response_loss(self):
        r,calls=self.full_run(existing=True)
        self.assertEqual(r['status'],'pr_ready',r.get('error'))
        self.assertFalse([c for c in calls if c[1:3]==['pr','create']])

    def clarification_run(self):
        source,remote=self.prepare_remote()
        self.ticket('GA-002',title='Choose reward price')
        r=self.runner.submit('Game',['GA-001','GA-002'])
        real_execute=self.runner.execute
        def execute(rid,args,cwd,**kw):
            if args[0]=='git' and 'clone' in args:args=[*args[:-2],str(remote),args[-1]]
            return real_execute(rid,args,cwd,**kw)
        def agent(rid,clone,prompt,config):
            (clone/'game.py').write_text('def reward():\n    return 3\n')
            write_json(clone/'.playtest-result.json',{'summary':'One fixed; one decision needed','addressed':['GA-001'],'unaddressed':['GA-002'],'notes':'GA-002 — What price should the reward use?'})
        with patch.object(self.runner,'execute',side_effect=execute),patch.object(self.runner,'agent',side_effect=agent):
            self.runner.perform(r)
        return self.runner.items()[0]

    def test_agent_questions_are_reviewable_and_continue_the_same_saved_clone(self):
        r=self.clarification_run();rid=r['id'];clone=self.runner.root/rid/'repo'
        self.assertEqual(r['status'],'needs_review')
        before=(clone/'game.py').read_bytes()
        self.runner.review(rid,{'answers':{'GA-002':'Use 50 coins'},'note':'Keep the existing reward fix.'})
        self.assertEqual(self.runner.items()[0]['status'],'needs_review')
        self.assertEqual((clone/'game.py').read_bytes(),before)
        restarted=Runs(self.store,threading.Event())
        self.assertEqual(restarted.items()[0]['review']['answers']['GA-002'],'Use 50 coins')
        resumed=restarted.continue_run(rid,{'answers':{'GA-002':'Use 50 coins'},'note':'Keep the existing reward fix.'})
        self.assertEqual(resumed['id'],rid);self.assertEqual(resumed['branch'],r['branch'])
        self.assertEqual(len(restarted.items()),1)
        self.assertEqual(restarted.continue_run(rid,{'answers':{'GA-002':'Use 50 coins'}})['id'],rid)
        def agent(rid,folder,prompt,config):
            self.assertEqual(folder,clone);self.assertEqual((folder/'game.py').read_bytes(),before)
            self.assertIn('Use 50 coins',prompt);self.assertIn('Keep the existing reward fix.',prompt)
            write_json(folder/'.playtest-result.json',{'summary':'Both fixed','addressed':['GA-001','GA-002'],'unaddressed':[],'notes':'All requests checked'})
        with patch.object(restarted,'agent',side_effect=agent),patch.object(restarted,'publish') as publish,patch.object(restarted,'execute',wraps=restarted.execute) as execute:
            restarted.perform(resumed)
        self.assertEqual(publish.call_count,1)
        self.assertFalse(any('clone' in call.args[1] for call in execute.call_args_list))
        self.assertTrue(restarted.items()[0]['testsPassed'])
        self.assertEqual(len(restarted.items()[0]['reviewHistory']),1)

    def test_cancelled_notes_can_be_reviewed_without_restarting_or_reserving_until_continue(self):
        r=self.clarification_run();rid=r['id'];self.runner.cancel(rid)
        self.runner.review(rid,{'answers':{'GA-002':'50 coins'}})
        self.store.tickets['GA-001'].update(approvedAt='later reapproval',order=999)
        self.store.save_ticket(self.store.tickets['GA-001'])
        self.assertEqual(self.store.tickets['GA-001']['status'],'approved')
        self.assertEqual(self.runner.items()[0]['status'],'cancelled')
        self.runner.continue_run(rid,{'answers':{'GA-002':'50 coins'}})
        self.assertEqual(self.store.tickets['GA-001']['runId'],rid)
        self.assertEqual(self.store.tickets['GA-002']['status'],'fixing')

    def test_continue_refuses_missing_answers_modified_approvals_and_changed_history(self):
        r=self.clarification_run();rid=r['id'];clone=self.runner.root/rid/'repo'
        with self.assertRaises(ValueError):self.runner.continue_run(rid,{'answers':{}})
        self.runner.cancel(rid)
        self.store.update_ticket('GA-001',{'want':'Different approved request'})
        with self.assertRaises(ValueError):self.runner.continue_run(rid,{'answers':{'GA-002':'50 coins'}})
        original=next(t for t in r['snapshot'] if t['id']=='GA-001')
        self.store.save_ticket({**original,'status':'approved'})
        command(['git','checkout','-b','different'],clone)
        with self.assertRaises(ValueError):self.runner.continue_run(rid,{'answers':{'GA-002':'50 coins'}})
        self.assertEqual(self.store.tickets['GA-001']['status'],'approved')
        self.assertEqual(self.runner.items()[0]['status'],'cancelled')

    def test_merge_requires_original_head_and_required_checks(self):
        r=self.runner.submit('Game',['GA-001']); self.runner.update(r['id'],status='pr_ready',pr='https://github.com/test/game/pull/1',headSha='original')
        for data in [{'state':'OPEN','headRefOid':'changed','statusCheckRollup':[{'conclusion':'SUCCESS'}]},
                     {'state':'OPEN','headRefOid':'original','statusCheckRollup':[]},
                     {'state':'OPEN','headRefOid':'original','statusCheckRollup':[{'conclusion':'FAILURE'}]}]:
            calls=[]
            def cmd(args,*_):
                calls.append(args)
                if args[1]=='api': return json.dumps({'contexts':['Checks']})
                return json.dumps(data)
            with patch('desk_runs.command',side_effect=cmd):
                with self.assertRaises(ValueError): self.runner.merge(r['id'])
            self.assertFalse(any(c[1:3]==['pr','merge'] for c in calls))
        with patch('desk_runs.command',side_effect=[json.dumps({'state':'OPEN','headRefOid':'original','statusCheckRollup':[{'conclusion':'SUCCESS'}]}),json.dumps({'contexts':[]})]):
            with self.assertRaises(ValueError): self.runner.merge(r['id'])

    def test_merged_ticket_requires_human_playtest_then_can_reopen(self):
        r=self.runner.submit('Game',['GA-001']);self.runner.update(r['id'],status='pr_ready',pr='https://github.com/test/game/pull/1',headSha='sha')
        with patch('desk_runs.command',return_value=json.dumps({'state':'MERGED','headRefOid':'sha'})):
            self.runner.refresh(r['id'])
        self.assertEqual(self.store.tickets['GA-001']['status'],'fixed')
        self.runner.verify('GA-001',False)
        self.assertEqual(self.store.tickets['GA-001']['status'],'draft')
        self.assertNotIn('runId',self.store.tickets['GA-001'])

    @unittest.skipUnless(shutil.which('ffmpeg'),'ffmpeg not installed')
    def test_ios_mov_import_keeps_audio_and_deduplicates(self):
        mov=self.root/'iphone.mov'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=120x200:d=1', '-f','lavfi','-i','sine=frequency=440:duration=1','-c:v','libx264','-c:a','aac','-shortest',str(mov)],check=True)
        data=mov.read_bytes()
        one=import_recording(self.store,io.BytesIO(data),len(data),'Game','iphone.mov','iOS')
        two=import_recording(self.store,io.BytesIO(data),len(data),'Game','iphone.mov','iOS')
        self.assertFalse(one['duplicate']);self.assertTrue(two['duplicate']);self.assertEqual(one['file'],two['file'])
        meta=self.store.clips[one['file']]['meta'];self.assertTrue(meta['voice']);self.assertEqual(meta['platform'],'iOS')
        self.assertEqual(meta['pressedAtSecond'],0)
        self.assertTrue((self.store.inbox/one['file']).is_file())

    def test_import_rejects_missing_game_and_bad_size(self):
        for game,size,name in [('',2,'a.mov'),('Game',0,'a.mov'),('Game',751*1024*1024,'a.mov'),('Game',2,'a.txt')]:
            with self.assertRaises(ValueError): import_recording(self.store,io.BytesIO(b'bad'),size,game,name,'iOS')

if __name__=='__main__':unittest.main()
