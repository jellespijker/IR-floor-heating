"""
Kalman filter for sensor fusion.

Implemented locally instead of depending on filterpy: filterpy.kalman
unconditionally imports filterpy.common, which unconditionally imports
scipy.linalg at module load time even though we only need a linear
predict/update and one closed-form noise matrix. That made this
integration's setup fail outright on any environment where scipy has no
prebuilt wheel (e.g. a brand-new CPython release) and has to be built
from source.
"""

from dataclasses import dataclass

import numpy as np

# Small epsilon for dt comparisons
DT_EPSILON = 1e-4


def _q_discrete_white_noise(dt: float, var: float) -> np.ndarray:
    """
    Process noise for a discretized constant-velocity (position/velocity) model.

    Closed form for dim=2, block_size=1 from filterpy.common.Q_discrete_white_noise
    (Bar-Shalom, "Estimation with Applications to Tracking and Navigation", 2001,
    p. 274).
    """
    return var * np.array([[0.25 * dt**4, 0.5 * dt**3], [0.5 * dt**3, dt**2]])


class _LinearKalmanFilter:
    """
    Minimal linear Kalman filter, covering only predict/update.

    Ported from filterpy.kalman.KalmanFilter's predict()/update() (MIT
    licensed, Roger R Labbe Jr) for the subset of behavior FusionKalmanFilter
    relies on: a control-input predict step and a Joseph-form measurement
    update with an explicit H/R override.
    """

    def __init__(self, dim_x: int, dim_z: int) -> None:
        self.dim_x = dim_x
        self.x = np.zeros((dim_x, 1))
        self.P = np.eye(dim_x)
        self.Q = np.eye(dim_x)
        self.B: np.ndarray | None = None
        self.F = np.eye(dim_x)
        self.H = np.zeros((dim_z, dim_x))

    def predict(self, u: np.ndarray | None = None) -> None:
        """Advance the state estimate: x = Fx + Bu, P = FPF' + Q."""
        if self.B is not None and u is not None:
            self.x = self.F @ self.x + self.B @ u
        else:
            self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + self.Q

    def update(self, z: np.ndarray, r: np.ndarray, h: np.ndarray) -> None:
        """Fold in a measurement using the (numerically stable) Joseph form."""
        y = z - h @ self.x
        pht = self.P @ h.T
        s = h @ pht + r
        k = pht @ np.linalg.inv(s)
        self.x = self.x + k @ y
        i_kh = np.eye(self.dim_x) - k @ h
        self.P = i_kh @ self.P @ i_kh.T + k @ r @ k.T


@dataclass
class KalmanTuning:
    """Tuning for damped thermal mass model with nano-gains."""

    # 1. NANO-GAINS: Align 1000W with slow-heating thermal mass
    # Previous gains caused "Rocket Effect" - temperature acceleration was too
    # aggressive. These values prevent runaway velocity buildup.
    kf_floor_gain: float = 1e-9  # Was 1e-5
    kf_room_gain: float = 1e-10  # Was 1e-6

    # 2. HEAVY INERTIA: Trust the physical trend over jumps
    # Lower Q makes the filter rely on smooth predictions rather than sensor jumps.
    q_var_floor: float = 1e-7  # Was 1e-5
    q_var_room: float = 1e-8  # Was 1e-6

    # 3. DIFFERENTIATED SENSOR TRUST
    # Floor sensor is jittery (high R), room sensors are accurate (low R).
    r_var_floor: float = 1.5  # High R to smooth floor jitter
    r_var_room: float = 0.1  # Low R to track accurate room sensors


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

        self.kf = _LinearKalmanFilter(
            dim_x=4, dim_z=num_floor_sensors + num_room_sensors
        )

        # State Transition Matrix (F) will be set in _update_matrices with damping
        # Initialize with damped model
        damping = 0.95
        self.kf.F = np.array(
            [[1, dt, 0, 0], [0, damping, 0, 0], [0, 0, 1, dt], [0, 0, 0, damping]]
        )

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
        """Update F, B and Q matrices based on current dt and tuning."""
        # State Transition Matrix (F): Introduce damping to velocity states
        # This prevents the "Rocket Effect" by decaying the rate of change.
        # Without damping, velocity accumulates indefinitely causing runaway
        # temperatures.
        damping = 0.95
        self.kf.F = np.array(
            [
                [1, dt, 0, 0],  # Floor position influenced by velocity
                [0, damping, 0, 0],  # Floor velocity with damping (decay)
                [0, 0, 1, dt],  # Room position influenced by velocity
                [0, 0, 0, damping],  # Room velocity with damping (decay)
            ]
        )

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
        q_floor = _q_discrete_white_noise(dt, self.tuning.q_var_floor)
        q_room = _q_discrete_white_noise(dt, self.tuning.q_var_room)
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
        r_diag = []

        for i, idx in enumerate(valid_indices):
            if idx < self.num_floor:
                h_v[i, 0] = 1  # Map to T_floor
                r_diag.append(self.tuning.r_var_floor)
            else:
                h_v[i, 2] = 1  # Map to T_room
                r_diag.append(self.tuning.r_var_room)

        r_v = np.diag(r_diag)

        # 4. Update Step
        # H and R are sized to the gated (possibly shorter) measurement count;
        # update() derives K/S from them directly, so no separate dim_z
        # bookkeeping is needed.
        self.kf.update(np.array(z).reshape(num_valid, 1), r=r_v, h=h_v)

    @property
    def x(self) -> np.ndarray:
        """Get the current state vector."""
        return self.kf.x.flatten()

    @property
    def floor_temp(self) -> float:
        """Fused floor temperature."""
        return float(self.kf.x[0, 0])

    @property
    def room_temp(self) -> float:
        """Fused room temperature."""
        return float(self.kf.x[2, 0])
