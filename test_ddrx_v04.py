"""v0.4 BPM metadata and optional experimental mine-to-Shock tests."""
import struct
import unittest
from types import SimpleNamespace
import ddrx_converter as converter
import sm2ddr


class BPMTests(unittest.TestCase):
    def test_min_max_record_order(self):
        data = bytearray(152)
        song = SimpleNamespace(bpms=[(0, 144), (16, 128), (32, 201)])
        outcome = converter.patch_bpm(data, 0, song)
        self.assertEqual(outcome['new'], (201, 128))
        self.assertEqual(struct.unpack_from('<HH', data, 28), (201, 128))
        self.assertEqual(data[:28], bytearray(28))
        self.assertEqual(data[32:], bytearray(120))

    def test_bad_bpm_rejected(self):
        for bpm in [0, -100, 70000, float('nan')]:
            with self.subTest(bpm=bpm), self.assertRaises(converter.DDRXError):
                converter.patch_bpm(bytearray(152), 0, SimpleNamespace(bpms=[(0,bpm)]))


class ShockTests(unittest.TestCase):
    def test_ignore_preserves_original_steps(self):
        steps, tails, mines = sm2ddr.parse_notes('MMMM\n0001', 4, 'ignore')
        self.assertEqual(steps, {2048: 8})
        self.assertEqual(mines, 4)

    def test_all_full_row(self):
        steps, _, _ = sm2ddr.parse_notes('MMMM\n0001', 4, 'all')
        self.assertEqual(steps[0], 15)
        self.assertEqual(steps[2048], 8)

    def test_any_mixed_row_offset_one_sixteenth(self):
        # Beat 1 is at 1024 SSQ units. Shift only mines to beat 0.75.
        steps, _, _ = sm2ddr.parse_notes('0000\nM001\n0000\n0000', 4, 'any')
        self.assertEqual(steps[768], 15)
        self.assertEqual(steps[1024], 8)

    def test_any_mine_only_row(self):
        steps, _, _ = sm2ddr.parse_notes('M000\n0001', 4, 'any')
        self.assertEqual(steps[0], 15)
        self.assertEqual(steps[2048], 8)

    def test_mixed_row_at_zero_skipped(self):
        steps, _, _ = sm2ddr.parse_notes('M001\n0000', 4, 'any')
        self.assertNotIn(-256, steps)
        self.assertEqual(steps[0], 8)

    def test_double_full_row(self):
        steps, _, _ = sm2ddr.parse_notes('MMMMMMMM\n00000001', 8, 'all')
        self.assertEqual(steps[0], 255)

if __name__ == '__main__':
    unittest.main()
