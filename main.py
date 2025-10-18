#!/usr/bin/env python3
"""
Pidupa Display Controller - Main Entry Point

A Flask-based web application for controlling Raspberry Pi GPIO pins
to interface with a display controller.

This is the main entry point that initializes and runs the application.
All application logic has been moved to the src/ directory for better organization.
"""

import sys
import os

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src import PiAluprofApp


def main():
    """Main application entry point."""
    app = PiAluprofApp()
    
    try:
        # Initialize GPIO if running on Raspberry Pi
        if app.initialize_gpio():
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
        app.cleanup_gpio()


if __name__ == '__main__':
    main()
