"""v0.3 tests, including optional local resource fixtures."""
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
import ddrx_converter as d
import sm2ddr
import sn2

class TitleTests(unittest.TestCase):
    def test_transliterations_preferred(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'song.sm'
            p.write_text('#TITLE:日本語;\n#TITLETRANSLIT:English Title;\n#ARTIST:作曲家;\n#ARTISTTRANSLIT:Artist Name;\n', encoding='utf-8')
            self.assertEqual(d.display_metadata(p, SimpleNamespace(title='', artist='')),
                             ('English Title', 'Artist Name'))

    def test_missing_transliterations_fall_back(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'song.sm'
            p.write_text('#TITLE:Original Title;\n#ARTIST:Original Artist;\n', encoding='utf-8')
            self.assertEqual(d.display_metadata(p, SimpleNamespace(title='', artist='')),
                             ('Original Title', 'Original Artist'))

    def test_rating_patch_preserves_nonrating_fields(self):
        song = SimpleNamespace(charts=[
            SimpleNamespace(style='dance-single', difficulty='hard', meter=13),
            SimpleNamespace(style='dance-single', difficulty='challenge', meter=18),
            SimpleNamespace(style='dance-double', difficulty='medium', meter=9)])
        program = bytearray(range(152))
        original = program[:]
        change = d.patch_ratings(program, 0, song)
        slots = set(d.RATING_OFFSETS.values())
        self.assertEqual(len(slots), 9)
        self.assertTrue(all(program[i] == original[i] for i in range(152) if i not in slots))
        self.assertEqual(program[37], 0)  # SP Beginner absent
        self.assertEqual(program[38], 0)  # SP Basic absent
        self.assertEqual(program[39], 0)  # SP Difficult absent
        self.assertEqual(program[40], 13) # SP Expert
        self.assertEqual(program[41], 18) # SP Challenge
        self.assertEqual(program[44], 9)  # DP Difficult
        self.assertEqual(program[36], original[36])
        self.assertEqual(program[42], original[42])
        self.assertEqual(program[47], original[47])
        self.assertEqual(change['levels']['dance-single/challenge'], 18)

    def test_stock_dance_celebration_record_layout(self):
        # Native DDR X stock 'dace' values: +36 is a separate byte (4).
        # Difficulty ratings are SP (2,4,8,11,11), DP (5,7,10,10).
        program = bytearray(152)
        program[36:48] = bytes([4, 2, 4, 8, 11, 11, 0, 5, 7, 10, 10, 0])
        song = SimpleNamespace(charts=[
            SimpleNamespace(style='dance-single', difficulty='easy', meter=7),
            SimpleNamespace(style='dance-single', difficulty='medium', meter=11),
            SimpleNamespace(style='dance-single', difficulty='hard', meter=13),
            SimpleNamespace(style='dance-single', difficulty='challenge', meter=16)])
        d.patch_ratings(program, 0, song)
        self.assertEqual(list(program[36:48]), [4, 0, 7, 11, 13, 16, 0, 0, 0, 0, 0, 0])


    def test_native_title_fixtures(self):
        path = Path(__file__).parent / 'ddrx_art_fixture.bin'
        if not path.exists():
            self.skipTest('Local proprietary sample not distributed')
        items = d.split_pack(path.read_bytes())
        for ix in [0, 11, 28, 76]:
            a, b = struct.unpack_from('<II', items[ix]);title = sn2.lz_decompress(items[ix][a:b])
            new = d.render_title_card(title, 'Example Title', 'Example Artist')
            self.assertEqual(len(title), len(new))
            self.assertEqual(new[:4], b'TIM2')
            self.assertNotEqual(new, title)

if __name__ == '__main__':
    unittest.main()
