"""Constants for the IR floor heating integration."""

from homeassistant.const import Platform

DOMAIN = "ir_floor_heating"
PLATFORMS = [Platform.BINARY_SENSOR, Platform.CLIMATE, Platform.SENSOR]

# Configuration parameters
CONF_HEATER = "heater"
CONF_ROOM_SENSOR = "room_sensor"
CONF_FLOOR_SENSOR = "floor_sensor"
CONF_ROOM_SENSORS = "room_sensors"
CONF_FLOOR_SENSORS = "floor_sensors"
CONF_RELAYS = "relays"
CONF_POWER_SENSORS = "power_sensors"
CONF_TARGET_TEMP = "target_temp"
CONF_MAX_FLOOR_TEMP = "max_floor_temp"
CONF_MAX_FLOOR_TEMP_DIFF = "max_floor_temp_diff"
CONF_MIN_TEMP = "min_temp"
CONF_MAX_TEMP = "max_temp"
CONF_MIN_CYCLE_DURATION = "min_cycle_duration"
CONF_CYCLE_PERIOD = "cycle_period"
CONF_KEEP_ALIVE = "keep_alive"
CONF_PRECISION = "precision"
CONF_TEMP_STEP = "target_temp_step"
CONF_INITIAL_HVAC_MODE = "initial_hvac_mode"
CONF_BOOST_MODE = "boost_mode"
CONF_BOOST_TEMP_DIFF = "boost_temp_diff"
CONF_PID_KP = "pid_kp"
CONF_PID_KI = "pid_ki"
CONF_PID_KD = "pid_kd"
CONF_FLOOR_PID_KP = "floor_pid_kp"
CONF_FLOOR_PID_KI = "floor_pid_ki"
CONF_FLOOR_PID_KD = "floor_pid_kd"
CONF_SAFETY_HYSTERESIS = "safety_hysteresis"
CONF_MAINTAIN_COMFORT_LIMIT = "maintain_comfort_limit"
CONF_SAFETY_BUDGET_CAPACITY = "safety_budget_capacity"
CONF_SAFETY_BUDGET_INTERVAL = "safety_budget_interval"

# Default values
DEFAULT_NAME = "IR floor heating"
DEFAULT_TOLERANCE = 0.1
DEFAULT_MAX_FLOOR_TEMP = 28.0  # °C - Safe for engineered wood/laminate
DEFAULT_MAX_FLOOR_TEMP_DIFF = 5.0  # °C - Maximum floor-room differential
DEFAULT_CYCLE_PERIOD = 900  # 15 minutes (4 cycles per hour for relay protection)
DEFAULT_MIN_CYCLE_DURATION = 60  # 1 minute minimum on/off time
DEFAULT_BOOST_TEMP_DIFF = (
    1.5  # °C - Relax differential limit if room is this far from target
)
DEFAULT_SAFETY_HYSTERESIS = (
    0.25  # °C - Hysteresis for safety limit to prevent chattering
)
DEFAULT_MAINTAIN_COMFORT_LIMIT = False  # Disabled by default
DEFAULT_SAFETY_BUDGET_CAPACITY = 2.0  # tokens (1 cycle = 2 toggles)
DEFAULT_SAFETY_BUDGET_INTERVAL = 300  # seconds per token (12 tokens/hour)
# PID tuning defaults (optimized for floor heating)
DEFAULT_PID_KP = 80.0  # Proportional gain
DEFAULT_PID_KI = 2.0  # Integral gain
DEFAULT_PID_KD = 15.0  # Derivative gain
# Floor Limiter PID tuning defaults (dual-PID architecture)
DEFAULT_FLOOR_PID_KP = 20.0  # Floor limiter proportional gain
DEFAULT_FLOOR_PID_KI = 0.5  # Floor limiter integral gain
DEFAULT_FLOOR_PID_KD = 10.0  # Floor limiter derivative gain
