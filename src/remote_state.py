"""
State Management Module for Display Controller

This module handles in-memory state management for the display controller,
tracking the current channel value.
"""


class RemoteState:
    """Manages in-memory state for the display controller."""
    
    def __init__(self, max_value: int):
        """
        Initialize the state manager.
        
        Args:
            max_value: Maximum allowed value (0 to max_value inclusive)
        """
        self.max_value = max_value
        self._current_value = 0
    
    @property
    def current_value(self) -> int:
        """Get the current display value."""
        return self._current_value
    
    def set_value(self, value: int) -> bool:
        """
        Set the current display value.
        
        Args:
            value: New value to set
            
        Returns:
            True if value was set successfully, False if invalid
        """
        if not (0 <= value <= self.max_value):
            return False
        
        self._current_value = value
        return True
    
    def increment(self) -> int:
        """
        Increment the current value with wrap-around.
        
        Returns:
            New current value after increment
        """
        self._current_value = (self._current_value + 1) % (self.max_value + 1)
        return self._current_value
    
    def decrement(self) -> int:
        """
        Decrement the current value with wrap-around.
        
        Returns:
            New current value after decrement
        """
        self._current_value = (self._current_value - 1 + self.max_value + 1) % (self.max_value + 1)
        return self._current_value
    
    def get_state_info(self) -> dict:
        """
        Get comprehensive state information.
        
        Returns:
            Dictionary containing current state information
        """
        return {
            'current_value': self._current_value,
            'max_value': self.max_value,
        }