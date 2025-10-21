
from .gpio_controller import GPIOController
from .config import Config
from .remote_state import RemoteState
import time
import logging
from typing import Dict, Any


class RemoteController:
    """Controller for handling remote control button presses."""
    
    def __init__(self, gpio_controller: GPIOController, config: Config, remote_state: RemoteState) -> None:
        """
        Initialize the remote controller.
        
        Args:
            gpio_controller: GPIO controller instance for pin operations
            config: Configuration object containing pin mappings
            remote_state: RemoteState instance for state management
        """
        self.gpio_controller = gpio_controller
        self.config = config
        self.remote_state = remote_state
        self.last_action_time = 0  # Track when the last action was performed
        self.logger = logging.getLogger('RemoteController')
    
    def press_up_button(self) -> None:
        """Press the up button (MOVE_UP)."""
        self._wake_up_when_needed()
        self.gpio_controller.press_pin(self.config.PIN_MAP['MOVE_UP'])
        self._update_action_time()
    
    def press_down_button(self) -> None:
        """Press the down button (GO_DOWN)."""
        self._wake_up_when_needed()
        self.gpio_controller.press_pin(self.config.PIN_MAP['GO_DOWN'])
        self._update_action_time()
    
    def press_left_button(self) -> int:
        """Press the left button (DECREASE).
        
        Returns:
            int: The new current value after decrementing
        """
        self._wake_up_when_needed()
        self.gpio_controller.press_pin(self.config.PIN_MAP['DECREASE'])
        new_value = self.remote_state.decrement()
        self._update_action_time()
        return new_value
    
    def press_right_button(self) -> int:
        """Press the right button (INCREASE).
        
        Returns:
            int: The new current value after incrementing
        """
        self._wake_up_when_needed()
        self.gpio_controller.press_pin(self.config.PIN_MAP['INCREASE'])
        new_value = self.remote_state.increment()
        self._update_action_time()
        return new_value
    
    def press_stop_button(self) -> None:
        """Press the stop button (STOP)."""
        self._wake_up_when_needed()
        self.gpio_controller.press_pin(self.config.PIN_MAP['STOP'])
        self._update_action_time()
    
    def press_p2_button(self) -> None:
        """Press the P2 button (placeholder for future implementation)."""
        self._wake_up_when_needed()
        # Note: P2 button pin mapping needs to be added to config.PIN_MAP when available
        self._update_action_time()
    
    # State management methods
    def get_current_value(self) -> int:
        """Get the current state value."""
        return self.remote_state.current_value
    
    def set_value(self, value: int) -> bool:
        """Set the current state value."""
        return self.remote_state.set_value(value)
    
    def get_state_info(self) -> Dict[str, Any]:
        """Get comprehensive state information."""
        return self.remote_state.get_state_info()
    
    def move_to_target(self, target: int) -> Dict[str, Any]:
        """Move to a specific target value using the shortest path."""
        current_value = self.remote_state.current_value
        self.logger.debug(f"move_to_target: current={current_value}, target={target}")

        if not (0 <= target <= self.config.MAX_VALUE):
            return {"error": f"Target {target} out of range (0-{self.config.MAX_VALUE}).", "status": "failed"}

        if current_value == target:
            self.logger.debug("Already at target - no movement needed")
            return {"status": "already_at_target", "final_value": current_value, "steps_taken": 0}

        # Calculate shortest path (using modulo arithmetic for wrap-around)
        diff_increase = (target - current_value + self.config.MAX_VALUE + 1) % (self.config.MAX_VALUE + 1)
        diff_decrease = (current_value - target + self.config.MAX_VALUE + 1) % (self.config.MAX_VALUE + 1)
        
        min_presses = min(diff_increase, diff_decrease)
        self.logger.debug(f"Path calculation: increase={diff_increase}, decrease={diff_decrease}, min={min_presses}")

        if diff_increase == min_presses:
            direction_func = self.press_right_button
            direction_str = "INCREASE"
        else:
            direction_func = self.press_left_button
            direction_str = "DECREASE"

        self.logger.debug(f"Moving {direction_str} for {min_presses} steps")

        # Execute Movement
        steps_taken = 0
        while steps_taken < min_presses:
            direction_func()
            steps_taken += 1
            self.logger.debug(f"Step {steps_taken}: new value = {self.remote_state.current_value}")
        
        final_value = self.remote_state.current_value
        self.logger.info(f"Navigation complete: {current_value} → {final_value} (target: {target})")
        
        return {
            "status": "moved_to_target",
            "target_reached": target,
            "initial_value": current_value,
            "final_value": final_value,
            "steps_taken": steps_taken,
            "direction": direction_str
        }
    
    # Private methods
    def _is_device_asleep(self) -> bool:
        """Check if the device is currently asleep based on time since last action.
        
        Uses a threshold buffer to ensure the device is definitely asleep,
        avoiding uncertainty when timing is very close to the sleep delay.
        
        Complete Logic:
        - 0 to (8-1)s = 0-7s: Device is definitely awake, return False immediately
        - (8-1)s to (8+1)s = 7-9s: Uncertain zone (approaching/transitioning to sleep)
          -> WAIT until 9s total elapsed, then return True (device is asleep)
        - (8+1)s+ = 9s+: Device is definitely asleep, return True immediately
        
        Configuration:
        - GO_TO_SLEEP_DELAY_SEC = 8s (when device starts sleeping)
        - SLEEP_THRESHOLD_SEC = 1s (buffer for uncertainty)
        - Uncertain zone = [7s, 9s) where we wait to be certain
        
        Examples:
        - At 6.5s: Return False (clearly awake)
        - At 7.3s: Wait 1.7s until 9s total, then return True
        - At 8.2s: Wait 0.8s until 9s total, then return True  
        - At 9.1s: Return True immediately (clearly asleep)
        """
        sleep_delay = self.config.GO_TO_SLEEP_DELAY_SEC
        threshold = self.config.SLEEP_THRESHOLD_SEC
        
        if self.last_action_time == 0:
            # Device starts in unknown state - wait to be certain it's asleep
            wait_time = sleep_delay + threshold
            self.logger.debug(f"Device in unknown state - waiting {wait_time:.1f}s to ensure it's asleep")
            time.sleep(wait_time)
            return True
        
        time_since_last_action = time.time() - self.last_action_time
        
        uncertain_zone_start = sleep_delay - threshold
        uncertain_zone_end = sleep_delay + threshold
        
        # If we're approaching or past sleep time but not yet at threshold, wait
        if uncertain_zone_start <= time_since_last_action <= uncertain_zone_end:
            # We're in the uncertain zone - wait until we're sure
            wait_time = uncertain_zone_end - time_since_last_action
            self.logger.debug(f"Device approaching/in sleep transition - waiting {wait_time:.1f}s to be certain")
            time.sleep(wait_time)
            return True
        
        return time_since_last_action >= uncertain_zone_end
    
    def _wake_up_when_needed(self) -> None:
        """Wake up the device if it's asleep."""
        if self._is_device_asleep():
            self.logger.info("Device is asleep - waking up...")
            self.gpio_controller.press_pin(self.config.PIN_MAP['INCREASE'])
            self.last_action_time = time.time()
            time.sleep(self.config.WAKE_UP_DELAY_SEC)
        else:
            self.logger.debug("Device is already awake - continuing...")
    
    def _update_action_time(self) -> None:
        """Update the last action time to current time."""
        self.last_action_time = time.time()
