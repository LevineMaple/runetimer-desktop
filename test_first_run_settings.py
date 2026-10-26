"""Exercise production settings seeding without launching UI or touching user data."""
import ast
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


class FirstRunSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / 'home'
        self.data = Path(self.temp.name) / 'data'
        self.legacy = self.home / 'AppData/Roaming/MapleTimerAutoDetect'
        self.legacy.mkdir(parents=True)
        # Execute the actual function alone: importing pc_app starts settings and DPI setup.
        source = Path(__file__).with_name('pc_app.py')
        tree = ast.parse(source.read_text(encoding='utf-8-sig'))
        function = next(node for node in tree.body
                        if isinstance(node, ast.FunctionDef) and node.name == 'seed_settings')
        module = ast.Module(body=[function], type_ignores=[])
        namespace = {'DATA': self.data, 'Path': Path, 'json': json}
        exec(compile(module, str(source), 'exec'), namespace)
        self.seed = namespace['seed_settings']

    def run_seed(self):
        with patch.object(Path, 'home', return_value=self.home):
            self.seed()

    def assert_both_profiles_off(self):
        for name in ('settings.json', 'settings-low.json'):
            with self.subTest(profile=name):
                settings = json.loads((self.data / name).read_text(encoding='utf-8'))
                self.assertIs(settings['booster_mode_enabled'], False)

    def test_fresh_install_starts_off_in_both_profiles(self):
        self.run_seed()
        self.assert_both_profiles_off()

    def test_legacy_enabled_setting_does_not_enable_first_run(self):
        for name in ('settings.json', 'settings-low.json'):
            (self.legacy / name).write_text(
                json.dumps({'booster_mode_enabled': True}), encoding='utf-8')
        self.run_seed()
        self.assert_both_profiles_off()

    def test_legacy_high_profile_fallback_also_starts_off(self):
        (self.legacy / 'settings.json').write_text(
            json.dumps({'booster_mode_enabled': True}), encoding='utf-8')
        self.run_seed()
        self.assert_both_profiles_off()

    def test_later_launch_preserves_users_enabled_setting(self):
        self.run_seed()
        originals = {}
        for name in ('settings.json', 'settings-low.json'):
            target = self.data / name
            settings = json.loads(target.read_text(encoding='utf-8'))
            settings['booster_mode_enabled'] = True
            target.write_text(json.dumps(settings), encoding='utf-8')
            originals[name] = target.read_bytes()
        self.run_seed()
        for name, original in originals.items():
            with self.subTest(profile=name):
                self.assertEqual((self.data / name).read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
