"""Connection uses a GitHub link, readable setup preview, and no executable project code."""
import base64
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'mac'))
from desk_runs import preview_repository, github_slug, suggested_check, Runs
from desk_store import Store, write_json
from desk_games import games


class RepositoryTests(unittest.TestCase):
    def metadata(self,args,*_,**kw):
        if args[:3]==['gh','repo','view']:
            return json.dumps({'nameWithOwner':'Example/orbit','defaultBranchRef':{'name':'main'},'viewerPermission':'WRITE','isArchived':False,'isEmpty':False})
        if args[:2]==['gh','api'] and '/contents/package.json?' in args[2]:
            package={'scripts':{'build':'node build.mjs','qa':'node qa.mjs'},'devDependencies':{'playwright':'1.0.0'}}
            return json.dumps({'content':base64.b64encode(json.dumps(package).encode()).decode()})
        if args[:2]==['gh','api'] and '/contents?' in args[2]:
            return json.dumps([{'type':'file','name':'package.json'},{'type':'file','name':'package-lock.json'}])
        raise AssertionError('Unexpected command: '+repr(args))

    def test_paste_github_link_detects_checks_without_clone_or_execution(self):
        with patch('desk_runs.command',side_effect=self.metadata) as cmd:
            repo=preview_repository('https://github.com/Example/orbit.git/')
        self.assertEqual(repo['github'],'Example/orbit');self.assertEqual(repo['path'],'')
        self.assertEqual(repo['base'],'main');self.assertEqual(repo['checkLabel'],'Build + game QA')
        self.assertEqual(repo['testCommand'],'npm ci && npx playwright install chromium && npm run build && npm run qa')
        self.assertTrue(all(call.args[0][0]=='gh' for call in cmd.call_args_list))

    def test_sources_and_missing_checks_are_not_silently_guessed(self):
        for source in ['https://evil.example/team/repo','https://user:password@github.com/team/repo','https://github.com/team/repo/tree/main','--help/repo','../repo','']:
            with self.subTest(source=source),self.assertRaises(ValueError):github_slug(source)
        self.assertEqual(github_slug('team/repo'),'team/repo')
        self.assertEqual(github_slug('git@github.com:team/repo.git'),'team/repo')
        self.assertEqual(suggested_check({})['testCommand'],'')
        self.assertEqual(suggested_check({'scripts':{'test':'echo "Error: no test specified" && exit 1'}})['testCommand'],'')
        self.assertEqual(suggested_check({'scripts':{'build':'node build.js'}})['checkLabel'],'Build check')

    def test_read_only_access_rejected_and_remote_connection_saved_without_local_clone(self):
        with tempfile.TemporaryDirectory() as temp:
            store=Store(Path(temp));games(store.inbox,['Orbit']);runs=Runs(store,threading.Event())
            with patch('desk_runs.command',side_effect=self.metadata):
                saved=runs.configure('Orbit',{'source':'Example/orbit','provider':'codex','model':'chosen-model','effort':'','autoMerge':False})
            self.assertEqual(saved['testCommand'],'npm ci && npx playwright install chromium && npm run build && npm run qa')
            self.assertEqual(saved['model'],'chosen-model');self.assertFalse(saved['autoMerge']);self.assertFalse(runs.items())
            self.assertEqual(store.state()['repositories']['Orbit']['github'],'Example/orbit')
            def readonly(args,*rest,**kw):
                data=json.loads(self.metadata(args,*rest,**kw))
                if args[:3]==['gh','repo','view']:data['viewerPermission']='READ'
                return json.dumps(data)
            with patch('desk_runs.command',side_effect=readonly),self.assertRaises(ValueError):preview_repository('Example/orbit')

    def test_game_rename_preserves_approval_ids_media_and_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            store=Store(Path(temp));folder=store.inbox/'Launcher';folder.mkdir()
            video=folder/'clip.mp4';video.write_bytes(b'unchanged-media')
            write_json(video.with_suffix('.json'),{'game':'Launcher','pressedAtSecond':10,'voice':True})
            store.set_clip('Launcher/clip.mp4',status='done',meta={'game':'Launcher'},tickets=['LA-001'])
            store.save_ticket({'id':'LA-001','game':'Launcher','clip':'Launcher/clip.mp4','status':'approved','title':'Adjust button'})
            games(store.inbox,['Launcher','Other'])
            result=store.rename_game('Launcher','Orbit')
            self.assertEqual((result['clips'],result['tickets']),(1,1));self.assertEqual(video.read_bytes(),b'unchanged-media')
            self.assertEqual(json.loads(video.with_suffix('.json').read_text())['pressedAtSecond'],10)
            self.assertEqual(store.tickets['LA-001']['status'],'approved');self.assertEqual(store.tickets['LA-001']['game'],'Orbit')
            restarted=Store(store.inbox)
            self.assertEqual(restarted.clips['Launcher/clip.mp4']['meta']['game'],'Orbit')
            self.assertNotIn('Launcher',games(store.inbox));self.assertIn('Orbit',games(store.inbox))
            self.assertTrue(list((store.root/'Game renames').glob('*.json')))

    def test_game_rename_refuses_active_work_and_conflicting_repo_mapping(self):
        with tempfile.TemporaryDirectory() as temp:
            store=Store(Path(temp));games(store.inbox,['Old','New'])
            store.set_clip('Old/clip.mp4',status='working',meta={'game':'Old'})
            with self.assertRaises(ValueError):store.rename_game('Old','New')
            store.set_clip('Old/clip.mp4',status='done')
            write_json(store.root/'repositories.json',{'Old':{'github':'one/game'},'New':{'github':'two/game'}})
            with self.assertRaises(ValueError):store.rename_game('Old','New')
            self.assertEqual(store.clips['Old/clip.mp4']['meta']['game'],'Old')

if __name__=='__main__':unittest.main()
