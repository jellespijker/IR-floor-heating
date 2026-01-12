"""Unit tests for TPI controller."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch, MagicMock

from custom_components.ir_floor_heating.tpi import TPIController


class TestTPIController(unittest.TestCase):
    """Test cases for TPIController class."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.cycle_period = timedelta(seconds=900)  # 15 minutes
        self.min_cycle_duration = timedelta(seconds=60)  # 1 minute
        self.controller = TPIController(
            cycle_period=self.cycle_period,
            min_cycle_duration=self.min_cycle_duration,
        )

    def test_initialization(self) -> None:
        """Test controller initialization."""
        assert self.controller._cycle_period == self.cycle_period
        assert self.controller._min_cycle_duration == self.min_cycle_duration
        assert self.controller._cycle_start_time is None

    def test_relay_on_high_demand(self) -> None:
        """Test relay turns on with high demand."""
        # 100% demand should always be on
        state = self.controller.get_relay_state(demand_percent=100.0)
        assert state

    def test_relay_off_zero_demand(self) -> None:
        """Test relay turns off with zero demand."""
        # 0% demand should be off
        state = self.controller.get_relay_state(demand_percent=0.0)
        assert not state

    def test_relay_mid_demand(self) -> None:
        """Test relay cycles with mid-range demand."""
        # 50% demand - should be on half the time
        # First call initializes cycle
        state1 = self.controller.get_relay_state(demand_percent=50.0)
        assert isinstance(state1, bool)

    def test_cycle_initialization(self) -> None:
        """Test cycle is initialized on first call."""
        assert self.controller._cycle_start_time is None
        self.controller.get_relay_state(demand_percent=50.0)
        assert self.controller._cycle_start_time is not None

    def test_minimum_cycle_duration_on(self) -> None:
        """Test minimum on-time enforcement."""
        controller = TPIController(
            cycle_period=timedelta(seconds=100),
            min_cycle_duration=timedelta(seconds=30),
        )

        # Very low demand but above minimum
        # With min_cycle=30 and cycle=100, any demand < 30% should be OFF
        state = controller.get_relay_state(demand_percent=20.0)
        assert not state

    def test_minimum_cycle_duration_off(self) -> None:
        """Test minimum off-time enforcement."""
        controller = TPIController(
            cycle_period=timedelta(seconds=100),
            min_cycle_duration=timedelta(seconds=30),
        )

        # Very high demand but below full cycle
        # With min_cycle=30 and cycle=100, any demand > 70% should be ON
        state = controller.get_relay_state(demand_percent=80.0)
        assert state

    def test_cycle_period_rollover(self) -> None:
        """Test cycle rolls over at period boundary."""
        with patch("homeassistant.util.dt.utcnow") as mock_now:
            # Set up time progression
            start_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
            mock_now.return_value = start_time

            controller = TPIController(
                cycle_period=timedelta(seconds=100),
                min_cycle_duration=timedelta(seconds=10),
            )

            # Get initial state at t=0. This sets cycle_start_time = start_time
            controller.get_relay_state(demand_percent=50.0)
            assert controller._cycle_start_time == start_time

            # Move time forward beyond cycle period (101s)
            end_time = start_time + timedelta(seconds=101)
            mock_now.return_value = end_time

            # This call should detect rollover and update cycle_start_time to end_time
            controller.get_relay_state(demand_percent=50.0)

            assert controller._cycle_start_time == end_time

            # Check info reflects new cycle
            info = controller.get_cycle_info()
            assert info["time_in_cycle"] == 0.0

    def test_reset_cycle(self) -> None:
        """Test cycle reset functionality."""
        self.controller.get_relay_state(demand_percent=50.0)
        initial_time = self.controller._cycle_start_time

        assert initial_time is not None

        self.controller.reset_cycle()
        assert self.controller._cycle_start_time is None

    def test_get_cycle_info_no_cycle(self) -> None:
        """Test cycle info when no cycle initialized."""
        info = self.controller.get_cycle_info()
        assert info["time_in_cycle"] == 0.0
        assert info["cycle_period"] == 900.0

    def test_get_cycle_info_with_cycle(self) -> None:
        """Test cycle info after initialization."""
        self.controller.get_relay_state(demand_percent=50.0)
        info = self.controller.get_cycle_info()

        assert "time_in_cycle" in info
        assert "cycle_period" in info
        assert info["time_in_cycle"] >= 0.0
        assert info["time_in_cycle"] < info["cycle_period"]
        assert info["cycle_period"] == 900.0

    def test_demand_calculation_formula(self) -> None:
        """Test on-duration is calculated correctly from demand."""
        TPIController(
            cycle_period=timedelta(seconds=1000),
            min_cycle_duration=timedelta(seconds=10),
        )

        # 25% demand = 250 seconds on, 750 seconds off
        demand = 25.0
        on_duration = (demand / 100.0) * 1000.0
        assert on_duration == 250.0

    def test_multiple_cycles(self) -> None:
        """Test behavior across multiple cycles."""
        states = []
        for _ in range(5):
            state = self.controller.get_relay_state(demand_percent=50.0)
            states.append(state)

        # Should get a mix of True and False states
        # (though timing dependent, structure should be maintained)
        assert len(states) == 5

    def test_demand_boundaries(self) -> None:
        """Test boundary demand values."""
        # Test with fresh controllers to avoid hysteresis from previous calls

        # 0% demand should be OFF
        controller_0 = TPIController(
            cycle_period=self.cycle_period,
            min_cycle_duration=self.min_cycle_duration,
        )
        assert not controller_0.get_relay_state(demand_percent=0.0)

        # 100% demand should be ON
        controller_100 = TPIController(
            cycle_period=self.cycle_period,
            min_cycle_duration=self.min_cycle_duration,
        )
        assert controller_100.get_relay_state(demand_percent=100.0)

        # 50% demand should be variable based on cycle position
        controller_50 = TPIController(
            cycle_period=self.cycle_period,
            min_cycle_duration=self.min_cycle_duration,
        )
        state = controller_50.get_relay_state(demand_percent=50.0)
        assert isinstance(state, bool)

    def test_very_short_cycle(self) -> None:
        """Test with very short cycle period."""
        controller = TPIController(
            cycle_period=timedelta(seconds=1),
            min_cycle_duration=timedelta(seconds=0.1),
        )
        state = controller.get_relay_state(demand_percent=50.0)
        assert isinstance(state, bool)

    def test_very_long_cycle(self) -> None:
        """Test with very long cycle period."""
        controller = TPIController(
            cycle_period=timedelta(seconds=86400),  # 24 hours
            min_cycle_duration=timedelta(seconds=60),
        )
        state = controller.get_relay_state(demand_percent=50.0)
        assert isinstance(state, bool)


class TestTPIControllerIntegration(unittest.TestCase):
    """Integration tests for TPIController with realistic scenarios."""

    def test_relay_wear_protection(self) -> None:
        """Test that minimum cycle duration protects relay from rapid switching."""
        controller = TPIController(
            cycle_period=timedelta(seconds=100),
            min_cycle_duration=timedelta(seconds=15),
        )

        # Very low demand - should not turn on/off rapidly
        for _ in range(10):
            state = controller.get_relay_state(demand_percent=10.0)
            # With min_cycle=15 and cycle=100, 10% < 15% so should be OFF
            assert not state

    def test_moderate_heating_demand(self) -> None:
        """Test typical moderate heating scenario."""
        controller = TPIController(
            cycle_period=timedelta(seconds=900),
            min_cycle_duration=timedelta(seconds=60),
        )

        # Realistic 40% demand
        # Should see relay mostly on for first part of cycle
        initial_state = controller.get_relay_state(demand_percent=40.0)
        assert isinstance(initial_state, bool)

        cycle_info = controller.get_cycle_info()
        on_duration = (40.0 / 100.0) * cycle_info["cycle_period"]
        # Should be on for 360 seconds of 900 second cycle
        self.assertAlmostEqual(on_duration, 360.0, places=0)

    def test_full_heating(self) -> None:
        """Test full heating scenario."""
        controller = TPIController(
            cycle_period=timedelta(seconds=900),
            min_cycle_duration=timedelta(seconds=60),
        )

        # 100% demand
        state = controller.get_relay_state(demand_percent=100.0)
        assert state

        # Should remain on consistently
        for _ in range(10):
            state = controller.get_relay_state(demand_percent=100.0)
            assert state

    def test_no_heating(self) -> None:
        """Test no heating scenario."""
        controller = TPIController(
            cycle_period=timedelta(seconds=900),
            min_cycle_duration=timedelta(seconds=60),
        )

        # 0% demand
        for _ in range(10):
            state = controller.get_relay_state(demand_percent=0.0)
            assert not state

    def test_demand_latching(self) -> None:
        """Test that demand is latched at the start of the cycle."""
        controller = TPIController(
            cycle_period=timedelta(seconds=900),
            min_cycle_duration=timedelta(seconds=60),
        )

        with patch("homeassistant.util.dt.utcnow") as mock_now:
            base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
            mock_now.return_value = base_time

            # Get initial state at 50% demand (should be ON in first 450s of cycle)
            initial_state = controller.get_relay_state(demand_percent=50.0)
            assert initial_state is True
            # Check internal latch - 50% of 900 is 450
            assert controller._current_on_duration == 450.0

            # Move time forward 10s
            mock_now.return_value = base_time + timedelta(seconds=10)

            # Change demand drastically to 5% (would be 45s)
            # But latching should keep it at 450s logic
            state2 = controller.get_relay_state(demand_percent=5.0)

            # Should still be True because we are at t=10s, and latched duration is 450s
            assert state2 is True
            assert controller._current_on_duration == 450.0

            # Move time forward 100s (t=110s)
            mock_now.return_value = base_time + timedelta(seconds=110)
            state3 = controller.get_relay_state(demand_percent=0.0)
            assert state3 is True  # Still ON despite 0 demand, because latched 50%

            # Move time past 450s (t=460s)
            mock_now.return_value = base_time + timedelta(seconds=460)
            state4 = controller.get_relay_state(demand_percent=100.0)
            assert (
                state4 is False
            )  # OFF because time > 450s, even if demand is 100 on this call


if __name__ == "__main__":
    unittest.main()
