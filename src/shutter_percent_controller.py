"""Move a shutter to a closing percentage by timing from an end stop."""

import logging
import time
from typing import Any, Dict, Optional

from .remote_controller import RemoteController
from .shutter_travel_times import ShutterTravelTimes


class ShutterPercentController:
    """Timed closing-percentage moves for one shutter channel.

    0 is fully open and 100 is fully closed. There is no position feedback,
    so the move always starts from a mechanical end stop:

    - 50% or less: open fully, then close for that percentage of the travel
      time, then stop.
    - more than 50%: close fully, then open for the remaining percentage of
      the travel time, then stop.

    Travel time is read from storage on every call, so a saved change applies
    without restarting.
    """

    def __init__(
        self,
        remote_controller: RemoteController,
        travel_times: Optional[ShutterTravelTimes] = None,
    ) -> None:
        self.remote_controller = remote_controller
        self.travel_times = travel_times or ShutterTravelTimes(
            ShutterTravelTimes.default_path(),
            remote_controller.config.MAX_VALUE,
        )
        self.logger = logging.getLogger('ShutterPercentController')

    def set_closing_percent(self, shutter_nr: int, percent: Any) -> None:
        """Select the shutter and move it to a closing percentage."""
        travel_time = self._travel_time_for(shutter_nr)
        closing_percent = self._closing_percent(percent)

        goto_result = self.remote_controller.move_to_target(shutter_nr)
        if goto_result.get("status") == "failed":
            raise ValueError(goto_result.get("error", "Failed to select shutter."))

        if closing_percent <= 50:
            approach = "open_then_close"
            timed_wait = travel_time * (closing_percent / 100.0)
        else:
            approach = "close_then_open"
            timed_wait = travel_time * ((100.0 - closing_percent) / 100.0)

        self.logger.info(
            f"Shutter {shutter_nr} to {closing_percent}% closed "
            f"({approach}, full travel {travel_time}s, timed move {timed_wait}s)"
        )

        try:
            if approach == "open_then_close":
                self.remote_controller.press_up_button()
                self._wait_for_travel(travel_time)
                if timed_wait > 0:
                    self.remote_controller.press_down_button()
                    self._wait_for_travel(timed_wait)
                    self.remote_controller.press_stop_button()
            else:
                self.remote_controller.press_down_button()
                self._wait_for_travel(travel_time)
                if timed_wait > 0:
                    self.remote_controller.press_up_button()
                    self._wait_for_travel(timed_wait)
                    self.remote_controller.press_stop_button()
        except Exception:
            self.logger.exception("Closing-percent move failed; pressing STOP")
            try:
                self.remote_controller.press_stop_button()
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

    def _closing_percent(self, percent: Any) -> float:
        """Return the percentage as a float."""
        if isinstance(percent, bool) or not isinstance(percent, (int, float)):
            raise ValueError("PERCENT requires a numeric 'percent' between 0 and 100.")
        if not 0 <= percent <= 100:
            raise ValueError("'percent' must be between 0 and 100.")
        return float(percent)

    def _wait_for_travel(self, seconds: float) -> None:
        """Wait while the shutter motor runs."""
        self.logger.info(f"Waiting {seconds:.2f}s for shutter travel")
        time.sleep(seconds)
