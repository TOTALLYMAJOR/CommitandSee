"""Real disposable repositories prove content results and read-only boundaries."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import local_insights as insights


@unittest.skipUnless(shutil.which('git'), 'Git is required')
class LocalInsightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='local-insight-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root/'repo'
        self.repo.mkdir()
        self.env = patch.dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
                              GIT_AUTHOR_NAME='Fixture', GIT_COMMITTER_NAME='Fixture',
                              GIT_AUTHOR_EMAIL='fixture@example.invalid', GIT_COMMITTER_EMAIL='fixture@example.invalid')
        self.env.start()
        self.addCleanup(self.env.stop)
        self.git('init', '-b', 'main')
        self.git('config', 'core.autocrlf', 'false')
        self.git('config', 'commit.gpgSign', 'false')
        self.write('story.txt', ''.join(f'line {i}\n' for i in range(24)))
        self.commit('Base')
        self.base = self.git('rev-parse', 'HEAD').strip()

    def git(self, *args, cwd=None):
        result = subprocess.run(['git', *map(str,args)], cwd=cwd or self.repo, capture_output=True,
                                check=True, env=os.environ)
        return result.stdout.decode('utf-8', 'surrogateescape')

    def write(self, name, content):
        path = self.repo/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode() if isinstance(content,str) else content)

    def commit(self, message):
        self.git('add', '.')
        self.git('commit', '-qm', message)

    def source(self, label=None, kind='branch'):
        opts = insights.options(self.repo)
        return next(row['id'] for row in opts['sources'] if row['kind']==kind and (label is None or row['label']==label))

    def target(self, label='heads/main'):
        return next(row['id'] for row in insights.options(self.repo)['targets'] if row['label']==label)

    def scan(self, label='heads/feature', kind='branch'):
        return insights.analyze(self.repo,self.source(label,kind),self.target())

    def hashes(self):
        return {str(p.relative_to(self.root)): ('link',os.readlink(p)) if p.is_symlink() else
                (hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mode)
                for p in self.root.rglob('*') if p.is_file() or p.is_symlink()}

    def feature(self):
        self.git('switch','-c','feature')
        content=(self.repo/'story.txt').read_text()
        self.write('story.txt',content.replace('line 2\n','changed 2\n').replace('line 20\n','changed 20\n'))
        self.commit('Two separated changes')

    def test_squash_and_current_content_are_read_only(self):
        self.feature()
        self.git('switch','main')
        self.git('merge','--squash','feature')
        self.commit('Squashed feature')
        before=self.hashes()
        report=self.scan()
        self.assertEqual(report['summary']['present'],1)
        self.assertEqual(report['files'][0]['preservation'],'matching_saved_version')
        self.assertEqual(self.hashes(),before)
        self.assertNotIn('changed 2',str(report))

    def test_inherited_trace_destinations_cannot_write_during_scan(self):
        self.feature()
        trace_names = ('GIT_TRACE', 'GIT_TRACE_SETUP', 'GIT_TRACE_PACKET',
                       'GIT_TRACE_PACK_ACCESS', 'GIT_TRACE_SHALLOW', 'GIT_TRACE_CURL',
                       'GIT_TRACE2', 'GIT_TRACE2_EVENT', 'GIT_TRACE2_PERF')
        trace_paths = {name: str(self.repo/(name.lower()+'.log')) for name in trace_names}
        before = self.hashes()
        with patch.dict(os.environ, {**trace_paths, 'GIT_CURL_VERBOSE': '1'}):
            opts = insights.options(self.repo)
            source = next(row['id'] for row in opts['sources'] if row['label']=='heads/feature')
            target = next(row['id'] for row in opts['targets'] if row['label']=='heads/main')
            report = insights.analyze(self.repo, source, target)
        self.assertEqual(report['summary']['remaining'], 1)
        self.assertEqual(self.hashes(), before)
        for destination in trace_paths.values():
            self.assertFalse(Path(destination).exists())

    def test_partial_and_reverted_content_are_not_treated_as_integrated(self):
        self.feature()
        self.git('switch','main')
        self.write('story.txt',(self.repo/'story.txt').read_text().replace('line 2\n','changed 2\n'))
        self.commit('Adopt first part')
        self.assertEqual(self.scan()['files'][0]['integration'],'partial')
        self.git('revert','--no-edit','HEAD')
        self.assertEqual(self.scan()['files'][0]['integration'],'remaining')

    def test_cherry_pick_with_unrelated_target_edit(self):
        self.feature()
        sha=self.git('rev-parse','HEAD').strip()
        self.git('switch','main')
        self.write('unrelated.txt','other work\n')
        self.commit('Target advances')
        self.git('cherry-pick',sha)
        self.assertEqual(self.scan()['files'][0]['integration'],'present')

    def test_ancestor_source_reverted_on_target_refuses_empty_success(self):
        self.feature()
        self.git('switch','main')
        self.git('merge','--ff-only','feature')
        self.git('revert','--no-edit','HEAD')
        with self.assertRaises(insights.InsightError) as raised:
            self.scan()
        self.assertEqual(raised.exception.code,'ambiguous_base')
        self.git('switch','feature')
        report=self.scan(None,'worktree')
        self.assertEqual(report['files'],[])
        self.assertTrue(any('does not establish whether earlier committed' in warning for warning in report['warnings']))

    def test_working_and_staged_versions_are_independent_and_unchanged(self):
        original=(self.repo/'story.txt').read_bytes()
        self.write('story.txt','unique staged version\n')
        self.git('add','story.txt')
        self.write('story.txt',original)
        self.write('new.txt','not yet committed\n')
        before=self.hashes()
        index=self.scan(None,'index')
        work=self.scan(None,'worktree')
        self.assertEqual([r['path'] for r in index['files']],['story.txt'])
        self.assertEqual(index['files'][0]['preservation'],'no_matching_saved_version')
        self.assertEqual([r['path'] for r in work['files']],['new.txt'])
        self.assertEqual(self.hashes(),before)

    def test_stash_includes_saved_untracked_files(self):
        self.write('story.txt','stashed change\n')
        self.write('new.txt','untracked saved content\n')
        self.git('stash','push','-u','-m','Saved')
        before=self.hashes()
        report=self.scan(None,'stash')
        self.assertEqual({r['path'] for r in report['files']},{'story.txt','new.txt'})
        self.assertTrue(all(r['preservation']=='matching_saved_version' for r in report['files']))
        self.assertEqual(self.hashes(),before)

    def test_stash_staged_version_is_a_source_and_a_saved_copy(self):
        original=(self.repo/'story.txt').read_bytes()
        self.write('story.txt','staged version A\n')
        self.git('add','story.txt')
        self.write('story.txt',original)
        self.git('stash','push','-m','Staged only')
        self.assertEqual(self.scan(None,'stash')['files'],[])
        index=self.scan(None,'stash_index')
        self.assertEqual(index['files'][0]['integration'],'remaining')
        self.write('story.txt','staged version A\n')
        before=self.hashes()
        report=self.scan(None,'worktree')
        self.assertEqual(report['files'][0]['preservation'],'matching_saved_version')
        self.assertTrue(any('staged files' in label for label in report['files'][0]['saved_copies']))
        self.assertEqual(self.hashes(),before)

    def test_saved_copy_found_in_different_path_and_reflog(self):
        self.git('switch','-c','old')
        self.write('old.txt','preserved bytes\n')
        self.commit('Old work')
        self.git('switch','main')
        self.git('branch','-D','old')
        self.write('new.txt','preserved bytes\n')
        report=self.scan(None,'worktree')
        self.assertEqual(report['files'][0]['preservation'],'matching_saved_version')
        self.assertTrue(any(label.startswith('Reflog ') for label in report['files'][0]['saved_copies']))

    def test_saved_search_truncation_never_claims_absence(self):
        self.write('new.txt','only in working files\n')
        source,target=self.source(None,'worktree'),self.target()
        with patch.object(insights,'MAX_REFLOG',0):
            report=insights.analyze(self.repo,source,target)
        self.assertTrue(report['coverage']['saved_search_limited'])
        self.assertEqual(report['files'][0]['preservation'],'unknown')

    def test_mode_only_change_does_not_match_saved_bytes_in_another_mode(self):
        self.git('update-index','--chmod=+x','story.txt')
        before=self.hashes()
        report=self.scan(None,'index')
        self.assertEqual(report['files'][0]['integration'],'remaining')
        self.assertEqual(report['files'][0]['preservation'],'no_matching_saved_version')
        self.assertEqual(self.hashes(),before)

    def test_ambiguous_repeated_blocks_remain_uncertain(self):
        before=('100644','a'*40); desired=('100644','b'*40); target=('100644','c'*40)
        from unittest.mock import Mock
        scan=Mock()
        scan.blob.side_effect=[b'x\n'*12+b'old\n'+b'x\n'*12,
                               b'x\n'*12+b'new\n'+b'x\n'*12,
                               (b'x\n'*12+b'new\n'+b'x\n'*12)*2]
        state,_=insights._classify(scan,before,desired,target)
        self.assertEqual(state,'uncertain')

    def test_binary_mode_add_delete_and_newline_names(self):
        self.write('remove.txt','remove me\n')
        self.commit('Second base')
        self.git('switch','-c','feature')
        self.write('binary.dat',b'a\0b')
        self.write('add.txt','new\n')
        (self.repo/'remove.txt').unlink()
        self.git('update-index','--chmod=+x','story.txt')
        self.commit('Kinds')
        self.git('switch','main')
        rows={row['path']:row for row in self.scan()['files']}
        self.assertEqual(rows['binary.dat']['integration'],'uncertain')
        self.assertEqual(rows['add.txt']['integration'],'remaining')
        self.assertEqual(rows['remove.txt']['integration'],'remaining')
        if os.name=='posix':
            self.write('line\nname.txt','new file\n')
            self.assertIn('line\nname.txt',[r['path'] for r in self.scan(None,'worktree')['files']])

    def test_exclusions_ignored_files_and_symlinks(self):
        self.write('.gitignore','ignored.txt\n')
        self.commit('Ignore')
        self.write('ignored.txt','private ignored content\n')
        self.write('exclude.txt','excluded content\n')
        outside=self.root/'outside.txt'; outside.write_text('must not read')
        try:
            (self.repo/'link.txt').symlink_to(outside)
        except OSError:
            self.skipTest('Symlink privilege unavailable')
        source,target=self.source(None,'worktree'),self.target()
        before=self.hashes()
        report=insights.analyze(self.repo,source,target,exclude_globs=['exclude.txt'])
        self.assertEqual([r['path'] for r in report['files']],['link.txt'])
        self.assertEqual(report['files'][0]['integration'],'uncertain')
        self.assertEqual(self.hashes(),before)

    @unittest.skipUnless(os.name=='posix','POSIX shell tripwire')
    def test_filters_hooks_external_diff_and_replacements_do_not_execute(self):
        marker=self.root/'executed'
        command='touch '+str(marker)
        self.git('config','filter.trip.clean',command)
        self.git('config','filter.trip.process',command)
        self.git('config','core.fsmonitor',command)
        self.git('config','diff.external',command)
        self.write('.gitattributes','*.txt filter=trip diff=trip\n')
        self.git('config','diff.trip.textconv',command)
        self.write('story.txt','new bytes\n')
        before=self.hashes()
        report=self.scan(None,'worktree')
        self.assertTrue(report['files'])
        self.assertFalse(marker.exists())
        self.assertEqual(self.hashes(),before)

    def test_unknown_selections_and_budget_fail_closed(self):
        with self.assertRaises(insights.InsightError):
            insights.analyze(self.repo,'../../outside','--help')
        self.write('new.txt','new\n')
        source,target=self.source(None,'worktree'),self.target()
        with patch.object(insights,'MAX_COMMANDS',2):
            with self.assertRaises(insights.InsightError) as raised:
                insights.analyze(self.repo,source,target)
        self.assertEqual(raised.exception.code,'budget_exceeded')
        with self.assertRaises(insights.InsightError) as raised:
            insights.options(self.repo,cancel_check=lambda:True)
        self.assertEqual(raised.exception.code,'cancelled')

    def test_working_file_change_during_scan_discards_result(self):
        self.write('new.txt','first\n')
        source,target=self.source(None,'worktree'),self.target()
        original=insights.Scan.working
        count=0
        def changed(scan,src):
            nonlocal count
            result=original(scan,src)
            count+=1
            if count==1:
                self.write('new.txt','second\n')
            return result
        with patch.object(insights.Scan,'working',changed):
            with self.assertRaises(insights.InsightError) as raised:
                insights.analyze(self.repo,source,target)
        self.assertEqual(raised.exception.code,'changed')

    def test_ref_change_during_scan_discards_result(self):
        self.feature()
        source,target=self.source('heads/feature'),self.target()
        original=insights.Scan.inventory
        count=0
        def changed(scan):
            nonlocal count
            result=original(scan)
            count+=1
            if count==1:
                self.git('update-ref','refs/heads/main',self.git('rev-parse','feature').strip())
            return result
        with patch.object(insights.Scan,'inventory',changed):
            with self.assertRaises(insights.InsightError) as raised:
                insights.analyze(self.repo,source,target)
        self.assertEqual(raised.exception.code,'changed')

    def test_reflog_expiry_during_saved_copy_scan_discards_result(self):
        self.write('story.txt','recoverable version\n')
        self.commit('Recoverable')
        orphan=self.git('rev-parse','HEAD').strip()
        self.git('reset','--hard',self.base)
        self.write('story.txt','recoverable version\n')
        source,target=self.source(None,'worktree'),self.target()
        original=insights.Scan.tree
        expired=False
        def expire(scan,oid):
            nonlocal expired
            result=original(scan,oid)
            if oid==orphan and not expired:
                expired=True
                self.git('reflog','expire','--expire=now','--all')
            return result
        with patch.object(insights.Scan,'tree',expire):
            with self.assertRaises(insights.InsightError) as raised:
                insights.analyze(self.repo,source,target)
        self.assertTrue(expired)
        self.assertEqual(raised.exception.code,'changed')

    def test_capability_preflight_obeys_cancellation_and_budget(self):
        with patch.object(insights,'_run') as command:
            with self.assertRaises(insights.InsightError):
                insights.options(self.repo,cancel_check=lambda:True)
            command.assert_not_called()
        with patch.object(insights,'MAX_SECONDS',0),patch.object(insights,'_run') as command:
            with self.assertRaises(insights.InsightError):
                insights.options(self.repo)
            command.assert_not_called()

    def test_sparse_missing_file_is_unknown_not_a_deletion(self):
        self.git('update-index','--skip-worktree','story.txt')
        (self.repo/'story.txt').unlink()
        report=self.scan(None,'worktree')
        self.assertEqual(report['files'][0]['integration'],'uncertain')
        self.assertEqual(report['files'][0]['preservation'],'unknown')

    @unittest.skipUnless(os.name=='posix','POSIX nofollow directory fixture')
    def test_root_ancestor_swap_cannot_read_outside_bytes(self):
        parent=self.root/'nested'
        root=parent/'repo'
        root.mkdir(parents=True)
        (root/'file.txt').write_text('inside')
        outside=self.root/'outside'
        (outside/'repo').mkdir(parents=True)
        (outside/'repo'/'file.txt').write_text('outside sentinel')
        original=os.open
        swapped=False
        def swapped_open(path,*args,**kwargs):
            nonlocal swapped
            if path=='nested' and not swapped:
                swapped=True
                parent.rename(self.root/'original-parent')
                parent.symlink_to(outside,target_is_directory=True)
            return original(path,*args,**kwargs)
        with patch.object(insights.os,'open',swapped_open):
            payload,kind=insights._read_regular(root,'file.txt',100)
        self.assertIsNone(payload)
        self.assertEqual(kind,'unsupported')

    def test_oversized_and_output_time_budgets_fail_closed(self):
        self.write('large.txt','x'*100)
        source,target=self.source(None,'worktree'),self.target()
        with patch.object(insights,'MAX_BLOB',64):
            report=insights.analyze(self.repo,source,target)
        large=next(r for r in report['files'] if r['path']=='large.txt')
        self.assertEqual(large['integration'],'uncertain')
        self.assertEqual(large['preservation'],'unknown')
        for setting,value in [('MAX_SECONDS',0),('MAX_BYTES',1),('MAX_FILES',1)]:
            with self.subTest(setting=setting),patch.object(insights,setting,value):
                with self.assertRaises(insights.InsightError):
                    insights.analyze(self.repo,source,target)

    def test_worktree_redirection_is_rejected(self):
        outside=self.root/'outside'
        outside.mkdir()
        self.git('config','core.worktree',str(outside))
        with self.assertRaises(insights.InsightError) as raised:
            insights.options(self.repo)
        self.assertEqual(raised.exception.code,'unsafe_path')

    def test_shallow_history_is_not_complete_evidence(self):
        other=self.root/'shallow'
        self.git('clone','--depth=1','file://'+str(self.repo),str(other))
        opts=insights.options(other)
        with self.assertRaises(insights.InsightError) as raised:
            insights.analyze(other,opts['sources'][0]['id'],opts['targets'][0]['id'])
        self.assertEqual(raised.exception.code,'incomplete_history')


if __name__=='__main__':
    unittest.main()
