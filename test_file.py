import unittest
import os
import json
import tempfile
from ui import clean_filename, save_data, load_saved, SAVED_PATTERNS_DIR

class TestFileUtils(unittest.TestCase):
    def test_clean_filename(self):
        name = "test/\\:*?\"<>|file"
        cleaned = clean_filename(name)
        # Check if forbidden characters are removed.
        self.assertNotRegex(cleaned, r'[\\/*?:"<>|]')

    def test_save_and_load_data(self):
        # Create temporary directory to avoid filesystem side-effects.
        with tempfile.TemporaryDirectory() as tmpdir:
            # Temporarily override SAVED_PATTERNS_DIR to use the temp directory.
            original_dir = SAVED_PATTERNS_DIR
            try:
                # Redirect save directory
                ui_module = __import__('ui')
                ui_module.SAVED_PATTERNS_DIR = tmpdir

                data_single = {'type': 'single', 'pattern': [0]*8}
                path = save_data(data_single, name="test_pattern", overwrite=True)
                self.assertTrue(os.path.exists(path))

                loaded = load_saved(path)
                self.assertEqual(loaded, data_single)
            finally:
                ui_module.SAVED_PATTERNS_DIR = original_dir

if __name__ == '__main__':
    unittest.main()