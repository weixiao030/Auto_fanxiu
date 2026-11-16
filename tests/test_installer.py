from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fanxiu_assistant import install as installer


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.game=self.root/'游戏 Library/凡修'
        self.game.mkdir(parents=True)
        self.runtime=self.root/'用户 profile/runtime'
        self.backups=self.root/'用户 profile/backups'
        payload=b'fixture game, never executed'
        (self.game/'run.exe').write_bytes(payload)
        (self.game/'release-manifest.json').write_text('{"version":"fixture"}',encoding='utf-8')
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        for name,value in [('RUNTIME',self.runtime),('BACKUPS',self.backups),('ROOT',self.root/'persistent resources')]:
            self.stack.enter_context(patch.object(installer,name,value))
        self.stack.enter_context(patch.object(installer,'game_folder',return_value=self.game))
        self.stack.enter_context(patch.object(installer,'process_images',return_value=[]))

    def test_install_preserves_config_key_and_backup(self):
        cfg=self.game/'override.cfg'
        original='[display]\nwindow/size=123\n; 自定义设置\n'
        cfg.write_text(original,encoding='utf-8')
        key='ab'*32
        (self.game/'fanxiu-assistant.key').write_text(key,encoding='utf-8')
        installer.install()
        changed=cfg.read_text(encoding='utf-8')
        self.assertIn(original.strip(),changed)
        self.assertIn((self.root/'persistent resources/bridge/loader.gd').as_posix(),changed)
        self.assertEqual((self.runtime/'bridge.key').read_text(),key)
        self.assertTrue(any(p.read_text(encoding='utf-8')==original for p in self.backups.rglob('override.cfg')))

    def test_repeat_install_does_not_duplicate_or_rotate(self):
        installer.install()
        before=(self.game/'override.cfg').read_bytes()
        key=(self.runtime/'bridge.key').read_bytes()
        backups=list(self.backups.rglob('manifest.json'))
        installer.install()
        self.assertEqual(before,(self.game/'override.cfg').read_bytes())
        self.assertEqual(key,(self.runtime/'bridge.key').read_bytes())
        self.assertEqual(backups,list(self.backups.rglob('manifest.json')))

    def test_changed_executable_and_unknown_version_allow_install(self):
        cfg=self.game/'override.cfg';cfg.write_text(';keep',encoding='utf-8')
        (self.game/'run.exe').write_bytes(b'changed')
        installer.install()
        self.assertIn(';keep',cfg.read_text())
        self.assertIn(installer.MARK_BEGIN,cfg.read_text())
        (self.game/'release-manifest.json').write_text('{"version":"future"}',encoding='utf-8')
        installer.install()
        self.assertEqual(cfg.read_text().count(installer.MARK_BEGIN),1)

    def test_missing_or_invalid_version_metadata_does_not_block(self):
        for content in ('not json', '[]', '{}'):
            (self.game/'release-manifest.json').write_text(content,encoding='utf-8')
            self.assertTrue(installer.install()['installed'])

    def test_incomplete_marker_is_not_overwritten(self):
        cfg=self.game/'override.cfg';cfg.write_text(installer.MARK_BEGIN,encoding='utf-8')
        with self.assertRaises(RuntimeError):installer.install()
        self.assertEqual(cfg.read_text(),installer.MARK_BEGIN)

    def test_uninstall_removes_only_marker_and_keeps_backup(self):
        cfg=self.game/'override.cfg'
        cfg.write_text('[display]\nwindow/size=123\n',encoding='utf-8')
        installer.install()
        cfg.write_text(cfg.read_text(encoding='utf-8')+'\n[extra]\nkeep=true\n',encoding='utf-8')
        before=cfg.read_bytes()
        installer.uninstall()
        after=cfg.read_text(encoding='utf-8')
        self.assertIn('window/size=123',after)
        self.assertIn('keep=true',after)
        self.assertNotIn(installer.MARK_BEGIN,after)
        self.assertTrue(any(p.read_bytes()==before for p in self.backups.rglob('override.cfg')))


if __name__=='__main__':unittest.main()
