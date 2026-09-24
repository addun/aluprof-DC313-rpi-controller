#!/usr/bin/env python3
"""Tests for timed shutter opening percentage."""

import os
import sys
import tempfile
import threading
import time
import unittest
from contextlib import nullcontext
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.app import PiAluprofApp
from src.config import Config
from src.remote_controller import RemoteController
from src.remote_state import RemoteState
from src.shutter_percent_controller import ActionCancelled, ShutterPercentController
from src.shutter_travel_times import ShutterTravelTimeError, ShutterTravelTimes


PIN_DECREASE = 2
PIN_UP = 3
PIN_STOP = 4
PIN_INCREASE = 14
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
            self.controller.set_opening_percent(shutter_nr, percent)
        return events

    def test_fifty_percent_opens_fully_then_closes_halfway(self):
        events = self._run(1, 50)

        self.assertEqual(events, [
            ("press", PIN_UP),
            ("sleep", 20.0),
            ("press", PIN_DOWN),
            ("sleep", 10.0),
            ("press", PIN_STOP),
        ])

    def test_below_fifty_closes_fully_then_opens_for_that_fraction(self):
        events = self._run(1, 25)

        self.assertEqual(events, [
            ("press", PIN_DOWN),
            ("sleep", 20.0),
            ("press", PIN_UP),
            ("sleep", 5.0),
            ("press", PIN_STOP),
        ])

    def test_above_fifty_opens_fully_then_closes_back(self):
        events = self._run(2, 75)

        self.assertEqual(events, [
            ("press", PIN_UP),
            ("sleep", 40.0),
            ("press", PIN_DOWN),
            ("sleep", 10.0),
            ("press", PIN_STOP),
        ])

    def test_zero_percent_only_closes_fully(self):
        events = self._run(1, 0)

        self.assertEqual(events, [
            ("press", PIN_DOWN),
            ("sleep", 20.0),
        ])

    def test_one_hundred_percent_only_opens_fully(self):
        events = self._run(1, 100)

        self.assertEqual(events, [
            ("press", PIN_UP),
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

    def test_fractional_percent_does_not_move(self):
        with self.assertRaises(ValueError):
            self._run(1, 50.5)

        self.mock_gpio.press_pin.assert_not_called()

    def test_missing_percent_does_not_move(self):
        with self.assertRaises(ValueError):
            self._run(1, None)

        self.mock_gpio.press_pin.assert_not_called()

    def test_changed_travel_time_applies_without_a_new_controller(self):
        events = self._run(1, 100)
        self.assertEqual(events, [("press", PIN_UP), ("sleep", 20.0)])

        self.store.replace({1: 8.0, 2: 40.0})
        events = self._run(1, 100)
        self.assertEqual(events, [("press", PIN_UP), ("sleep", 8.0)])

    def test_travel_wait_lets_another_channel_use_the_remote(self):
        state = RemoteState(self.config.MAX_VALUE)
        state.set_value(1)
        remote = RemoteController(self.mock_gpio, self.config, state)
        remote.last_action_time = time.time()
        self.store.replace({1: 8.0, 2: 10.0})
        controller = ShutterPercentController(remote, self.store)

        events = []
        first_wait_entered = threading.Event()
        release_first_wait = threading.Event()

        def press(pin):
            events.append(("press", pin))

        def fake_sleep(seconds):
            events.append(("sleep", seconds))
            if seconds == 8.0:
                first_wait_entered.set()
                self.assertTrue(release_first_wait.wait(2))

        self.mock_gpio.press_pin.side_effect = press
        worker = threading.Thread(
            target=lambda: controller.set_opening_percent(1, 50),
            name="shutter-1",
        )
        try:
            with patch("time.sleep", side_effect=fake_sleep):
                worker.start()
                self.assertTrue(first_wait_entered.wait(2))
                controller.set_opening_percent(2, 0)
                self.assertEqual(events, [
                    ("press", PIN_UP),
                    ("sleep", 8.0),
                    ("press", PIN_INCREASE),
                    ("press", PIN_DOWN),
                    ("sleep", 10.0),
                ])
                release_first_wait.set()
                worker.join(2)
        finally:
            release_first_wait.set()
            worker.join(2)

        self.assertFalse(worker.is_alive())
        self.assertEqual(events, [
            ("press", PIN_UP),
            ("sleep", 8.0),
            ("press", PIN_INCREASE),
            ("press", PIN_DOWN),
            ("sleep", 10.0),
            ("press", PIN_DECREASE),
            ("press", PIN_DOWN),
            ("sleep", 4.0),
            ("press", PIN_STOP),
        ])

    def test_cancel_during_the_first_press_skips_the_rest_of_the_move(self):
        cancel = threading.Event()
        events = []
        self.mock_state.current_value = 1

        def press(pin):
            events.append(pin)
            cancel.set()

        self.mock_gpio.press_pin.side_effect = press
        with self.assertRaises(ActionCancelled):
            self.controller.set_opening_percent(1, 20, cancel)

        self.assertEqual(events, [PIN_DOWN])

    def test_cancel_after_the_return_move_does_not_press_stop(self):
        cancel = threading.Event()
        events = []
        self.mock_state.current_value = 1
        self.store.replace({1: 0.05})

        def press(pin):
            events.append(pin)
            if pin == PIN_UP:
                cancel.set()

        self.mock_gpio.press_pin.side_effect = press
        with self.assertRaises(ActionCancelled):
            self.controller.set_opening_percent(1, 20, cancel)

        self.assertEqual(events, [PIN_DOWN, PIN_UP])

    def test_failure_still_presses_stop_when_the_move_was_not_cancelled(self):
        events = []
        self.mock_state.current_value = 1

        def press(pin):
            events.append(pin)
            if pin == PIN_UP:
                raise RuntimeError("gpio failed")

        self.mock_gpio.press_pin.side_effect = press
        with patch("time.sleep", side_effect=lambda seconds: events.append(("sleep", seconds))):
            with self.assertRaises(RuntimeError):
                self.controller.set_opening_percent(1, 100)

        self.assertEqual(events, [PIN_UP, PIN_STOP])


class TestPercentActionRoute(unittest.TestCase):
    def setUp(self):
        self.config = Config()
        self.remote = Mock()
        self.remote.get_lock.return_value = nullcontext()
        self.remote.get_state_info.return_value = {"current_value": 1, "max_value": 15}
        self.remote.get_current_value.return_value = 1
        self.remote._is_device_asleep.return_value = False
        self.shutter_percent = Mock()
        self.shutter_percent.travel_times.get_seconds.return_value = 20.0
        self.app = PiAluprofApp(self.config, self.remote, self.shutter_percent)
        self.client = self.app.app.test_client()

    def tearDown(self):
        self._join_device_actions()

    def _join_device_actions(self):
        for thread in threading.enumerate():
            if thread.name == "device-action":
                thread.join(timeout=2)
                self.assertFalse(thread.is_alive())

    def test_percent_action_is_delegated(self):
        response = self.client.post(
            "/actions",
            json={"nr": 1, "action": "PERCENT", "percent": 50},
        )
        self._join_device_actions()

        self.assertEqual(response.status_code, 202)
        self._assert_percent_call(1, 50)
        body = response.get_json()
        self.assertEqual(body["status"], "accepted")
        self.assertEqual(body["percent"], 50)

    def test_percent_action_returns_before_the_move_finishes(self):
        started = threading.Event()
        release = threading.Event()

        def block(shutter_nr, percent, cancel_event):
            started.set()
            self.assertTrue(release.wait(2))

        self.shutter_percent.set_opening_percent.side_effect = block

        try:
            response = self.client.post(
                "/actions",
                json={"nr": 1, "action": "PERCENT", "percent": 25},
            )
            self.assertEqual(response.status_code, 202)
            self.assertTrue(started.wait(2))
            self._assert_percent_call(1, 25)
        finally:
            release.set()

    def test_same_channel_request_cancels_the_previous_move(self):
        first_entered = threading.Event()
        first_cancelled = threading.Event()
        second_entered = threading.Event()
        release_second = threading.Event()

        def run(shutter_nr, percent, cancel_event):
            if percent == 20:
                first_entered.set()
                if cancel_event.wait(2):
                    first_cancelled.set()
                    raise ActionCancelled()
                return
            second_entered.set()
            self.assertTrue(release_second.wait(2))

        self.shutter_percent.set_opening_percent.side_effect = run

        try:
            first = self.client.post(
                "/actions",
                json={"nr": 1, "action": "PERCENT", "percent": 20},
            )
            self.assertEqual(first.status_code, 202)
            self.assertTrue(first_entered.wait(2))
            second = self.client.post(
                "/actions",
                json={"nr": 1, "action": "PERCENT", "percent": 50},
            )
            self.assertEqual(second.status_code, 202)
            self.assertTrue(first_cancelled.wait(2))
            self.assertTrue(second_entered.wait(2))
        finally:
            release_second.set()

    def test_button_on_the_same_channel_cancels_the_percent_move(self):
        entered = threading.Event()
        cancelled = threading.Event()

        def run(shutter_nr, percent, cancel_event):
            entered.set()
            if cancel_event.wait(2):
                cancelled.set()
                raise ActionCancelled()

        self.shutter_percent.set_opening_percent.side_effect = run

        started = self.client.post(
            "/actions",
            json={"nr": 1, "action": "PERCENT", "percent": 20},
        )
        self.assertEqual(started.status_code, 202)
        self.assertTrue(entered.wait(2))

        replacement = self.client.post(
            "/actions",
            json={"nr": 1, "action": "UP"},
        )
        self._join_device_actions()

        self.assertEqual(replacement.status_code, 202)
        self.assertTrue(cancelled.is_set())
        self.remote.move_to_target.assert_called_once_with(1)
        self.remote.press_up_button.assert_called_once_with()

    def test_a_different_channel_does_not_cancel_the_move_in_progress(self):
        both_started = threading.Event()
        release = threading.Event()
        cancels = {}
        order_lock = threading.Lock()

        def run(shutter_nr, percent, cancel_event):
            with order_lock:
                cancels[shutter_nr] = cancel_event
                if len(cancels) == 2:
                    both_started.set()
            self.assertTrue(release.wait(2))
            self.assertFalse(cancel_event.is_set())

        self.shutter_percent.set_opening_percent.side_effect = run

        try:
            first = self.client.post(
                "/actions",
                json={"nr": 1, "action": "PERCENT", "percent": 20},
            )
            second = self.client.post(
                "/actions",
                json={"nr": 2, "action": "PERCENT", "percent": 50},
            )
            self.assertEqual(first.status_code, 202)
            self.assertEqual(second.status_code, 202)
            self.assertTrue(both_started.wait(2))
            self.assertFalse(cancels[1].is_set())
            self.assertFalse(cancels[2].is_set())
        finally:
            release.set()

    def test_array_body_uses_only_the_first_action(self):
        response = self.client.post(
            "/actions",
            json=[
                {"nr": 1, "action": "PERCENT", "percent": 20},
                {"nr": 2, "action": "UP"},
            ],
        )
        self._join_device_actions()

        self.assertEqual(response.status_code, 202)
        self._assert_percent_call(1, 20)
        self.remote.press_up_button.assert_not_called()

    def test_up_action_is_accepted(self):
        response = self.client.post(
            "/actions",
            json={"nr": 2, "action": "UP"},
        )
        self._join_device_actions()

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.get_json()["status"], "accepted")
        self.remote.move_to_target.assert_called_once_with(2)
        self.remote.press_up_button.assert_called_once_with()

    def test_percent_configuration_error_is_returned(self):
        self.shutter_percent.travel_times.get_seconds.return_value = 0

        response = self.client.post(
            "/actions",
            json={"nr": 1, "action": "percent", "percent": 40},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Travel time", response.get_json()["error"])
        self.shutter_percent.set_opening_percent.assert_not_called()

    def test_fractional_percent_is_rejected_before_the_move(self):
        response = self.client.post(
            "/actions",
            json={"nr": 1, "action": "PERCENT", "percent": 50.5},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("integer", response.get_json()["error"])
        self.shutter_percent.set_opening_percent.assert_not_called()

    def _assert_percent_call(self, shutter_nr, percent):
        self.shutter_percent.set_opening_percent.assert_called_once()
        called_nr, called_percent, cancel_event = self.shutter_percent.set_opening_percent.call_args.args
        self.assertEqual((called_nr, called_percent), (shutter_nr, percent))
        self.assertIsInstance(cancel_event, threading.Event)
        self.assertFalse(cancel_event.is_set())

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
