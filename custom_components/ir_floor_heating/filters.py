"""Kalman filter for sensor fusion."""

from dataclasses import dataclass

import numpy as np
from filterpy.common import Q_discrete_white_noise
from filterpy.kalman import KalmanFilter

# Small epsilon for dt comparisons
DT_EPSILON = 1e-4


@dataclass
class KalmanTuning:
    """Tuning parameters for the Kalman Filter."""

    kf_floor_gain: float = 0.0001
    kf_room_gain: float = 0.00001
    q_var_floor: float = 0.001
    q_var_room: float = 0.0001
    r_var: float = 0.1


class FusionKalmanFilter:
    """
    MIMO Kalman Filter for Sensor Fusion of floor and room temperatures.

    The state vector x is defined as:
    x = [T_floor, T_floor_dot, T_room, T_room_dot]^T
    where:
    - T_floor: Floor temperature (°C)
    - T_floor_dot: Floor temperature rate of change (°C/s)
    - T_room: Room temperature (°C)
    - T_room_dot: Room temperature rate of change (°C/s)

    The mathematical matrices H and R are constructed dynamically based on the
    number of available sensors during each update step.
    """

    def __init__(
        self,
        num_floor_sensors: int,
        num_room_sensors: int,
        dt: float = 60.0,
        tuning: KalmanTuning | None = None,
    ) -> None:
        """
        Initialize the FusionKalmanFilter.

        Args:
            num_floor_sensors: Maximum number of floor sensors.
            num_room_sensors: Maximum number of room sensors.
            dt: Default time step in seconds.
            tuning: Tuning parameters for the filter.

        """
        if tuning is None:
            tuning = KalmanTuning()

        self.dt = dt
        self.num_floor = num_floor_sensors
        self.num_room = num_room_sensors
        self.kf_floor_gain = tuning.kf_floor_gain
        self.kf_room_gain = tuning.kf_room_gain
        self.r_var = tuning.r_var
        self.q_var_floor = tuning.q_var_floor
        self.q_var_room = tuning.q_var_room

        # State vector dimension: 4, Measurement dimension: M + N
        self.kf = KalmanFilter(dim_x=4, dim_z=num_floor_sensors + num_room_sensors)

        # State Transition Matrix (F): Newtonian kinematics
        self.kf.F = np.array([[1, dt, 0, 0], [0, 1, 0, 0], [0, 0, 1, dt], [0, 0, 0, 1]])

        # Control Input Matrix (B): Mapping power (Watts) to state
        # We assume power affects the rate of change.
        self.kf.B = np.array(
            [
                [0.5 * self.kf_floor_gain * dt**2],
                [self.kf_floor_gain * dt],
                [0.5 * self.kf_room_gain * dt**2],
                [self.kf_room_gain * dt],
            ]
        )

        # Measurement Matrix (H): Mapping state to observations
        self._update_h_matrix(num_floor_sensors, num_room_sensors)

        # Measurement Noise (R): Initially diagonal
        self.kf.R = np.eye(self.kf.dim_z) * self.r_var

        # Process Noise (Q): Using block diagonal discrete white noise
        self._update_q_matrix(dt, self.q_var_floor, self.q_var_room)

        # Initial state estimation: [20, 0, 20, 0]
        self.kf.x = np.array([[20.0, 0.0, 20.0, 0.0]]).T
        self.kf.P *= 10.0

    def _update_h_matrix(self, m: int, n: int) -> None:
        """Construct the measurement matrix H dynamically."""
        h = np.zeros((m + n, 4))
        # Rows 0 to M-1 map to T_floor (index 0)
        for i in range(m):
            h[i, 0] = 1
        # Rows M to M+N-1 map to T_room (index 2)
        for i in range(n):
            h[m + i, 2] = 1
        self.kf.H = h

    def _update_q_matrix(self, dt: float, var_floor: float, var_room: float) -> None:
        """Update the process noise matrix Q."""
        q_floor = Q_discrete_white_noise(dim=2, dt=dt, var=var_floor)
        q_room = Q_discrete_white_noise(dim=2, dt=dt, var=var_room)
        self.kf.Q = np.block([[q_floor, np.zeros((2, 2))], [np.zeros((2, 2)), q_room]])

    def update(
        self,
        floor_values: list[float | None],
        room_values: list[float | None],
        power: float,
        dt: float | None = None,
    ) -> None:
        """
        Perform prediction and update steps with dynamic sensor gating.

        The measurement matrix H and noise matrix R are reconstructed during
        each update step to include only the sensors that provided a valid
        numeric reading (i.e., not None). This implementation follows the
        MIMO (Multi-Input Multi-Output) structure where multiple sensors
        of the same type are fused into a single state estimation.

        Args:
            floor_values: List of temperature readings from floor sensors.
            room_values: List of temperature readings from room sensors.
            power: Total heating power in Watts.
            dt: Time delta since last update in seconds.

        """
        if dt is not None and dt > 0 and abs(dt - self.dt) > DT_EPSILON:
            self.dt = dt
            self.kf.F[0, 1] = dt
            self.kf.F[2, 3] = dt
            self.kf.B[0, 0] = 0.5 * self.kf_floor_gain * dt**2
            self.kf.B[1, 0] = self.kf_floor_gain * dt
            self.kf.B[2, 0] = 0.5 * self.kf_room_gain * dt**2
            self.kf.B[3, 0] = self.kf_room_gain * dt
            self._update_q_matrix(dt, self.q_var_floor, self.q_var_room)

        # 1. Prediction Step
        self.kf.predict(u=np.array([[power]]))

        # 2. Prepare valid measurements (Gating)
        z = []
        valid_indices = []

        # Collect valid floor measurements
        for i, val in enumerate(floor_values):
            if val is not None:
                z.append(val)
                valid_indices.append(i)

        # Collect valid room measurements
        for i, val in enumerate(room_values):
            if val is not None:
                z.append(val)
                valid_indices.append(self.num_floor + i)

        if not z:
            return

        # 3. Dynamic construction of H and R for this update
        num_valid = len(z)
        h_v = np.zeros((num_valid, 4))
        for i, idx in enumerate(valid_indices):
            if idx < self.num_floor:
                h_v[i, 0] = 1  # Map to T_floor
            else:
                h_v[i, 2] = 1  # Map to T_room

        r_v = np.eye(num_valid) * self.r_var

        # 4. Update Step
        self.kf.update(np.array(z), R=r_v, H=h_v)

    @property
    def x(self) -> np.ndarray:
        """Get the current state vector."""
        return self.kf.x.flatten()

    @property
    def floor_temp(self) -> float:
        """Fused floor temperature."""
        return float(self.kf.x[0])

    @property
    def room_temp(self) -> float:
        """Fused room temperature."""
        return float(self.kf.x[2])
