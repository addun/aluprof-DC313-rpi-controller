# Pidupa Display Controller

A Flask-based web application for controlling Raspberry Pi GPIO pins to interface with a display controller.

## Project Structure

```
pidupa/
├── main.py                    # Application entry point
├── display_state.json         # Persistent state file
├── requirements.txt           # Python dependencies
├── venv/                     # Virtual environment
└── src/                      # Application source code
    ├── __init__.py           # Package initialization
    ├── app.py                # Main Flask application class
    ├── config.py             # Configuration settings
    ├── gpio_controller.py    # GPIO control operations
    ├── state_manager.py      # State management and persistence
    └── templates/
        └── index.html        # Web interface
```

## Features

- **State Management**: Persistent state tracking with JSON file storage
- **GPIO Control**: Safe GPIO pin control with simulation mode for development
- **Web Interface**: Clean web UI for controlling the display
- **RESTful API**: JSON API for external integrations
- **Thread Safety**: Concurrent request handling with proper locking
- **Modular Design**: Clean separation of concerns with organized modules

## Installation

1. **Clone/Download the project**
2. **Create virtual environment:**
   ```bash
   cd pidupa
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## Usage

### Running the Application

```bash
# Activate virtual environment
source venv/bin/activate

# Start the application
python3 main.py
```

The application will:
- Start on `http://0.0.0.0:4000` (accessible from local network)
- Load previous state from `display_state.json`
- Initialize GPIO (on Raspberry Pi) or run in simulation mode

### API Endpoints

- **GET /state** - Get current display state
- **POST /sync** - Manually sync state: `{"value": 5}`
- **POST /actions** - Execute commands: `[{"nr": 5, "action": "UP"}]`
- **GET /** - Web interface

### Web Interface

Access the web interface at `http://[raspberry-pi-ip]:4000` to:
- View current state
- Sync state manually
- Execute single or batch actions
- Monitor API responses

## Configuration

Edit `src/config.py` to modify:
- GPIO pin mappings
- Timing parameters
- Relay configuration (active high/low)
- Maximum display value

## Development

The application supports development mode:
- Automatically detects if running on non-Pi environment
- Simulates GPIO operations with console output
- All functionality works without actual GPIO hardware

## GPIO Pin Configuration

Default BCM pin mapping:
- **Pin 2**: DECREASE (decrements display value)
- **Pin 3**: MOVE_UP (cursor movement)
- **Pin 4**: STOP (stop action)
- **Pin 14**: INCREASE (increments display value)
- **Pin 15**: GO_DOWN (cursor movement)

## Safety Features

- Automatic GPIO cleanup on shutdown
- Thread-safe state management
- Error handling and validation
- Graceful fallback to simulation mode
- Persistent state across restarts