"""DDR X converter regression checks against extracted game resources, if present."""
import json
import struct
import unittest
import zipfile
from pathlib import Path
import ddrx_converter as d
import sn2

ROOT = Path(__file__).resolve().parent


class SlotTests(unittest.TestCase):
    def test_code_table_reference(self):
        p = ROOT / 'SLUS_217.67'
        if not p.exists():
            self.skipTest('Local PS2 executable sample not installed')
        r = d.slot_records(p.read_bytes())
        self.assertEqual(len(r), 77)
        self.assertEqual(r['dace']['index'], 28)
        self.assertEqual(r['thli']['index'], 0)
        self.assertEqual(r['plur']['index'], 76)
        self.assertEqual(len({x['index'] for x in r.values()}), 77)

    def test_wrong_elf_fails(self):
        with self.assertRaises(d.DDRXError):
            d.slot_records(b'foo' * 100)

    def test_invalid_pack(self):
        with self.assertRaises(d.DDRXError):
            d.split_pack(b'123')

    def test_pack_replacement_index(self):
        sample = struct.pack('<III', 12, 16, 20) + b'aaaa' + b'bbbb' + b'cccc'
        parts = d.split_pack(sample, 3)
        self.assertEqual(parts, [b'aaaa', b'bbbb', b'cccc'])

    def test_manifest_validation(self):
        class Mock:
            slot_map = {'dace': {'index': 28}, 'bloo': {'index': 27}}
        p = ROOT / 'ddrx_converter.py'
        with self.assertRaises(d.DDRXError):
            d.normalize_jobs([{'slot':'dace','song':str(p)}, {'slot':'dace','song':str(p)}], Mock())
        result = d.normalize_jobs([{'slot':'dace','song':str(p)}], Mock())
        self.assertEqual(result[0]['slot'],'dace')


if __name__ == '__main__':
    unittest.main()

class ArtworkTemplateTests(unittest.TestCase):
    def test_empty_placeholder_is_not_banner(self):
        blank = b'TIM2' + bytes(21760 - 4)
        self.assertFalse(d.banner_template_valid(blank))

    def test_bad_template_is_preserved_with_warning(self):
        # A malformed banner alone no longer suppresses title-card generation.
        import tempfile
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'test.sm'
            p.write_text('#TITLE:Test;\n#ARTIST:Artist;\n', encoding='utf-8')
            title = b'TIM2' + bytes(128)
            blank = b'TIM2' + bytes(1024)
            a = sn2.lz_compress(title)
            b = sn2.lz_compress(blank)
            stock = struct.pack('<II', 8, 8 + len(a)) + a + b
            warnings = []
            result = d.build_art_entry(stock, SimpleNamespace(title='Test', artist='Artist'),
                                       p, warnings, slot='test')
            self.assertEqual(result, stock)
            self.assertEqual(len(warnings), 2)

    def test_original_ddrx_art_pack_template_variants(self):
        archive = ROOT / 'ddrx_art_fixture.bin'
        if not archive.exists():
            self.skipTest('Local proprietary artwork fixture is not distributed')
        data = d.split_pack(archive.read_bytes())
        flags = []
        for entry in data:
            a, b = struct.unpack_from('<II', entry)
            flags.append(d.banner_template_valid(sn2.lz_decompress(entry[b:])))
        self.assertEqual(flags.count(False), 1)
        self.assertEqual(flags.index(False), 11)
