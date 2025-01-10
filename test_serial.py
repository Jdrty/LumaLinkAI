import unittest
from unittest.mock import patch, MagicMock
import glob
import time
from serial_utils import (
    MockSerial, find_arduino_port, init_serial,
    send_frame, send_animation
)

class TestSerialUtils(unittest.TestCase):
    def test_mock_serial_write_and_ack(self):
        mock_ser = MockSerial()
        with patch.object(time, 'sleep', return_value=None):
            # Test write scheduling ack callback for pattern
            mock_ser.write(bytes([0xFF]))
            # Check print output manually if needed, here we ensure no exceptions occur.

    def test_find_arduino_port_single(self):
        with patch('glob.glob', return_value=['/dev/ttyACM0']):
            port = find_arduino_port()
            self.assertEqual(port, '/dev/ttyACM0')

    def test_find_arduino_port_none(self):
        with patch('glob.glob', return_value=[]):
            with self.assertRaises(Exception):
                find_arduino_port()

    def test_find_arduino_port_multiple(self):
        with patch('glob.glob', return_value=['/dev/ttyACM0', '/dev/ttyACM1']):
            with self.assertRaises(Exception):
                find_arduino_port()

    def test_init_serial_mock(self):
        # Force the use of MockSerial
        from serial_utils import USE_MOCK_SERIAL
        USE_MOCK_SERIAL = True
        ser = init_serial()
        self.assertIsInstance(ser, MockSerial)

    def test_send_frame_invalid_length(self):
        # Test send_frame with wrong pattern length
        logger = lambda msg, lv="info": None
        fake_ser = MagicMock()
        # Using a pattern of incorrect length
        send_frame(fake_ser, [0xFF]*7, logger=logger)
        # Expected logger call would log a warning; no serial writes should happen.

    def test_send_animation_invalid_frame_count(self):
        logger = lambda msg, lv="info": None
        fake_ser = MagicMock()
        # Frame count zero should result in logging and no writes.
        send_animation(fake_ser, [], logger=logger)

if __name__ == '__main__':
    unittest.main()