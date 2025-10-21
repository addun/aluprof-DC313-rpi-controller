#!/usr/bin/env python3
"""
Test suite for RemoteController sleep detection logic.
Run from project root: python -m tests.test_remote_controller
"""

import unittest
from unittest.mock import Mock, patch
import time
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Import the actual classes
from src.remote_controller import RemoteController
from src.config import Config


class TestRemoteControllerSleepLogic(unittest.TestCase):
    """Test cases for RemoteController sleep detection logic."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_gpio = Mock()
        self.config = Config()
        self.mock_state = Mock()
        
        # Set up config values for predictable testing
        self.config.GO_TO_SLEEP_DELAY_SEC = 8.0
        self.config.SLEEP_THRESHOLD_SEC = 1.0
        self.config.WAKE_UP_DELAY_SEC = 0.5
        
        # Create the actual RemoteController instance
        self.controller = RemoteController(self.mock_gpio, self.config, self.mock_state)

    def test_device_starts_asleep(self):
        """Test that device is considered asleep when last_action_time is 0."""
        # Device starts with last_action_time = 0
        self.assertEqual(self.controller.last_action_time, 0)
        self.assertTrue(self.controller._is_device_asleep())

    @patch('time.time')
    def test_zone_1_device_awake_immediate_false(self, mock_time):
        """Test Zone 1 (0-7s): Device awake, return False immediately."""
        base_time = 1000.0
        self.controller.last_action_time = base_time
        
        # Test various points in the awake zone (0-7s)
        test_cases = [
            (base_time + 1.0, "1 second"),
            (base_time + 3.5, "3.5 seconds"), 
            (base_time + 6.9, "6.9 seconds"),
        ]
        
        for current_time, description in test_cases:
            with self.subTest(time_elapsed=description):
                mock_time.return_value = current_time
                
                start = time.perf_counter()
                result = self.controller._is_device_asleep()
                duration = time.perf_counter() - start
                
                self.assertFalse(result, f"Should be awake at {description}")
                self.assertLess(duration, 0.1, f"Should not wait at {description}")

    @patch('time.time')
    @patch('time.sleep')
    def test_zone_2_uncertain_zone_wait_then_true(self, mock_sleep, mock_time):
        """Test Zone 2 (7-9s): Uncertain zone, wait then return True."""
        base_time = 1000.0
        self.controller.last_action_time = base_time
        
        test_cases = [
            (base_time + 7.0, 2.0, "exactly 7s (start of uncertain zone)"),
            (base_time + 7.3, 1.7, "7.3s (early uncertain zone)"),
            (base_time + 8.0, 1.0, "exactly 8s (device starts sleeping)"),
            (base_time + 8.2, 0.8, "8.2s (device sleeping, not at threshold)"),
            (base_time + 8.9, 0.1, "8.9s (almost at threshold)"),
        ]
        
        for current_time, expected_wait, description in test_cases:
            with self.subTest(scenario=description):
                mock_time.return_value = current_time
                mock_sleep.reset_mock()
                
                result = self.controller._is_device_asleep()
                
                self.assertTrue(result, f"Should be asleep after waiting at {description}")
                mock_sleep.assert_called_once()
                
                actual_wait = mock_sleep.call_args[0][0]
                self.assertAlmostEqual(
                    actual_wait, expected_wait, delta=0.1,
                    msg=f"Wait time should be ~{expected_wait}s at {description}, got {actual_wait}s"
                )

    @patch('time.time')
    def test_zone_3_device_asleep_immediate_true(self, mock_time):
        """Test Zone 3 (9s+): Device asleep, return True immediately."""
        base_time = 1000.0
        self.controller.last_action_time = base_time
        
        test_cases = [
            (base_time + 9.0, "exactly 9s (threshold reached)"),
            (base_time + 9.1, "9.1s (just past threshold)"),
            (base_time + 15.0, "15s (long time asleep)"),
        ]
        
        for current_time, description in test_cases:
            with self.subTest(time_elapsed=description):
                mock_time.return_value = current_time
                
                start = time.perf_counter()
                result = self.controller._is_device_asleep()
                duration = time.perf_counter() - start
                
                self.assertTrue(result, f"Should be asleep at {description}")
                self.assertLess(duration, 0.1, f"Should not wait at {description}")


if __name__ == '__main__':
    print("Testing actual RemoteController sleep logic...")
    print("Configuration: GO_TO_SLEEP_DELAY_SEC=8s, SLEEP_THRESHOLD_SEC=1s")
    print("Zones: 0-7s (awake), 7-9s (uncertain/wait), 9s+ (asleep)")
    print()
    
    unittest.main(verbosity=2)