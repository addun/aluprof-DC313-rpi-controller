"""
Pidupa Display Controller Package

A Flask-based web application for controlling Raspberry Pi GPIO pins
to interface with a display controller.
"""

from .app import PiAluprofApp
from .config import Config
from .remote_state import RemoteState
from .gpio_controller import GPIOController

__version__ = "1.0.0"
__all__ = ["PiAluprofApp", "Config", "RemoteState", "GPIOController"]