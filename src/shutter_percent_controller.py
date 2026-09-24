"""Move a shutter to an opening percentage by timing from an end stop."""

import logging
import time

from .remote_controller import RemoteController
from .shutter_travel_times import ShutterTravelTimes


class ShutterPercentController:
    """Timed opening-percentage moves for one shutter channel.

    0 is fully closed and 100 is fully open. There is no position feedback,
    so the move always starts from a mechanical end stop:

    - 50% or more: open fully, then close for the remaining percentage of
      the travel time, then stop.
    - less than 50%: close fully, then open for that percentage of the travel
      time, then stop.

    Travel time is read from storage on every call, so a saved change applies
    without restarting.

    The travel wait does not hold the remote, so another channel can be
    commanded while this motor is running.
    """

    def __init__(
        self,
        remote_controller: RemoteController,
        travel_times: ShutterTravelTimes,
    ) -> None:
        self.remote_controller = remote_controller
        self.travel_times = travel_times
        self.logger = logging.getLogger('ShutterPercentController')

    def set_opening_percent(self, shutter_nr: int, percent: int) -> None:
        """Move a shutter to an opening percentage.

        The remote is taken only for each channel selection and button press.
        """
        travel_time = self._travel_time_for(shutter_nr)
        opening_percent = self._opening_percent(percent)

        if opening_percent >= 50:
            approach = "open_then_close"
            timed_wait = travel_time * ((100 - opening_percent) / 100.0)
        else:
            approach = "close_then_open"
            timed_wait = travel_time * (opening_percent / 100.0)

        self.logger.info(
            f"Shutter {shutter_nr} to {opening_percent}% open "
            f"({approach}, full travel {travel_time}s, timed move {timed_wait}s)"
        )

        remote = self.remote_controller
        buttons = {
            "UP": remote.press_up_button,
            "DOWN": remote.press_down_button,
            "STOP": remote.press_stop_button,
        }

        def press(action: str) -> None:
            with remote.get_lock():
                remote.move_to_target(shutter_nr)
                buttons[action]()

        try:
            if approach == "open_then_close":
                press("UP")
                self._wait_for_travel(travel_time)
                if timed_wait > 0:
                    press("DOWN")
                    self._wait_for_travel(timed_wait)
                    press("STOP")
            else:
                press("DOWN")
                self._wait_for_travel(travel_time)
                if timed_wait > 0:
                    press("UP")
                    self._wait_for_travel(timed_wait)
                    press("STOP")
        except Exception:
            self.logger.exception("Opening-percent move failed; pressing STOP")
            try:
                press("STOP")
            except Exception:
                self.logger.exception("Failed to stop shutter after error")
            raise

    def _travel_time_for(self, shutter_nr: int) -> float:
        """Return the full travel time."""
        travel_time = self.travel_times.get_seconds(shutter_nr)

        if travel_time <= 0:
            raise ValueError(
                f"Travel time for shutter {shutter_nr} is 0. "
                "Set it on the controller page before moving the shutter."
            )

        return travel_time

    def _opening_percent(self, percent: int) -> int:
        """Return the percentage when it is a whole number from 0 to 100."""
        if isinstance(percent, bool) or not isinstance(percent, int):
            raise ValueError("PERCENT requires an integer 'percent' between 0 and 100.")
        if not 0 <= percent <= 100:
            raise ValueError("'percent' must be between 0 and 100.")
        return percent

    def _wait_for_travel(self, seconds: float) -> None:
        """Wait while the shutter motor runs."""
        self.logger.info(f"Waiting {seconds:.2f}s for shutter travel")
        time.sleep(seconds)
