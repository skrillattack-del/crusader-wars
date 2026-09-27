"""Tests for the options ledger: schema validation, checksum, discovery, rails."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import config

REPO_ROOT = HERE.parents[1]
SCHEMA_PATH = REPO_ROOT / 'schemas' / 'config.schema.json'
# The schema's defaults, not the live config/cw2_config.json: players edit that one.
DEFAULTS = {key: spec['default'] for key, spec in
            json.loads(SCHEMA_PATH.read_text(encoding='utf-8'))['properties'].items()}


class TempBase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def write_schema(self):
        (self.base / 'schemas').mkdir(exist_ok=True)
        shutil.copy2(SCHEMA_PATH, self.base / 'schemas' / SCHEMA_PATH.name)
        return json.loads(SCHEMA_PATH.read_text(encoding='utf-8'))

    def write_ledger(self, doc=None):
        (self.base / 'config').mkdir(exist_ok=True)
        path = self.base / 'config' / 'cw2_config.json'
        path.write_text(json.dumps(DEFAULTS if doc is None else doc), encoding='utf-8')
        return path


class ValidateTests(TempBase):
    def test_defaults_document_is_valid(self):
        schema = self.write_schema()
        config.validate(schema, DEFAULTS)

    def test_bad_enum_wrong_type_unknown_key_and_bounds_are_rejected(self):
        schema = self.write_schema()
        cases = [
            ({'show_mode': 'arcade'}, 'show_mode'),
            ({'army_scale_factor': 'big'}, 'army_scale_factor'),
            ({'army_scale_factor': 0}, 'exclusiveMinimum'),
            ({'army_scale_factor': 10.5}, 'maximum'),
            ({'auto_battle_report': 'yes'}, 'auto_battle_report'),
            ({'army_scale_factor': True}, 'boolean'),
            ({'cheat_mode': True}, 'unknown key'),
            ({}, 'missing'),
        ]
        for doc, fragment in cases:
            with self.assertRaises(ValueError) as ctx:
                config.validate(schema, doc)
            self.assertIn(fragment, str(ctx.exception), doc)

    def test_violations_are_listed_together(self):
        schema = self.write_schema()
        with self.assertRaises(ValueError) as ctx:
            config.validate(schema, {'show_mode': 'arcade', 'domain_focus': 'qin'})
        self.assertIn('show_mode', str(ctx.exception))
        self.assertIn('domain_focus', str(ctx.exception))

    def test_bool_is_not_a_number(self):
        schema = {'type': 'number'}
        for doc in (True, False):
            with self.assertRaises(ValueError):
                config.validate(schema, doc)


class EffectiveTests(TempBase):
    def test_missing_keys_fill_from_schema_defaults(self):
        schema = self.write_schema()
        merged = config.effective(schema, {'domain_focus': 'shu'})
        self.assertEqual(merged['domain_focus'], 'shu')
        self.assertEqual(merged['show_mode'], 'dramatic')
        self.assertEqual(merged['army_scale_factor'], 1.0)
        self.assertEqual(merged['cut_3d_voice'], True)  # reserved, still tracked

    def test_checksum_is_canonical(self):
        a = config.checksum({'b': 1, 'a': 2})
        b = config.checksum({'a': 2, 'b': 1})
        self.assertEqual(a, b)
        self.assertNotEqual(a, config.checksum({'a': 2, 'b': 3}))
        self.assertEqual(len(a), 64)


class LedgerTests(TempBase):
    def test_first_run_seeds_defaults_beside_base(self):
        self.write_schema()
        ledger = config.find_ledger(self.base)
        self.assertEqual(ledger, self.base / 'config' / 'cw2_config.json')
        self.assertEqual(json.loads(ledger.read_text(encoding='utf-8')), DEFAULTS)

    def test_load_returns_config_path_and_checksum(self):
        self.write_schema()
        self.write_ledger({'show_mode': 'minimal'})
        cfg, path, sha = config.load(self.base)
        self.assertEqual(cfg['show_mode'], 'minimal')
        self.assertEqual(cfg['domain_focus'], 'custom')  # default filled
        self.assertEqual(path, self.base / 'config' / 'cw2_config.json')
        self.assertEqual(sha, config.checksum(cfg))

    def test_load_rejects_an_invalid_ledger(self):
        self.write_schema()
        self.write_ledger({'domain_focus': 'qin'})
        with self.assertRaises(ValueError) as ctx:
            config.load(self.base)
        self.assertIn('domain_focus', str(ctx.exception))

    def test_load_without_schema_raises(self):
        self.write_ledger()
        with self.assertRaises(ValueError):
            config.load(self.base)

    def test_save_merges_validates_and_writes_atomically(self):
        self.write_schema()
        self.write_ledger()
        cfg, path, sha = config.save(self.base, {'army_scale_factor': 2.5})
        self.assertEqual(cfg['army_scale_factor'], 2.5)
        self.assertEqual(cfg['show_mode'], 'dramatic')
        self.assertEqual(sha, config.checksum(cfg))
        self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['army_scale_factor'], 2.5)
        with self.assertRaises(ValueError):
            config.save(self.base, {'army_scale_factor': -1})
        self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['army_scale_factor'], 2.5)

    def test_reserved_cut_3d_voice_round_trips_but_nothing_consumes_it(self):
        self.write_schema()
        self.write_ledger()
        cfg, _, _ = config.save(self.base, {'cut_3d_voice': False})
        self.assertFalse(cfg['cut_3d_voice'])
        for source in (HERE / 'bridge.py', HERE / 'ui' / 'index.html',
                       HERE.parents[0] / 'battle_math' / 'roll.py'):
            code = self._strip_comments(source.read_text(encoding='utf-8'))
            self.assertNotIn('cut_3d_voice', code,
                             f'{source.name} must not act on the reserved key')

    @staticmethod
    def _strip_comments(text):
        import re
        text = re.sub(r'<!--.*?-->', '', text, flags=re.S)
        text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
        return re.sub(r'(?m)(^|\s)//[^\n]*', r'\1', text)


class SlotsTests(TempBase):
    def test_empty_registry_is_injective(self):
        self.assertEqual(config.assert_injective({'mappings': []}), [])

    def test_duplicate_slot_or_character_violates_both_directions(self):
        registry = {'mappings': [
            {'ck3_character_id': 1, 'slot': 'hero_1'},
            {'ck3_character_id': 2, 'slot': 'hero_1'},
            {'ck3_character_id': 2, 'slot': 'hero_2'},
        ]}
        with self.assertRaises(ValueError) as ctx:
            config.assert_injective(registry)
        message = str(ctx.exception)
        self.assertIn('hero_1', message)
        self.assertIn('character 2', message)
        self.assertEqual(len(config.assert_injective(registry, strict=False)), 2)

    def test_check_slots_discovers_the_registry(self):
        self.assertEqual(config.check_slots(self.base), ([], None))
        registry = self.write_ledger()
        registry.with_name('slots.registry.json').write_text(
            json.dumps({'mappings': [{'ck3_character_id': 7, 'slot': 'hero_1'}]}))
        violations, path = config.check_slots(self.base)
        self.assertEqual((violations, path), ([], registry.with_name('slots.registry.json')))


class ScreenshotSeamTests(TempBase):
    def test_flag_is_written_only_when_enabled(self):
        run = self.base / 'run'
        self.assertIsNone(config.maybe_request_screenshots(run, False))
        self.assertFalse(run.exists())
        flag = config.maybe_request_screenshots(run, True)
        self.assertTrue(flag.is_file())
        self.assertIn('no capture backend', flag.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
