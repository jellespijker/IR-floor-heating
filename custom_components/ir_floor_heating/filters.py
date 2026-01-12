"""Kalman filter for sensor fusion."""

from dataclasses import dataclass

import numpy as np
from filterpy.common import Q_discrete_white_noise
from filterpy.kalman import KalmanFilter

# Small epsilon for dt comparisons
DT_EPSILON = 1e-4


@dataclass
class KalmanTuning:
    """
    Tuning parameters for a slower, more stable response.

    Lower gain = slower reaction to power.
    Lower Q = smoother state transitions (less jitter).
    Higher R = more immunity to sensor noise.
    """

    # Reduced gains for a slower build-up
    kf_floor_gain: float = 0.00001  # Reduced from 0.0001
    kf_room_gain: float = 0.000001  # Reduced from 0.00001

    # Process noise: Lowering these makes the filter "stiffer" (ignores spikes)
    q_var_floor: float = 0.0001  # Reduced from 0.001
    q_var_room: float = 0.00001  # Reduced from 0.0001

    # Measurement noise: Increasing this helps filter out "touch noise"
    r_var: float = 0.5  # Increased from 0.1


class FusionKalmanFilter:
    """MIMO Kalman Filter with damped power response."""

    def __init__(
        self,
        num_floor_sensors: int,
        num_room_sensors: int,
        dt: float = 60.0,
        tuning: KalmanTuning | None = None,
    ) -> None:
        """Initialize the FusionKalmanFilter."""
        if tuning is None:
            tuning = KalmanTuning()

        self.dt = dt
        self.num_floor = num_floor_sensors
        self.num_room = num_room_sensors

        # Store tuning
        self.tuning = tuning

        self.kf = KalmanFilter(dim_x=4, dim_z=num_floor_sensors + num_room_sensors)

        # State Transition Matrix (F): Constant Velocity Model
        self.kf.F = np.array([[1, dt, 0, 0], [0, 1, 0, 0], [0, 0, 1, dt], [0, 0, 0, 1]])

        # Update B and Q matrices
        self._update_matrices(dt)

        # Measurement Matrix (H)
        self._update_h_matrix(num_floor_sensors, num_room_sensors)

        # Initial Uncertainty: Set high to allow initial convergence,
        # but the filter will tighten up quickly.
        self.kf.P *= 5.0

        # Reasonable initial state
        self.kf.x = np.array([[20.0, 0.0, 20.0, 0.0]]).T

    def _update_matrices(self, dt: float) -> None:
        """Update B and Q matrices based on current dt and tuning."""
        # Control Input Matrix (B)
        self.kf.B = np.array(
            [
                [0.5 * self.tuning.kf_floor_gain * dt**2],
                [self.tuning.kf_floor_gain * dt],
                [0.5 * self.tuning.kf_room_gain * dt**2],
                [self.tuning.kf_room_gain * dt],
            ]
        )

        # Process Noise (Q)
        q_floor = Q_discrete_white_noise(dim=2, dt=dt, var=self.tuning.q_var_floor)
        q_room = Q_discrete_white_noise(dim=2, dt=dt, var=self.tuning.q_var_room)
        self.kf.Q = np.block([[q_floor, np.zeros((2, 2))], [np.zeros((2, 2)), q_room]])

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

    def update(
        self,
        floor_values: list[float | None],
        room_values: list[float | None],
        power: float,
        dt: float | None = None,
    ) -> None:
        """Perform prediction and update steps with dynamic sensor gating."""
        if dt is not None and dt > 0 and abs(dt - self.dt) > DT_EPSILON:
            self.dt = dt
            self.kf.F[0, 1] = dt
            self.kf.F[2, 3] = dt
            self._update_matrices(dt)

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

        r_v = np.eye(num_valid) * self.tuning.r_var

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
