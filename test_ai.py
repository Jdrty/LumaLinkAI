import unittest
from unittest.mock import patch
from ai_utils import (
    parse_response, simple_pattern, simple_animation,
    visualize_pattern, is_symmetric, mirror_pattern, mirror_animation
)

class TestAIUtils(unittest.TestCase):
    def test_parse_response_valid(self):
        raw = (
            "B10000001\nB01000010\nB00100100\nB00011000\n"
            "B00011000\nB00100100\nB01000010\nB10000001\n"
        )
        expected = [129, 66, 36, 24, 24, 36, 66, 129]
        self.assertEqual(parse_response(raw), expected)

    def test_parse_response_invalid(self):
        # Less than 8 lines provided
        raw = "B10000001\nB01000010\n"
        self.assertIsNone(parse_response(raw))
    
    def test_simple_pattern(self):
        pattern = simple_pattern()
        self.assertEqual(len(pattern), 8)
        # Check known symmetric pattern values.
        self.assertEqual(pattern[0], 0b10000001)

    def test_simple_animation(self):
        frames = simple_animation(3)
        self.assertEqual(len(frames), 3)
        for frame in frames:
            self.assertEqual(len(frame), 8)

    def test_visualize_pattern(self):
        pattern = [0b10101010] * 8
        visual = visualize_pattern(pattern)
        expected_line = "█•█•█•█•\n"  # Based on pattern bits
        self.assertTrue(expected_line in visual)

    def test_is_symmetric_true(self):
        pattern = simple_pattern()
        self.assertTrue(is_symmetric(pattern))

    def test_is_symmetric_false(self):
        pattern = [0b10000000] * 8  # Not symmetric horizontally
        self.assertFalse(is_symmetric(pattern))

    def test_mirror_pattern_horizontal(self):
        pattern = [0b10000001] * 8
        mirrored = mirror_pattern(pattern, horizontal=True)
        self.assertEqual(mirrored, pattern)  # same because it's symmetric horizontally

    def test_mirror_pattern_vertical(self):
        pattern = list(reversed(simple_pattern()))
        mirrored = mirror_pattern(simple_pattern(), horizontal=False)
        self.assertEqual(mirrored, pattern)

    def test_mirror_animation(self):
        frames = simple_animation(2)
        mirrored_frames = mirror_animation(frames, horizontal=True)
        self.assertEqual(len(mirrored_frames), 2)
        for original, mirrored in zip(frames, mirrored_frames):
            self.assertEqual(mirrored, mirror_pattern(original, horizontal=True))

if __name__ == '__main__':
    unittest.main()