"""Unit tests for the HeaterShuffler cascading power bucket algorithm."""

import pytest
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

from homeassistant.core import HomeAssistant

from ..heater_manager import Heater, HeaterShuffler


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock(spec=HomeAssistant)
    hass.services.async_call = AsyncMock()
    hass.states.get = MagicMock(return_value=None)
    hass.states.is_state = MagicMock(return_value=False)
    return hass


@pytest.fixture
def basic_heaters():
    """Create basic heater list for testing."""
    return [
        Heater(entity_id="switch.heater_1", power=1500.0, name="Heater 1"),
        Heater(entity_id="switch.heater_2", power=1500.0, name="Heater 2"),
    ]


@pytest.fixture
def unequal_heaters():
    """Create heaters with unequal power ratings."""
    return [
        Heater(entity_id="switch.heater_1", power=2000.0, name="Large Heater"),
        Heater(entity_id="switch.heater_2", power=1000.0, name="Small Heater"),
        Heater(entity_id="switch.heater_3", power=500.0, name="Tiny Heater"),
    ]


class TestHeaterShufflerInitialization:
    """Test HeaterShuffler initialization."""

    def test_init_with_valid_heaters(self, mock_hass, basic_heaters):
        """Test successful initialization."""
        shuffler = HeaterShuffler(
            hass=mock_hass,
            heaters=basic_heaters,
            cycle_period=timedelta(seconds=900),
            min_cycle_duration=timedelta(seconds=60),
        )
        assert shuffler.hass == mock_hass
        assert len(shuffler.heaters) == 2
        assert shuffler._total_capacity == 3000.0

    def test_init_fails_without_heaters(self, mock_hass):
        """Test initialization fails with empty heater list."""
        with pytest.raises(ValueError, match="At least one heater must be configured"):
            HeaterShuffler(
                hass=mock_hass,
                heaters=[],
                cycle_period=timedelta(seconds=900),
                min_cycle_duration=timedelta(seconds=60),
            )

    def test_total_capacity_calculation(self, mock_hass, unequal_heaters):
        """Test total capacity is correctly calculated."""
        shuffler = HeaterShuffler(
            hass=mock_hass,
            heaters=unequal_heaters,
            cycle_period=timedelta(seconds=900),
            min_cycle_duration=timedelta(seconds=60),
        )
        assert shuffler._total_capacity == 3500.0  # 2000 + 1000 + 500


class TestCascadingPowerBucket:
    """Test the cascading power bucket algorithm."""

    @pytest.mark.asyncio
    async def test_100_percent_demand_all_heaters_on(self, mock_hass, unequal_heaters):
        """Test 100% demand turns on all heaters."""
        shuffler = HeaterShuffler(
            hass=mock_hass,
            heaters=unequal_heaters,
            cycle_period=timedelta(seconds=900),
            min_cycle_duration=timedelta(seconds=60),
        )

        # Apply 100% demand
        heater_states = await shuffler.async_apply_demand(100.0)

        # All heaters should be ON at 100%
        assert len(heater_states) == 3
        for entity_id, state in heater_states.items():
            assert state.should_be_on is True
            assert state.duty_cycle == 100.0

    @pytest.mark.asyncio
    async def test_zero_demand_all_heaters_off(self, mock_hass, unequal_heaters):
        """Test 0% demand turns off all heaters."""
        shuffler = HeaterShuffler(
            hass=mock_hass,
            heaters=unequal_heaters,
            cycle_period=timedelta(seconds=900),
            min_cycle_duration=timedelta(seconds=60),
        )

        # Apply 0% demand
        heater_states = await shuffler.async_apply_demand(0.0)

        # All heaters should be OFF
        assert len(heater_states) == 3
        for entity_id, state in heater_states.items():
            assert state.should_be_on is False
            assert state.duty_cycle == 0.0

    @pytest.mark.asyncio
    async def test_50_percent_demand_equal_heaters(self, mock_hass, basic_heaters):
        """Test 50% demand with equal heaters = one heater ON, one OFF."""
        shuffler = HeaterShuffler(
            hass=mock_hass,
            heaters=basic_heaters,
            cycle_period=timedelta(seconds=900),
            min_cycle_duration=timedelta(seconds=60),
        )

        # Apply 50% demand (1500W out of 3000W total)
        heater_states = await shuffler.async_apply_demand(50.0)

        # First heater should be ON (1500W), second should be OFF
        assert heater_states["switch.heater_1"].should_be_on is True
        assert heater_states["switch.heater_1"].duty_cycle == 100.0
        assert heater_states["switch.heater_2"].should_be_on is False
        assert heater_states["switch.heater_2"].duty_cycle == 0.0

    @pytest.mark.asyncio
    async def test_fractional_demand_uses_tpi(self, mock_hass, basic_heaters):
        """Test fractional demand uses TPI on last heater."""
        shuffler = HeaterShuffler(
            hass=mock_hass,
            heaters=basic_heaters,
            cycle_period=timedelta(seconds=900),
            min_cycle_duration=timedelta(seconds=60),
        )

        # Apply 75% demand (2250W out of 3000W)
        # Should be: Heater 1 ON 100%, Heater 2 ON 50%
        heater_states = await shuffler.async_apply_demand(75.0)

        assert heater_states["switch.heater_1"].should_be_on is True
        assert heater_states["switch.heater_1"].duty_cycle == 100.0
        # Second heater gets 750W of its 1500W capacity = 50% duty
        assert heater_states["switch.heater_2"].duty_cycle == pytest.approx(50.0, abs=1.0)

    @pytest.mark.asyncio
    async def test_unequal_heater_cascading(self, mock_hass, unequal_heaters):
        """Test cascading with unequal power heaters."""
        shuffler = HeaterShuffler(
            hass=mock_hass,
            heaters=unequal_heaters,
            cycle_period=timedelta(seconds=900),
            min_cycle_duration=timedelta(seconds=60),
        )

        # Apply 80% demand (2800W out of 3500W)
        # Should be: Large(2000W) ON, Small(1000W) needs 800W = 80% of 1000
        heater_states = await shuffler.async_apply_demand(80.0)

        assert heater_states["switch.heater_1"].should_be_on is True  # Large heater
        assert heater_states["switch.heater_1"].duty_cycle == 100.0
        assert heater_states["switch.heater_3"].should_be_on is False  # Tiny heater off
        # Small heater gets partial duty
        assert heater_states["switch.heater_2"].duty_cycle == pytest.approx(80.0, abs=1.0)

    @pytest.mark.asyncio
    async def test_demand_clamping(self, mock_hass, basic_heaters):
        """Test that invalid demand values are clamped."""
        shuffler = HeaterShuffler(
            hass=mock_hass,
            heaters=basic_heaters,
            cycle_period=timedelta(seconds=900),
            min_cycle_duration=timedelta(seconds=60),
        )

        # Apply negative demand (should clamp to 0%)
        heater_states = await shuffler.async_apply_demand(-50.0)
        assert all(not state.should_be_on for state in heater_states.values())

        # Apply over-100% demand (should clamp to 100%)
        heater_states = await shuffler.async_apply_demand(150.0)
        assert all(state.should_be_on for state in heater_states.values())


class TestHeaterRotation:
    """Test the heater priority rotation mechanism."""

    def test_rotation_order_increments(self, mock_hass, basic_heaters):
        """Test that rotation index increments."""
        shuffler = HeaterShuffler(
            hass=mock_hass,
            heaters=basic_heaters,
            cycle_period=timedelta(seconds=900),
            min_cycle_duration=timedelta(seconds=60),
        )

        # Get initial priority
        initial_priority = [h.entity_id for h in shuffler._get_prioritized_heaters()]
        assert initial_priority == ["switch.heater_1", "switch.heater_2"]

        # Increment rotation
        shuffler._rotation_index += 1

        # Get new priority (rotated)
        rotated_priority = [h.entity_id for h in shuffler._get_prioritized_heaters()]
        assert rotated_priority == ["switch.heater_2", "switch.heater_1"]

    def test_rotation_wraps_around(self, mock_hass, basic_heaters):
        """Test that rotation wraps around correctly."""
        shuffler = HeaterShuffler(
            hass=mock_hass,
            heaters=basic_heaters,
            cycle_period=timedelta(seconds=900),
            min_cycle_duration=timedelta(seconds=60),
        )

        # Rotate twice (should be back to original)
        shuffler._rotation_index = 2
        priority = [h.entity_id for h in shuffler._get_prioritized_heaters()]
        assert priority == ["switch.heater_1", "switch.heater_2"]

    @pytest.mark.asyncio
    async def test_rotation_prevents_wear_imbalance(self, mock_hass, basic_heaters):
        """Test that rotation prevents one heater from always being the TPI heater."""
        shuffler = HeaterShuffler(
            hass=mock_hass,
            heaters=basic_heaters,
            cycle_period=timedelta(seconds=900),
            min_cycle_duration=timedelta(seconds=60),
        )

        # Apply 60% demand (1800W out of 3000W)
        # Without rotation: Heater 1 ON, Heater 2 ON 20%
        states_1 = await shuffler.async_apply_demand(60.0)
        tpi_heater_1 = next(
            (s.entity_id for s in states_1.values() if 0 < s.duty_cycle < 100),
            None,
        )

        # Rotate and apply same demand
        # Heater 2 should now be the TPI heater
        shuffler._rotation_index = 1
        states_2 = await shuffler.async_apply_demand(60.0)
        tpi_heater_2 = next(
            (s.entity_id for s in states_2.values() if 0 < s.duty_cycle < 100),
            None,
        )

        # The TPI heater should be different after rotation
        assert tpi_heater_1 != tpi_heater_2


class TestToggleTracking:
    """Test toggle count tracking."""

    def test_toggle_count_initialization(self, mock_hass, basic_heaters):
        """Test that toggle counts are initialized to zero."""
        shuffler = HeaterShuffler(
            hass=mock_hass,
            heaters=basic_heaters,
            cycle_period=timedelta(seconds=900),
            min_cycle_duration=timedelta(seconds=60),
        )

        assert shuffler.get_total_toggle_count() == 0
        assert shuffler.get_toggle_count("switch.heater_1") == 0
        assert shuffler.get_toggle_count("switch.heater_2") == 0

    @pytest.mark.asyncio
    async def test_toggle_count_increments_on_state_change(self, mock_hass, basic_heaters):
        """Test toggle count increments when heater state changes."""
        shuffler = HeaterShuffler(
            hass=mock_hass,
            heaters=basic_heaters,
            cycle_period=timedelta(seconds=900),
            min_cycle_duration=timedelta(seconds=60),
        )

        # Mock states: heaters currently off
        mock_hass.states.is_state.return_value = False

        # Apply 100% demand (turns both heaters on)
        await shuffler.async_apply_demand(100.0)

        # Toggle count should be 2 (one for each heater turning on)
        assert shuffler.get_total_toggle_count() >= 2


class TestDiagnostics:
    """Test diagnostic information methods."""

    def test_get_heater_info(self, mock_hass, basic_heaters):
        """Test retrieval of heater information."""
        shuffler = HeaterShuffler(
            hass=mock_hass,
            heaters=basic_heaters,
            cycle_period=timedelta(seconds=900),
            min_cycle_duration=timedelta(seconds=60),
        )

        info = shuffler.get_heater_info()
        assert "switch.heater_1" in info
        assert "switch.heater_2" in info
        assert info["switch.heater_1"]["name"] == "Heater 1"
        assert info["switch.heater_1"]["power"] == 1500.0

    def test_get_rotation_info(self, mock_hass, basic_heaters):
        """Test retrieval of rotation information."""
        shuffler = HeaterShuffler(
            hass=mock_hass,
            heaters=basic_heaters,
            cycle_period=timedelta(seconds=900),
            min_cycle_duration=timedelta(seconds=60),
        )

        info = shuffler.get_rotation_info()
        assert "rotation_index" in info
        assert "current_priority_order" in info
        assert info["rotation_index"] == 0
        assert len(info["current_priority_order"]) == 2

    def test_get_cycle_info_uninitialized(self, mock_hass, basic_heaters):
        """Test cycle info before cycle start."""
        shuffler = HeaterShuffler(
            hass=mock_hass,
            heaters=basic_heaters,
            cycle_period=timedelta(seconds=900),
            min_cycle_duration=timedelta(seconds=60),
        )

        info = shuffler.get_cycle_info()
        assert info["time_in_cycle"] == 0.0
        assert info["cycle_period"] == 0.0


if __name__ == "__main__":
    # Simple demonstration of the cascading power bucket algorithm
    print("=" * 70)
    print("CASCADING POWER BUCKET ALGORITHM DEMONSTRATION")
    print("=" * 70)

    # Example: 3 heaters with unequal power
    heaters = [
        Heater(entity_id="switch.heater_1", power=2000.0, name="2kW Heater"),
        Heater(entity_id="switch.heater_2", power=1500.0, name="1.5kW Heater"),
        Heater(entity_id="switch.heater_3", power=500.0, name="0.5kW Heater"),
    ]
    total_capacity = sum(h.power for h in heaters)

    print(f"\nHeaters configured: {len(heaters)}")
    print(f"Total capacity: {total_capacity}W")
    for h in heaters:
        print(f"  - {h.name}: {h.power}W")

    # Test different demand levels
    test_demands = [0, 25, 50, 75, 100]

    for demand_pct in test_demands:
        required_power = total_capacity * (demand_pct / 100)
        print(f"\n--- Demand: {demand_pct}% ({required_power:.0f}W) ---")

        remaining = required_power
        for i, heater in enumerate(heaters):
            if remaining >= heater.power:
                print(f"  {heater.name}: ON (100% duty, -{heater.power:.0f}W)")
                remaining -= heater.power
            elif remaining > 0:
                duty = (remaining / heater.power) * 100
                print(f"  {heater.name}: TPI {duty:.1f}% duty (-{remaining:.0f}W)")
                remaining = 0
            else:
                print(f"  {heater.name}: OFF")
