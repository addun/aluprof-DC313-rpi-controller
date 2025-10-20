#!/usr/bin/env python3
"""
Aluprof Display Controller - Main Entry Point

A Flask-based web application for controlling Raspberry Pi GPIO pins
to interface with a display controller.

This is the main entry point that initializes and runs the application.
All application logic has been moved to the src/ directory for better organization.
"""

import sys
import os
import logging

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src import PiAluprofApp
from src.config import Config
from src.remote_state import RemoteState
from src.gpio_controller import GPIOController
from src.remote_controller import RemoteController


def main():
    """Main application entry point."""

    logging.basicConfig(
        level=logging.DEBUG,
        format='%(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),  # Console output
        ],
        force=True  # Override any existing logging config
    )
    
    # Initialize all components
    config = Config()
    gpio_controller = GPIOController(config)
    remote_state = RemoteState(
        state_file=config.STATE_FILE,
        max_value=config.MAX_VALUE
    )
    remote_controller = RemoteController(gpio_controller, config, remote_state)
    
    # Create app with dependencies
    app = PiAluprofApp(config, remote_controller)
    
    try:
        # Initialize GPIO if running on Raspberry Pi
        if gpio_controller.initialize_gpio():
            print("GPIO initialized successfully.")
        else:
            print("Running in simulation mode (GPIO not available).")
        
        # Run the Flask application
        app.run(host='0.0.0.0', port=4000, debug=False)
        
    except KeyboardInterrupt:
        print("\nShutdown requested by user.")
    except Exception as e:
        print(f"Failed to start application: {e}")
    finally:
        # Cleanup GPIO resources
        gpio_controller.cleanup_gpio()


if __name__ == '__main__':
    main()
