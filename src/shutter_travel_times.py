"""File-backed shutter travel times."""

import json
import os
import threading
from typing import Dict, Mapping


class ShutterTravelTimeError(Exception):
    """The travel-time file or a submitted map is not usable."""


class ShutterTravelTimes:
    """Seconds to travel from fully open to fully closed, per shutter channel."""

    def __init__(self, path: str, max_value: int) -> None:
        self.path = path
        self.max_value = max_value
        self._lock = threading.Lock()

    @staticmethod
    def default_path() -> str:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        return os.path.join(root, "storage", "shutter_travel_times.json")

    def load(self) -> Dict[int, float]:
        """Return channels 0–15. A missing entry is 0 seconds."""
        with self._lock:
            return self._with_defaults(self._read())

    def get_seconds(self, shutter_nr: int) -> float:
        """Return one shutter's travel time. An unset channel is 0."""
        return self.load().get(shutter_nr, 0.0)

    def replace(self, times: Mapping) -> Dict[int, float]:
        """Replace the whole map and write it immediately.

        Channels omitted from ``times`` are stored as 0.
        """
        normalized = self._with_defaults(self._normalize(times))
        with self._lock:
            self._write(normalized)
        return normalized

    def _read(self) -> Dict[int, float]:
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise ShutterTravelTimeError(f"Could not read travel times from {self.path}: {exc}") from exc

        if not isinstance(raw, dict):
            raise ShutterTravelTimeError("Travel time file must contain an object of shutter number to seconds.")

        return self._normalize(raw)

    def _write(self, times: Dict[int, float]) -> None:
        directory = os.path.dirname(self.path)
        os.makedirs(directory, exist_ok=True)
        payload = {str(shutter_nr): seconds for shutter_nr, seconds in sorted(times.items())}
        temporary_path = self.path + ".tmp"
        with open(temporary_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
        os.replace(temporary_path, self.path)

    def _with_defaults(self, times: Dict[int, float]) -> Dict[int, float]:
        complete = {shutter_nr: 0.0 for shutter_nr in range(0, self.max_value + 1)}
        for shutter_nr, seconds in times.items():
            if shutter_nr in complete:
                complete[shutter_nr] = seconds
        return complete

    def _normalize(self, times: Mapping) -> Dict[int, float]:
        if not isinstance(times, Mapping):
            raise ShutterTravelTimeError("Travel times must be an object of shutter number to seconds.")

        normalized: Dict[int, float] = {}
        for key, value in times.items():
            shutter_nr = self._shutter_nr(key)
            if shutter_nr in normalized:
                raise ShutterTravelTimeError(f"Shutter {shutter_nr} is listed more than once.")
            normalized[shutter_nr] = self._seconds(value, shutter_nr)
        return normalized

    def _shutter_nr(self, key) -> int:
        if isinstance(key, bool):
            raise ShutterTravelTimeError(f"Shutter number {key!r} is not valid.")

        if isinstance(key, int):
            shutter_nr = key
        elif isinstance(key, str) and key.strip().isdigit():
            shutter_nr = int(key.strip())
        else:
            raise ShutterTravelTimeError(f"Shutter number {key!r} must be an integer from 0 to {self.max_value}.")
        if not 0 <= shutter_nr <= self.max_value:
            raise ShutterTravelTimeError(f"Shutter number {shutter_nr} must be from 0 to {self.max_value}.")
        return shutter_nr

    def _seconds(self, value, shutter_nr: int) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise ShutterTravelTimeError(
                f"Travel time for shutter {shutter_nr} must be zero or a positive number of seconds."
            )
        return float(value)
