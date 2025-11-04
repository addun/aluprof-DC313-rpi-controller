import time
import threading
import logging
from flask import Flask, request, jsonify, Response, render_template
from typing import List, Dict, Any
from .remote_controller import RemoteController
from .config import Config
from .git_utils import get_git_info


class PiAluprofApp:
    def __init__(self, config: Config, remote_controller: RemoteController) -> None:
        self.logger = logging.getLogger('PiAluprofApp')
        self.logger.info("=== PiAluprofApp Starting ===")
        
        self.config = config
        self.remote_controller = remote_controller
        self.app = Flask(__name__, template_folder='templates')
        self.state_lock = threading.Lock()
        
        # Get git info once at startup
        self.git_info = get_git_info()
        self.logger.info(f"Git info: {self.git_info}")
        
        self._setup_routes()
    
    def _setup_routes(self):
        """Setup Flask routes."""
        self.app.route('/state', methods=['GET'])(self.get_state)
        self.app.route('/sync', methods=['POST'])(self.sync_state)
        self.app.route('/actions', methods=['POST'])(self.process_actions)
        self.app.route('/press/<button_id>', methods=['POST'])(self.press_button)
        self.app.route('/reset', methods=['POST'])(self.reset_device)
        self.app.route('/')(self.serve_index)
    
    def get_state(self):
        """Returns the current synchronized state of the display."""
        state_info = self.remote_controller.get_state_info()
        state_info['is_device_asleep'] = self.remote_controller._is_device_asleep()
        return jsonify(state_info)
    
    def sync_state(self):
        """Manually sets the internal state value. POST Body: {"value": 5}"""
        try:
            data = request.get_json()
            new_value = data.get('value')
            
            if new_value is None or not isinstance(new_value, int):
                return jsonify({"error": "Invalid or missing 'value'. Must be an integer."}), 400
            
            if not self.remote_controller.set_value(new_value):
                return jsonify({"error": f"Invalid value. Must be between 0 and {self.config.MAX_VALUE}."}), 400
                
            self.logger.info(f"STATE SYNCED: Current value manually set to {new_value}")
            
            return jsonify({
                "status": "synchronized",
                "new_value": self.remote_controller.get_current_value()
            }), 200

        except Exception as e:
            return jsonify({"error": f"Invalid JSON format or internal error: {e}"}), 400
    
    def process_actions(self):
        """
        Unified endpoint for processing a batch of sequenced commands.
        Each command item requires 'nr' (the device/state to select) and 'action' (the command to execute).

        Request Body Example:
        [
          {"nr": 1, "action": "DOWN"},    // 1. Go to number 1. 2. Press GO_DOWN (BCM 15).
          {"nr": 1, "action": "UP"},      // 2. Press MOVE_UP (BCM 3).
          {"nr": 1, "action": "STOP"}     // 3. Press STOP (BCM 4).
        ]
        """
        with self.state_lock:
            try:
                actions: List[Dict[str, Any]] = request.get_json()
                if not isinstance(actions, list):
                    return jsonify({"error": "Request body must be a JSON array of actions."}), 400
                
                results = []

                for action_dict in actions:
                    self.logger.debug(f"Processing action: {action_dict}")
                    
                    # Validate required fields
                    if 'nr' not in action_dict or 'action' not in action_dict:
                        results.append({"type": "error", "details": "Each command must include both 'nr' and 'action'."})
                        continue
                    
                    target_value = action_dict['nr']
                    action_name = str(action_dict['action']).upper()
                    
                    self.logger.info(f"Action: Go to {target_value}, then {action_name}")
                    
                    # --- 1. Go to Target Number (Select Device) ---
                    if not isinstance(target_value, int) or not (0 <= target_value <= self.config.MAX_VALUE):
                        results.append({"type": "error", "details": f"'nr' must be an integer (0-{self.config.MAX_VALUE})."})
                        continue

                    goto_result = self.remote_controller.move_to_target(target_value)
                    
                    # --- 2. Execute Action (UP/DOWN/STOP/DELAY) ---
                    
                    # Execute the action using remote controller methods
                    if action_name == 'UP':
                        self.remote_controller.press_up_button()
                    elif action_name == 'DOWN':
                        self.remote_controller.press_down_button()
                    elif action_name == 'STOP':
                        self.remote_controller.press_stop_button()
                    else:
                        results.append({"type": "error", "details": f"Invalid action: {action_name}. Valid actions: UP, DOWN, STOP"})
                        continue
                    
                    time.sleep(0.5) # Small delay to ensure action is registered
                    
                    results.append({
                        "type": "sequenced_command", 
                        "target_nr": target_value,
                        "action": action_name,
                        "goto_details": goto_result,
                        "final_value": self.remote_controller.get_current_value()
                    })
                


                return jsonify({
                    "status": "batch_completed",
                    "current_state": self.remote_controller.get_current_value(),
                    "results": results
                }), 200

            except Exception as e:
                self.logger.error(f"API Error in process_actions: {e}")
                return jsonify({"error": f"Invalid JSON format or internal server error: {e}"}), 500
    
    def press_button(self, button_id):
        """Press a specific button by ID."""
        with self.state_lock:
            try:
                button_id = button_id.upper()
                self.logger.info(f"Button press request: {button_id}")
                
                # Map button IDs to remote controller methods
                button_actions = {
                    'UP': self.remote_controller.press_up_button,
                    'DOWN': self.remote_controller.press_down_button,
                    'LEFT': self.remote_controller.press_left_button,
                    'RIGHT': self.remote_controller.press_right_button,
                    'STOP': self.remote_controller.press_stop_button,
                    'P2': self.remote_controller.press_p2_button
                }
                
                if button_id not in button_actions:
                    return jsonify({
                        "error": f"Invalid button ID: {button_id}. Valid buttons: {list(button_actions.keys())}"
                    }), 400
                
                # Execute the button press
                result = button_actions[button_id]()
                
                # Handle buttons that return new values (LEFT/RIGHT)
                response_data = {
                    "status": "button_pressed",
                    "button": button_id,
                    "current_state": self.remote_controller.get_current_value()
                }
                
                if result is not None:  # LEFT/RIGHT buttons return new value
                    response_data["new_value"] = result
                
                return jsonify(response_data), 200
                
            except Exception as e:
                self.logger.error(f"API Error in press_button: {e}")
                return jsonify({"error": f"Internal server error: {e}"}), 500
    
    def reset_device(self):
        """Reset the device to its default state (channel 01)."""
        with self.state_lock:
            try:
                self.logger.info("Device reset requested via API")
                
                # Perform the reset
                reset_result = self.remote_controller.reset_device()
                
                if reset_result["success"]:
                    return jsonify(reset_result), 200
                else:
                    return jsonify(reset_result), 500
                    
            except Exception as e:
                self.logger.error(f"API Error in reset_device: {e}")
                return jsonify({
                    "success": False,
                    "error": f"Internal server error: {e}",
                    "current_value": self.remote_controller.get_current_value()
                }), 500
    
    def serve_index(self):
        """Serves the controller page with git information."""
        try:
            return render_template('controller.html', git_info=self.git_info)
        except Exception as e:
            self.logger.error(f"Error serving controller page: {e}")
            return Response(f"Error serving controller page: {e}", status=500)
    
    def run(self, host='0.0.0.0', port=4000, debug=False):
        """Run the Flask application."""
        self.logger.info(f"Starting Flask API on port {port}...")
        state_info = self.remote_controller.get_state_info()
        self.logger.info(f"Loaded State: {state_info['current_value']}. Range: 0-{state_info['max_value']}. State file: {state_info['state_file']}")

        self.app.run(host=host, port=port, debug=debug)