"""
GPIO Controller Module for Pidupa Display Controller

This module handles all GPIO operations including pin configuration and control.
"""

import time
import logging

try:
    import RPi.GPIO as GPIO
except ImportError:
    # For development/testing on non-Pi environments
    GPIO = None


class GPIOController:
    """Handles GPIO pin configuration and control operations."""
    
    def __init__(self, config):
        """
        Initialize the GPIO controller.
        
        Args:
            config: Configuration object containing GPIO settings
        """
        self.config = config
        self._gpio_available = GPIO is not None
        self.logger = logging.getLogger('GPIOController')
    
    def configure_pins(self):
        """Configure all GPIO pins as outputs with inactive state."""
        if not self._gpio_available:
            self.logger.warning("GPIO not available - running in simulation mode")
            return
        
        for pin in self.config.PIN_MAP.values():
            GPIO.setup(pin, GPIO.OUT, initial=self.config.INACTIVE_STATE)
    
    def press_pin(self, pin: int):
        """Simulates a momentary button press with automatic duration based on pin type."""
        # Find the button name for this pin and get its duration
        button_name = None
        for name, pin_num in self.config.PIN_MAP.items():
            if pin_num == pin:
                button_name = name
                break
        
        if button_name:
            press_duration = self.config.PRESS_DURATION_MAP.get(button_name, 0.1)
        else:
            press_duration = 0.1  # Default fallback
            
        if self._gpio_available:
            # 1. Activate the relay (press the button)
            GPIO.output(pin, self.config.ACTIVE_STATE)
            time.sleep(press_duration)

            # 2. Deactivate the relay (release the button)
            GPIO.output(pin, self.config.INACTIVE_STATE)
            time.sleep(self.config.PRESS_DELAY_SEC)
        else:
            # Simulation for testing on a non-Pi environment
            self.logger.debug(f"[SIMULATE] Pin {pin} pressed for {press_duration}s.")
            time.sleep(self.config.PRESS_DELAY_SEC)
    
    def initialize_gpio(self) -> bool:
        """Initialize GPIO configuration."""
        if not self._gpio_available:
            self.logger.warning("GPIO module not available - running in simulation mode")
            return False
        
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            self.configure_pins()
            self.logger.info("GPIO initialized successfully")
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize GPIO: {e}")
            return False
    
    def cleanup_gpio(self) -> None:
        """Cleanup GPIO resources."""
        if self._gpio_available:
            self.logger.info("Cleaning up GPIO...")
            GPIO.cleanup()
        else:
            self.logger.info("GPIO cleanup skipped - running in simulation mode")