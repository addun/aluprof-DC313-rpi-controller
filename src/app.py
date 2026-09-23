import time
import threading
import logging
from flask import Flask, request, jsonify, Response, render_template, redirect
from .remote_controller import RemoteController
from .shutter_percent_controller import ShutterPercentController
from .config import Config
from .git_utils import get_git_info
from .shutter_travel_times import ShutterTravelTimeError


class PiAluprofApp:
    def __init__(
        self,
        config: Config,
        remote_controller: RemoteController,
        shutter_percent_controller: ShutterPercentController,
    ) -> None:
        self.logger = logging.getLogger('PiAluprofApp')
        self.logger.info("=== PiAluprofApp Starting ===")
        
        self.config = config
        self.remote_controller = remote_controller
        self.shutter_percent_controller = shutter_percent_controller
        self.app = Flask(__name__, template_folder='templates')
        self.device_action_lock = threading.Lock()
        
        # Get git info once at startup
        self.git_info = get_git_info()
        self.logger.info(f"Git info: {self.git_info}")
        
        self._setup_routes()
    
    def _setup_routes(self):
        """Setup Flask routes."""
        self.app.route('/state', methods=['GET'])(self.get_state)
        self.app.route('/shutter-travel-times', methods=['GET'])(self.get_shutter_travel_times)
        self.app.route('/shutter-travel-times', methods=['PUT'])(self.put_shutter_travel_times)
        self.app.route('/actions', methods=['POST'])(self.process_actions)
        self.app.route('/press/<button_id>', methods=['POST'])(self.press_button)
        self.app.route('/reset', methods=['POST'])(self.reset_device)
        self.app.route('/')(self.serve_index)
        self.app.route('/travel-times', methods=['GET'])(self.serve_travel_times)
        self.app.route('/travel-times', methods=['POST'])(self.save_travel_times)
    
    def get_state(self):
        """Returns the current synchronized state of the display."""
        state_info = self.remote_controller.get_state_info()
        state_info['is_device_asleep'] = self.remote_controller._is_device_asleep()
        return jsonify(state_info)

    def get_shutter_travel_times(self):
        """Return the live shutter travel-time map."""
        try:
            times = self.shutter_percent_controller.travel_times.load()
        except ShutterTravelTimeError as exc:
            return jsonify({"error": str(exc)}), 500
        return jsonify({"times": {str(shutter_nr): seconds for shutter_nr, seconds in sorted(times.items())}})

    def put_shutter_travel_times(self):
        """Replace the travel-time map. The new values apply to the next move."""
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or "times" not in body:
            return jsonify({"error": 'Request body must be {"times": {"1": 28.0}}.'}), 400
        try:
            saved = self.shutter_percent_controller.travel_times.replace(body["times"])
        except ShutterTravelTimeError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"times": {str(shutter_nr): seconds for shutter_nr, seconds in sorted(saved.items())}})


    
    def process_actions(self):
        """
        Execute one command. The body is a single action:

        {"nr": 1, "action": "PERCENT", "percent": 20}

        If a JSON array is sent, only the first item is used.
        """
        with self.device_action_lock:
            try:
                action_dict = self._single_action(request.get_json(silent=True))
                self.logger.debug(f"Processing action: {action_dict}")

                if 'nr' not in action_dict or 'action' not in action_dict:
                    raise ValueError("The action must include both 'nr' and 'action'.")

                target_value = action_dict['nr']
                action_name = str(action_dict['action']).upper()
                self.logger.info(f"Action: Go to {target_value}, then {action_name}")

                if isinstance(target_value, bool) or not isinstance(target_value, int) or not (0 <= target_value <= self.config.MAX_VALUE):
                    raise ValueError(f"'nr' must be an integer (0-{self.config.MAX_VALUE}).")

                if action_name == 'PERCENT':
                    self.shutter_percent_controller.set_closing_percent(
                        target_value, action_dict.get('percent')
                    )

                    return jsonify({
                        "status": "completed",
                    }), 200

                goto_result = self.remote_controller.move_to_target(target_value)

                if action_name == 'UP':
                    self.remote_controller.press_up_button()
                elif action_name == 'DOWN':
                    self.remote_controller.press_down_button()
                elif action_name == 'STOP':
                    self.remote_controller.press_stop_button()
                else:
                    raise ValueError(f"Invalid action: {action_name}. Valid actions: UP, DOWN, STOP, PERCENT")

                time.sleep(0.5)

                return jsonify({
                    "status": "completed",
                }), 200

            except (ValueError, ShutterTravelTimeError) as e:
                self.logger.error(f"API Error in process_actions: {e}")
                return jsonify({"error": str(e)}), 400
            except Exception as e:
                self.logger.error(f"API Error in process_actions: {e}")
                return jsonify({"error": str(e)}), 500

    def _single_action(self, body):
        """Return one action object. An array falls back to its first item."""
        if isinstance(body, dict):
            return body
        if isinstance(body, list):
            if not body or not isinstance(body[0], dict):
                raise ValueError("Request body must be a single action.")
            if len(body) > 1:
                self.logger.info(f"Received {len(body)} actions; using only the first")
            return body[0]
        raise ValueError("Request body must be a single action.")
    
    def press_button(self, button_id):
        """Press a specific button by ID."""
        with self.device_action_lock:
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
        with self.device_action_lock:
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

    def serve_travel_times(self):
        """Show the travel-time form."""
        try:
            return self._render_travel_times(saved=request.args.get('saved') == '1')
        except Exception as e:
            self.logger.error(f"Error serving travel times page: {e}")
            return Response(f"Error serving travel times page: {e}", status=500)

    def save_travel_times(self):
        """Save the submitted travel-time form."""
        try:
            submitted = {}
            for shutter_nr in range(0, self.config.MAX_VALUE + 1):
                raw = request.form.get(str(shutter_nr))
                if raw is None or raw.strip() == "":
                    return self._render_travel_times(
                        error=f"Travel time for shutter {shutter_nr} is required.",
                        status=400,
                    )
                try:
                    submitted[shutter_nr] = float(raw)
                except ValueError:
                    return self._render_travel_times(
                        error=f"Travel time for shutter {shutter_nr} must be a number.",
                        status=400,
                    )

            self.shutter_percent_controller.travel_times.replace(submitted)
        except ShutterTravelTimeError as exc:
            return self._render_travel_times(error=str(exc), status=400)
        except Exception as e:
            self.logger.error(f"Error saving travel times: {e}")
            return Response(f"Error saving travel times: {e}", status=500)
        return redirect('/travel-times?saved=1')

    def _render_travel_times(self, saved: bool = False, error: str = None, status: int = 200):
        times = self.shutter_percent_controller.travel_times.load()
        rows = [
            {"nr": shutter_nr, "seconds": times.get(shutter_nr, 0.0)}
            for shutter_nr in range(0, self.config.MAX_VALUE + 1)
        ]
        return render_template(
            'travel_times.html',
            rows=rows,
            saved=saved,
            error=error,
        ), status
    
    def run(self, host='0.0.0.0', port=4000, debug=False):
        """Run the Flask application."""
        self.logger.info(f"Starting Flask API on port {port}...")
        state_info = self.remote_controller.get_state_info()
        self.logger.info(f"Loaded State: {state_info['current_value']}. Range: 0-{state_info['max_value']}")

        self.app.run(host=host, port=port, debug=debug)