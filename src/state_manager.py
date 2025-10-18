"""
State Management Module for Display Controller

This module handles persistent state management for the display controller,
including loading/saving state to JSON file and providing thread-safe operations.
"""

import json
import os
import time
import threading
from typing import Optional


class StateManager:
    """Manages persistent state for the display controller."""
    
    def __init__(self, state_file: str = 'display_state.json', max_value: int = 15):
        """
        Initialize the state manager.
        
        Args:
            state_file: Path to the state file
            max_value: Maximum allowed value (0 to max_value inclusive)
        """
        self.state_file = state_file
        self.max_value = max_value
        self._current_value = 0
        self._lock = threading.Lock()  # Thread safety for concurrent access
        
        # Load initial state
        self._current_value = self._load_from_file()
    
    def _load_from_file(self) -> int:
        """Load the current display value from state file, or return 0 if file doesn't exist."""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    value = data.get('current_value', 0)
                    if 0 <= value <= self.max_value:
                        print(f"State loaded from file: {value}")
                        return value
                    else:
                        print(f"Invalid value {value} in state file, using default 0")
            return 0  # Default value if file doesn't exist or invalid
        except Exception as e:
            print(f"Warning: Could not load state from file: {e}. Using default value 0.")
            return 0
    
    def _save_to_file(self, value: int) -> None:
        """Save the current display value to state file."""
        try:
            state_data = {
                'current_value': value,
                'timestamp': time.time(),
                'max_value': self.max_value
            }
            with open(self.state_file, 'w') as f:
                json.dump(state_data, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not save state to file: {e}")
    
    @property
    def current_value(self) -> int:
        """Get the current display value (thread-safe)."""
        with self._lock:
            return self._current_value
    
    def set_value(self, value: int) -> bool:
        """
        Set the current display value (thread-safe).
        
        Args:
            value: New value to set
            
        Returns:
            True if value was set successfully, False if invalid
        """
        if not (0 <= value <= self.max_value):
            return False
        
        with self._lock:
            self._current_value = value
            self._save_to_file(value)
        return True
    
    def increment(self) -> int:
        """
        Increment the current value with wrap-around (thread-safe).
        
        Returns:
            New current value after increment
        """
        with self._lock:
            self._current_value = (self._current_value + 1) % (self.max_value + 1)
            self._save_to_file(self._current_value)
            return self._current_value
    
    def decrement(self) -> int:
        """
        Decrement the current value with wrap-around (thread-safe).
        
        Returns:
            New current value after decrement
        """
        with self._lock:
            self._current_value = (self._current_value - 1 + self.max_value + 1) % (self.max_value + 1)
            self._save_to_file(self._current_value)
            return self._current_value
    
    def get_state_info(self) -> dict:
        """
        Get comprehensive state information.
        
        Returns:
            Dictionary containing current state information
        """
        with self._lock:
            return {
                'current_value': self._current_value,
                'max_value': self.max_value,
                'state_file': self.state_file,
                'synced': True
            }