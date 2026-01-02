"""Constants for the IR floor heating integration."""

from homeassistant.const import Platform

DOMAIN = "ir_floor_heating"
PLATFORMS = [Platform.CLIMATE, Platform.SENSOR]

# Configuration parameters
CONF_HEATER = "heater"
CONF_ROOM_SENSOR = "room_sensor"
CONF_FLOOR_SENSOR = "floor_sensor"
CONF_TARGET_TEMP = "target_temp"
CONF_MAX_FLOOR_TEMP = "max_floor_temp"
CONF_MAX_FLOOR_TEMP_DIFF = "max_floor_temp_diff"
CONF_MIN_TEMP = "min_temp"  # TODO: Implement in climate
CONF_MAX_TEMP = "max_temp"  # TODO: Implement in climate
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
CONF_SAFETY_HYSTERESIS = "safety_hysteresis"

# Default values
DEFAULT_NAME = "IR floor heating"
DEFAULT_TOLERANCE = 0.3
DEFAULT_MAX_FLOOR_TEMP = 28.0  # °C - Safe for engineered wood/laminate
DEFAULT_MAX_FLOOR_TEMP_DIFF = 5.0  # °C - Maximum floor-room differential
DEFAULT_CYCLE_PERIOD = (
    600
)  # 10 minutes (6 cycles per hour for relay protection)
DEFAULT_MIN_CYCLE_DURATION = 60  # 1 minute minimum on/off time
DEFAULT_BOOST_TEMP_DIFF = (
    2.0  # °C - Relax differential limit if room is this far from target
)
DEFAULT_SAFETY_HYSTERESIS = (
    0.25  # °C - Hysteresis for safety limit to prevent chattering
)
# PID tuning defaults (optimized for floor heating)
DEFAULT_PID_KP = 10.0  # Proportional gain
DEFAULT_PID_KI = 0.5  # Integral gain
DEFAULT_PID_KD = 0.0  # Derivative gain
