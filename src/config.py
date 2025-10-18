"""
Configuration Module for Pidupa Display Controller

This module contains all configuration constants and settings for the application.
"""


class Config:
    """Configuration class containing all application settings."""
    
    # --- Core Configuration ---
    MAX_VALUE = 15
    STATE_FILE = 'display_state.json'
    
    # --- Timing Configuration ---
    PRESS_DURATION_SEC = 0.1
    PRESS_DELAY_SEC = 0.1  # Delay between presses to allow the PIC chip to register input
    WAKE_UP_DELAY_SEC = 0.5
    GO_TO_SLEEP_DELAY_SEC = 8  # Device needs 8 seconds to go to sleep after any action
    
    # --- GPIO Pin Configuration ---
    # Corrected Pin Mapping based on user input
    PIN_MAP = {
        'DECREASE': 2,   # BCM 2: Decreases the current number (updates state)
        'MOVE_UP': 3,    # BCM 3: Moves cursor/action (DOES NOT update number state)
        'STOP': 4,       # BCM 4: Action (DOES NOT update number state)
        'INCREASE': 14,  # BCM 14: Increases the current number (updates state)
        'GO_DOWN': 15,   # BCM 15: Moves cursor/action (DOES NOT update number state)
    }
    
        # Mapping user-friendly actions to defined PIN_MAP keys (used in /actions body)
    ACTION_ALIAS = {
        "UP": "MOVE_UP",
        "DOWN": "GO_DOWN",
        "STOP": "STOP"
    }
    
    # --- GPIO Relay Configuration ---
    # NOTE: Set this flag based on relay module.
    # True: HIGH (3.3V) activates the relay.
    # False: LOW (0V) activates the relay (most common Active-LOW relays).
    ACTIVE_HIGH = False
    
    @property
    def ACTIVE_STATE(self):
        """GPIO state that activates the relay."""
        try:
            import RPi.GPIO as GPIO
            return GPIO.HIGH if self.ACTIVE_HIGH else GPIO.LOW
        except ImportError:
            return 1 if self.ACTIVE_HIGH else 0
    
    @property
    def INACTIVE_STATE(self):
        """GPIO state that deactivates the relay."""
        try:
            import RPi.GPIO as GPIO
            return GPIO.LOW if self.ACTIVE_HIGH else GPIO.HIGH
        except ImportError:
            return 0 if self.ACTIVE_HIGH else 1