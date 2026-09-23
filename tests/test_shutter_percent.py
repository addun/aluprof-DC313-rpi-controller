#!/usr/bin/env python3
"""Tests for timed shutter closing percentage."""

import os
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.app import PiAluprofApp
from src.config import Config
from src.remote_controller import RemoteController
from src.shutter_percent_controller import ShutterPercentController
from src.shutter_travel_times import ShutterTravelTimeError, ShutterTravelTimes


PIN_UP = 3
PIN_STOP = 4
PIN_DOWN = 15


class TestSetClosingPercent(unittest.TestCase):
    def setUp(self):
        self.mock_gpio = Mock()
        self.config = Config()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = ShutterTravelTimes(
            os.path.join(self.temp_dir.name, "shutter_travel_times.json"),
            self.config.MAX_VALUE,
        )
        self.store.replace({1: 20.0, 2: 40.0})
        self.mock_state = Mock()
        self.mock_state.current_value = 1
        self.remote = RemoteController(self.mock_gpio, self.config, self.mock_state)
        self.remote.last_action_time = time.time()
        self.controller = ShutterPercentController(self.remote, self.store)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _run(self, shutter_nr, percent):
        events = []
        self.mock_state.current_value = shutter_nr
        self.mock_gpio.press_pin.side_effect = lambda pin: events.append(("press", pin))
        with patch("time.sleep", side_effect=lambda seconds: events.append(("sleep", seconds))):
            result = self.controller.set_closing_percent(shutter_nr, percent)
        return result, events

    def test_fifty_percent_opens_fully_then_closes_halfway(self):
        result, events = self._run(1, 50)

        self.assertEqual(result["approach"], "open_then_close")
        self.assertEqual(events, [
            ("press", PIN_UP),
            ("sleep", 20.0),
            ("press", PIN_DOWN),
            ("sleep", 10.0),
            ("press", PIN_STOP),
        ])

    def test_below_fifty_closes_for_that_fraction(self):
        result, events = self._run(1, 25)

        self.assertEqual(result["approach"], "open_then_close")
        self.assertEqual(events, [
            ("press", PIN_UP),
            ("sleep", 20.0),
            ("press", PIN_DOWN),
            ("sleep", 5.0),
            ("press", PIN_STOP),
        ])

    def test_above_fifty_closes_fully_then_opens_back(self):
        result, events = self._run(2, 75)

        self.assertEqual(result["approach"], "close_then_open")
        self.assertEqual(result["timed_move_sec"], 10.0)
        self.assertEqual(events, [
            ("press", PIN_DOWN),
            ("sleep", 40.0),
            ("press", PIN_UP),
            ("sleep", 10.0),
            ("press", PIN_STOP),
        ])

    def test_zero_percent_only_opens_fully(self):
        _, events = self._run(1, 0)

        self.assertEqual(events, [
            ("press", PIN_UP),
            ("sleep", 20.0),
        ])

    def test_one_hundred_percent_only_closes_fully(self):
        _, events = self._run(1, 100)

        self.assertEqual(events, [
            ("press", PIN_DOWN),
            ("sleep", 20.0),
        ])

    def test_unknown_shutter_does_not_move(self):
        with self.assertRaises(ValueError) as caught:
            self._run(9, 50)

        self.assertIn("shutter 9 is 0", str(caught.exception))
        self.mock_gpio.press_pin.assert_not_called()

    def test_percent_out_of_range_does_not_move(self):
        with self.assertRaises(ValueError):
            self._run(1, 101)

        self.mock_gpio.press_pin.assert_not_called()

    def test_missing_percent_does_not_move(self):
        with self.assertRaises(ValueError):
            self._run(1, None)

        self.mock_gpio.press_pin.assert_not_called()

    def test_changed_travel_time_applies_without_a_new_controller(self):
        _, events = self._run(1, 0)
        self.assertEqual(events, [("press", PIN_UP), ("sleep", 20.0)])

        self.store.replace({1: 8.0, 2: 40.0})
        _, events = self._run(1, 0)
        self.assertEqual(events, [("press", PIN_UP), ("sleep", 8.0)])


class TestPercentActionRoute(unittest.TestCase):
    def setUp(self):
        self.config = Config()
        self.remote = Mock()
        self.remote.get_state_info.return_value = {"current_value": 1, "max_value": 15}
        self.remote.get_current_value.return_value = 1
        self.remote._is_device_asleep.return_value = False
        self.shutter_percent = Mock()
        self.app = PiAluprofApp(self.config, self.remote, self.shutter_percent)
        self.client = self.app.app.test_client()

    def test_percent_action_is_delegated(self):
        self.shutter_percent.set_closing_percent.return_value = {
            "percent": 50.0,
            "approach": "open_then_close",
            "travel_time_sec": 20.0,
            "timed_move_sec": 10.0,
            "final_value": 1,
        }

        response = self.client.post(
            "/actions",
            json={"nr": 1, "action": "PERCENT", "percent": 50},
        )

        self.assertEqual(response.status_code, 200)
        self.shutter_percent.set_closing_percent.assert_called_once_with(1, 50)
        body = response.get_json()
        self.assertEqual(body["approach"], "open_then_close")
        self.assertEqual(body["percent"], 50.0)

    def test_array_body_uses_only_the_first_action(self):
        self.shutter_percent.set_closing_percent.return_value = {
            "percent": 20.0,
            "approach": "open_then_close",
            "travel_time_sec": 20.0,
            "timed_move_sec": 4.0,
            "final_value": 1,
        }

        response = self.client.post(
            "/actions",
            json=[
                {"nr": 1, "action": "PERCENT", "percent": 20},
                {"nr": 2, "action": "UP"},
            ],
        )

        self.assertEqual(response.status_code, 200)
        self.shutter_percent.set_closing_percent.assert_called_once_with(1, 20)
        self.remote.press_up_button.assert_not_called()

    def test_percent_configuration_error_is_returned(self):
        self.shutter_percent.set_closing_percent.side_effect = ValueError(
            "No travel time configured for shutter 1."
        )

        response = self.client.post(
            "/actions",
            json={"nr": 1, "action": "percent", "percent": 40},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("travel time", response.get_json()["error"])

    def test_index_links_to_the_travel_times_page(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'href="/travel-times"', response.data)
        self.assertNotIn(b"Execute Action", response.data)
        self.assertNotIn(b"<form", response.data)


class TestShutterTravelTimeApi(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = ShutterTravelTimes(
            os.path.join(self.temp_dir.name, "shutter_travel_times.json"),
            max_value=15,
        )
        self.remote = Mock()
        self.remote.get_state_info.return_value = {"current_value": 1, "max_value": 15}
        self.remote.get_current_value.return_value = 1
        self.remote._is_device_asleep.return_value = False
        self.shutter_percent = Mock()
        self.shutter_percent.travel_times = self.store
        self.client = PiAluprofApp(Config(), self.remote, self.shutter_percent).app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_put_is_visible_on_the_next_get(self):
        response = self.client.put(
            "/shutter-travel-times",
            json={"times": {"1": 28, "2": 35.5}},
        )
        self.assertEqual(response.status_code, 200)
        times = response.get_json()["times"]
        self.assertEqual(len(times), 16)
        self.assertEqual(times["0"], 0.0)
        self.assertEqual(times["1"], 28.0)
        self.assertEqual(times["2"], 35.5)
        self.assertEqual(times["3"], 0.0)
        self.assertEqual(times["15"], 0.0)

        loaded = self.client.get("/shutter-travel-times")
        self.assertEqual(loaded.status_code, 200)
        self.assertEqual(loaded.get_json()["times"]["1"], 28.0)
        self.assertEqual(self.store.get_seconds(1), 28.0)
        self.assertEqual(self.store.get_seconds(9), 0.0)

    def test_put_rejects_a_negative_time(self):
        response = self.client.put(
            "/shutter-travel-times",
            json={"times": {"1": -1}},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("positive", response.get_json()["error"])

    def test_travel_times_form_saves_without_json(self):
        page = self.client.get("/travel-times")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'method="post"', page.data)
        self.assertIn(b"Execute Action", page.data)
        self.assertIn(b'name="0"', page.data)
        self.assertIn(b'name="15"', page.data)

        form = {str(nr): "0" for nr in range(0, 16)}
        form["0"] = "12.5"
        response = self.client.post("/travel-times", data=form, follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Saved.", response.data)
        self.assertEqual(self.store.get_seconds(0), 12.5)
        self.assertEqual(self.store.get_seconds(1), 0.0)

    def test_get_defaults_every_channel_to_zero(self):
        response = self.client.get("/shutter-travel-times")
        self.assertEqual(response.status_code, 200)
        times = response.get_json()["times"]
        self.assertEqual(
            {int(nr): seconds for nr, seconds in times.items()},
            {nr: 0.0 for nr in range(0, 16)},
        )

    def test_direct_file_edit_is_used_on_the_next_read(self):
        self.store.replace({1: 10.0})
        with open(self.store.path, "w", encoding="utf-8") as handle:
            handle.write('{"1": 12.5}\n')
        self.assertEqual(self.store.get_seconds(1), 12.5)

    def test_corrupt_file_raises(self):
        self.store.replace({1: 10.0})
        with open(self.store.path, "w", encoding="utf-8") as handle:
            handle.write("{")
        with self.assertRaises(ShutterTravelTimeError):
            self.store.load()


if __name__ == "__main__":
    unittest.main()
