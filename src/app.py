import time
import threading
from flask import Flask, request, jsonify, Response, send_from_directory
from typing import List, Dict, Any
from .state_manager import StateManager
from .gpio_controller import GPIOController
from .config import Config

try:
    import RPi.GPIO as GPIO
except ImportError:
    # For development/testing on non-Pi environments
    GPIO = None


class PiAluprofApp:
    """Main application class for the Pidupa display controller."""
    
    def __init__(self):
        self.config = Config()
        self.state_manager = StateManager(
            state_file=self.config.STATE_FILE,
            max_value=self.config.MAX_VALUE
        )
        self.gpio_controller = GPIOController(self.config)
        self.app = Flask(__name__, template_folder='templates')
        self.state_lock = threading.Lock()
        self._setup_routes()
    
    def _setup_routes(self):
        """Setup Flask routes."""
        self.app.route('/state', methods=['GET'])(self.get_state)
        self.app.route('/sync', methods=['POST'])(self.sync_state)
        self.app.route('/actions', methods=['POST'])(self.process_actions)
        self.app.route('/')(self.serve_index)
    
    def get_state(self):
        """Returns the current synchronized state of the display."""
        return jsonify(self.state_manager.get_state_info())
    
    def sync_state(self):
        """Manually sets the internal state value. POST Body: {"value": 5}"""
        try:
            data = request.get_json()
            new_value = data.get('value')
            
            if new_value is None or not isinstance(new_value, int):
                return jsonify({"error": "Invalid or missing 'value'. Must be an integer."}), 400
            
            if not self.state_manager.set_value(new_value):
                return jsonify({"error": f"Invalid value. Must be between 0 and {self.config.MAX_VALUE}."}), 400
                
            print(f"STATE SYNCED: Current value manually set to {new_value}")
            
            return jsonify({
                "status": "synchronized",
                "new_value": self.state_manager.current_value
            }), 200

        except Exception as e:
            return jsonify({"error": f"Invalid JSON format or internal error: {e}"}), 400
    
    def process_actions(self):
        """
        Unified endpoint for processing a batch of sequenced commands.
        Each command item requires 'nr' (the device/state to select) and 'action' (the command to execute).
        For DELAY actions, add 'duration' field with seconds to wait.

        Request Body Example:
        [
          {"nr": 1, "action": "DOWN"},           // 1. Go to number 1. 2. Press GO_DOWN (BCM 15).
          {"nr": 1, "action": "DELAY", "duration": 10},  // Wait 10 seconds at nr 1
          {"nr": 1, "action": "UP"},             // 3. Press MOVE_UP (BCM 3).
          {"nr": 1, "action": "DELAY", "duration": 2},   // Wait 2 seconds
          {"nr": 1, "action": "STOP"}            // 5. Press STOP (BCM 4).
        ]
        """
        with self.state_lock:
            try:
                actions: List[Dict[str, Any]] = request.get_json()
                if not isinstance(actions, list):
                    return jsonify({"error": "Request body must be a JSON array of actions."}), 400
                
                results = []

                # Press the STOP pin (BCM 4) to ensure the display is active before movement
                self.gpio_controller.press_pin(self.config.PIN_MAP['INCREASE'])
                time.sleep(self.config.WAKE_UP_DELAY_SEC)

                for action_dict in actions:
                    # Validate required fields
                    if 'nr' not in action_dict or 'action' not in action_dict:
                        results.append({"type": "error", "details": "Each command must include both 'nr' and 'action'."})
                        continue
                    
                    target_value = action_dict['nr']
                    action_name = str(action_dict['action']).upper()
                    
                    # --- 1. Go to Target Number (Select Device) ---
                    if not isinstance(target_value, int) or not (0 <= target_value <= self.config.MAX_VALUE):
                        results.append({"type": "error", "details": f"'nr' must be an integer (0-{self.config.MAX_VALUE})."})
                        continue

                    goto_result = self._move_to_target(target_value)
                    
                    # --- 2. Execute Action (UP/DOWN/STOP/DELAY) ---
                    
                    # Map user's UP/DOWN/STOP to the actual PIN_MAP keys
                    mapped_action = self.config.ACTION_ALIAS.get(action_name)

                    if not mapped_action:
                        results.append({"type": "error", "details": f"Invalid action: {action_name}. Valid actions: {list(self.config.ACTION_ALIAS.keys())}"})
                        continue
                    
                    # Handle DELAY action specially
                    if mapped_action == "DELAY":
                        # Get delay duration from 'duration' field, default to 1 second
                        delay_duration = action_dict.get('duration', 1)
                        if not isinstance(delay_duration, (int, float)) or delay_duration < 0:
                            results.append({"type": "error", "details": "DELAY action requires a positive 'duration' field (seconds)."})
                            continue
                        
                        print(f"DELAY: Waiting for {delay_duration} seconds...")
                        time.sleep(delay_duration)
                        
                        results.append({
                            "type": "delay_command",
                            "target_nr": target_value,
                            "action": action_name,
                            "duration": delay_duration,
                            "goto_details": goto_result,
                            "final_value": self.state_manager.current_value
                        })
                        continue
                    
                    # Press the manual pin (MOVE_UP, GO_DOWN, or STOP). This does NOT change the state value.
                    self.gpio_controller.press_pin(self.config.PIN_MAP[mapped_action])
                    
                    results.append({
                        "type": "sequenced_command", 
                        "target_nr": target_value,
                        "action": action_name,
                        "goto_details": goto_result,
                        "final_value": self.state_manager.current_value
                    })
                
                time.sleep(self.config.GO_TO_SLEEP_DELAY_SEC)

                return jsonify({
                    "status": "batch_completed",
                    "current_state": self.state_manager.current_value,
                    "results": results
                }), 200

            except Exception as e:
                print(f"API Error in process_actions: {e}")
                return jsonify({"error": f"Invalid JSON format or internal server error: {e}"}), 500
    
    def serve_index(self):
        """Serves the index.html file from the templates directory."""
        try:
            return send_from_directory('templates', 'index.html')
        except FileNotFoundError:
            return Response("Error: index.html not found. Please ensure the file is in the templates directory.", status=404)
        except Exception as e:
            return Response(f"Error serving index.html: {e}", status=500)
    
    def _move_to_target(self, target: int) -> Dict[str, Any]:
        """Calculates the shortest path to reach a specific target number and executes presses."""
        current_value = self.state_manager.current_value

        if not (0 <= target <= self.config.MAX_VALUE):
            return {"error": f"Target {target} out of range (0-{self.config.MAX_VALUE}).", "status": "failed"}

        if current_value == target:
            return {"status": "already_at_target", "final_value": current_value, "steps_taken": 0}

        # Calculate shortest path (using modulo arithmetic for wrap-around)
        diff_increase = (target - current_value + self.config.MAX_VALUE + 1) % (self.config.MAX_VALUE + 1)
        diff_decrease = (current_value - target + self.config.MAX_VALUE + 1) % (self.config.MAX_VALUE + 1)
        
        min_presses = min(diff_increase, diff_decrease)

        if diff_increase == min_presses:
            direction_func = self._press_increase_step
            direction_str = "INCREASE"
        else:
            direction_func = self._press_decrease_step
            direction_str = "DECREASE"

        # Execute Movement
        steps_taken = 0
        while steps_taken < min_presses:
            direction_func()
            steps_taken += 1
        
        return {
            "status": "moved_to_target",
            "target_reached": target,
            "initial_value": current_value,
            "final_value": self.state_manager.current_value,
            "steps_taken": steps_taken,
            "direction": direction_str
        }
    
    def _press_increase_step(self):
        """Presses the INCREASE button (BCM 14) and updates the state (e.g., 15 -> 0)."""
        self.gpio_controller.press_pin(self.config.PIN_MAP['INCREASE'])
        
        # State update happens ONLY on number change buttons
        new_value = self.state_manager.increment()
        
        return new_value

    def _press_decrease_step(self):
        """Presses the DECREASE button (BCM 2) and updates the state (e.g., 0 -> 15)."""
        self.gpio_controller.press_pin(self.config.PIN_MAP['DECREASE'])
        
        # State update happens ONLY on number change buttons
        new_value = self.state_manager.decrement()
        
        return new_value
    
    def initialize_gpio(self):
        """Initialize GPIO configuration."""
        if GPIO is None:
            print("GPIO module not available - running in simulation mode")
            return False
        
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            self.gpio_controller.configure_pins()
            return True
        except Exception as e:
            print(f"Failed to initialize GPIO: {e}")
            return False
    
    def cleanup_gpio(self):
        """Cleanup GPIO resources."""
        if GPIO is not None:
            print("Cleaning up GPIO...")
            GPIO.cleanup()
    
    def run(self, host='0.0.0.0', port=4000, debug=False):
        """Run the Flask application."""
        print(f"Starting Flask API on port {port}...")
        state_info = self.state_manager.get_state_info()
        print(f"Loaded State: {state_info['current_value']}. Range: 0-{state_info['max_value']}. State file: {state_info['state_file']}")
        
        self.app.run(host=host, port=port, debug=debug)