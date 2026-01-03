"""Unit tests for PID controller."""

from __future__ import annotations

import unittest

from custom_components.ir_floor_heating.pid import PIDController


class TestPIDController(unittest.TestCase):
    """Test cases for PIDController class."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.controller = PIDController(kp=80.0, ki=2.0, kd=15.0, name="TestPID")

    def test_initialization(self) -> None:
        """Test controller initialization."""
        assert self.controller._kp == 80.0
        assert self.controller._ki == 2.0
        assert self.controller._kd == 15.0
        assert self.controller._name == "TestPID"
        assert self.controller._integral_error == 0.0
        assert self.controller._last_process_variable is None

    def test_proportional_only(self) -> None:
        """Test proportional term calculation."""
        controller = PIDController(kp=10.0, ki=0.0, kd=0.0)
        # Error = 10 - 0 = 10, P_term = 10 * 10 = 100
        result = controller.calculate(setpoint=10.0, process_variable=0.0, dt=1.0)
        assert result == 100.0  # Clamped to max 100%

    def test_proportional_negative_error(self) -> None:
        """Test proportional with negative error (cooling)."""
        controller = PIDController(kp=10.0, ki=0.0, kd=0.0)
        # Error = 15 - 20 = -5, P_term = 10 * -5 = -50, clamped to 0
        result = controller.calculate(setpoint=15.0, process_variable=20.0, dt=1.0)
        assert result == 0.0

    def test_integral_accumulation(self) -> None:
        """Test integral term accumulation."""
        controller = PIDController(kp=0.0, ki=1.0, kd=0.0)
        # First call: error = 5, integral = 5, i_term = 1 * 5 = 5
        result1 = controller.calculate(setpoint=5.0, process_variable=0.0, dt=1.0)
        assert result1 == 5.0

        # Second call: error = 5, integral = 5 + 5 = 10, i_term = 1 * 10 = 10
        result2 = controller.calculate(setpoint=5.0, process_variable=0.0, dt=1.0)
        assert result2 == 10.0

        # Third call: error = 5, integral = 10 + 5 = 15, i_term = 1 * 15 = 15
        result3 = controller.calculate(setpoint=5.0, process_variable=0.0, dt=1.0)
        assert result3 == 15.0

    def test_integral_windup_clamping(self) -> None:
        """Test integral windup prevention."""
        controller = PIDController(kp=0.0, ki=1.0, kd=0.0)
        # Repeatedly call with large error - integral should be clamped
        for _ in range(150):
            result = controller.calculate(setpoint=100.0, process_variable=0.0, dt=1.0)

        # With ki=1.0, max_integral = 100 / 1.0 = 100
        # So result should never exceed 100
        assert result <= 100.0
        assert result == 100.0

    def test_integral_zero_ki(self) -> None:
        """Test that zero Ki doesn't cause division by zero."""
        controller = PIDController(kp=10.0, ki=0.0, kd=0.0)
        # Should not raise an exception
        result = controller.calculate(setpoint=10.0, process_variable=0.0, dt=1.0)
        assert result == 100.0  # Clamped to max (kp * error = 10 * 10 = 100)

    def test_derivative_term(self) -> None:
        """Test derivative term calculation."""
        controller = PIDController(kp=0.0, ki=0.0, kd=10.0)

        # First call: no previous PV, so derivative = 0
        result1 = controller.calculate(setpoint=20.0, process_variable=0.0, dt=1.0)
        assert result1 == 0.0

        # Second call: PV changed from 0 to 5, pv_change = 5
        # d_term = -10 * 5 / 1 = -50, clamped to 0
        result2 = controller.calculate(setpoint=20.0, process_variable=5.0, dt=1.0)
        assert result2 == 0.0

    def test_combined_pid(self) -> None:
        """Test combined PID calculation."""
        controller = PIDController(kp=1.0, ki=0.5, kd=2.0)

        # First calculation with error = 10
        # P = 1 * 10 = 10
        # I = 0.5 * 10 * 1 = 5
        # D = 0 (no previous PV)
        # Total = 15
        result1 = controller.calculate(setpoint=10.0, process_variable=0.0, dt=1.0)
        self.assertAlmostEqual(result1, 15.0, places=5)

        # Second calculation with error = 0 (at setpoint)
        # P = 1 * 0 = 0
        # I = 0.5 * (10 + 0) * 1 = 5
        # D = -2 * (5 - 0) / 1 = -10, clamped to 0
        # Total = 0 + 5 - 10 = -5, clamped to 0
        result2 = controller.calculate(setpoint=5.0, process_variable=5.0, dt=1.0)
        self.assertAlmostEqual(result2, 0.0, places=5)

    def test_output_clamping(self) -> None:
        """Test output is clamped to 0-100%."""
        controller = PIDController(kp=1000.0, ki=0.0, kd=0.0)
        # Very large error should clamp to 100
        result = controller.calculate(setpoint=100.0, process_variable=0.0, dt=1.0)
        assert result == 100.0

    def test_pause_integration(self) -> None:
        """Test pause_integration resets integral error."""
        controller = PIDController(kp=0.0, ki=1.0, kd=0.0)

        # Accumulate integral error
        controller.calculate(setpoint=10.0, process_variable=0.0, dt=1.0)
        controller.calculate(setpoint=10.0, process_variable=0.0, dt=1.0)
        assert controller.get_integral_error() == 20.0

        # Pause integration
        controller.pause_integration()
        assert controller.get_integral_error() == 0.0

    def test_get_integral_error(self) -> None:
        """Test getting integral error value."""
        controller = PIDController(kp=0.0, ki=1.0, kd=0.0)
        initial = controller.get_integral_error()
        assert initial == 0.0

        controller.calculate(setpoint=5.0, process_variable=0.0, dt=1.0)
        after_first = controller.get_integral_error()
        assert after_first == 5.0

    def test_reset(self) -> None:
        """Test reset functionality."""
        controller = PIDController(kp=0.0, ki=1.0, kd=0.0)

        # Accumulate state
        controller.calculate(setpoint=10.0, process_variable=0.0, dt=1.0)
        controller.calculate(setpoint=10.0, process_variable=5.0, dt=1.0)

        # Reset
        controller.reset()
        assert controller.get_integral_error() == 0.0
        assert controller._last_process_variable is None

    def test_delta_time_handling(self) -> None:
        """Test different delta time values."""
        controller = PIDController(kp=0.0, ki=1.0, kd=0.0)

        # Calculate with dt=2.0
        # error = 10, integral = 10 * 2 = 20
        result = controller.calculate(setpoint=10.0, process_variable=0.0, dt=2.0)
        assert result == 20.0

    def test_setpoint_tracking(self) -> None:
        """Test controller tracks toward setpoint."""
        controller = PIDController(kp=10.0, ki=0.1, kd=1.0)

        # Simulate approaching setpoint
        demands = []
        pv = 0.0
        setpoint = 20.0

        for _ in range(10):
            demand = controller.calculate(
                setpoint=setpoint, process_variable=pv, dt=1.0
            )
            demands.append(demand)
            # Simulate system response: PV approaches demand
            pv += (demand / 100.0) * 2.0

        # Demand should start high and decrease as we approach setpoint
        assert demands[0] > demands[-1]

    def test_zero_time_delta(self) -> None:
        """Test handling of zero time delta."""
        controller = PIDController(kp=1.0, ki=1.0, kd=1.0)
        # Should not raise exception with dt=0
        result = controller.calculate(setpoint=10.0, process_variable=0.0, dt=0.0)
        # Derivative term should be 0 with dt=0
        assert isinstance(result, float)

    def test_steady_state(self) -> None:
        """Test steady state behavior."""
        controller = PIDController(kp=1.0, ki=0.1, kd=0.5)

        # Reach steady state
        pv = 20.0
        for _ in range(20):
            controller.calculate(setpoint=20.0, process_variable=pv, dt=1.0)

        # At setpoint, demand should be near zero
        result = controller.calculate(setpoint=20.0, process_variable=20.0, dt=1.0)
        assert result < 5.0


class TestPIDControllerEdgeCases(unittest.TestCase):
    """Edge case tests for PIDController."""

    def test_very_small_ki(self) -> None:
        """Test with very small Ki value."""
        controller = PIDController(kp=1.0, ki=0.001, kd=0.0)
        result = controller.calculate(setpoint=10.0, process_variable=0.0, dt=1.0)
        assert isinstance(result, float)

    def test_negative_error_zero_output(self) -> None:
        """Test negative errors produce zero output."""
        controller = PIDController(kp=10.0, ki=0.0, kd=0.0)
        # PV above setpoint
        result = controller.calculate(setpoint=10.0, process_variable=20.0, dt=1.0)
        assert result == 0.0

    def test_large_derivative_change(self) -> None:
        """Test handling large derivative changes."""
        controller = PIDController(kp=0.0, ki=0.0, kd=100.0)

        # First call
        controller.calculate(setpoint=20.0, process_variable=0.0, dt=1.0)

        # Large PV change
        result = controller.calculate(setpoint=20.0, process_variable=15.0, dt=1.0)
        assert result == 0.0  # Negative derivative term, clamped


if __name__ == "__main__":
    unittest.main()
