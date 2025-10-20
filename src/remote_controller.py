
from .gpio_controller import GPIOController
from .config import Config
from .remote_state import RemoteState
import time
import logging
from typing import Dict, Any


class RemoteController:
    """Controller for handling remote control button presses."""
    
    def __init__(self, gpio_controller: GPIOController, config: Config) -> None:
        """
        Initialize the remote controller.
        
        Args:
            gpio_controller: GPIO controller instance for pin operations
            config: Configuration object containing pin mappings
        """
        self.gpio_controller = gpio_controller
        self.config = config
        self.remote_state = RemoteState(
            state_file=config.STATE_FILE,
            max_value=config.MAX_VALUE
        )
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
    
    def press_middle_button(self) -> None:
        """Press the middle button (STOP)."""
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
        """Check if the device is currently asleep based on time since last action."""
        if self.last_action_time == 0:
            return True  # Device starts asleep
        
        time_since_last_action = time.time() - self.last_action_time
        return time_since_last_action >= self.config.GO_TO_SLEEP_DELAY_SEC
    
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
