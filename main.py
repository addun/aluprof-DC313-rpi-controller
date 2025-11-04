#!/usr/bin/env python3
"""
Aluprof DC313 RPi Controller - Main Entry Point

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
        force=True
    )
    
    logger = logging.getLogger('Main')
    
    config = Config()
    gpio_controller = GPIOController(config)
    remote_state = RemoteState(
        max_value=config.MAX_VALUE
    )
    remote_controller = RemoteController(gpio_controller, config, remote_state)
    
    app = PiAluprofApp(config, remote_controller)
    
    try:
        if gpio_controller.initialize_gpio():
            logger.info("GPIO initialized successfully.")
        else:
            logger.info("Running in simulation mode (GPIO not available).")
        
        logger.info("Performing automatic device reset on startup...")
        reset_result = remote_controller.reset_device()
        if reset_result["success"]:
            logger.info("Automatic reset successful - device synchronized to channel 01")
        else:
            logger.error(f"Automatic reset failed: {reset_result.get('error', 'Unknown error')}")
        
        logger.info("Starting Flask application on 0.0.0.0:4000")
        app.run(host='0.0.0.0', port=4000, debug=False)
        
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user.")
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
    finally:
        # Cleanup GPIO resources
        logger.info("Cleaning up resources...")
        gpio_controller.cleanup_gpio()


if __name__ == '__main__':
    main()
