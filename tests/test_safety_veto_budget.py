import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from custom_components.ir_floor_heating.climate import IRFloorHeatingClimate
from custom_components.ir_floor_heating.tpi import BudgetBucket


class TestSafetyVetoBudgetIntegration(unittest.TestCase):
    def setUp(self):
        self.hass = MagicMock()
        self.config = MagicMock()
        self.config.hass = self.hass
        self.config.safety_budget_capacity = 2.0
        self.config.safety_budget_interval = 300.0  # 1 token per 300 seconds
        self.config.max_floor_temp = 28.0
        self.config.safety_hysteresis = 1.0
        self.config.floor_sensors = ["sensor.floor"]
        self.config.room_sensors = ["sensor.room"]
        self.config.cycle_period = timedelta(seconds=900)
        self.config.min_cycle_duration = timedelta(seconds=60)

        # Mock dependencies to allow instantiation
        with patch("custom_components.ir_floor_heating.climate.FusionKalmanFilter"):
            with patch("custom_components.ir_floor_heating.climate.PIDController"):
                with patch(
                    "custom_components.ir_floor_heating.climate.DualPIDController"
                ):
                    with patch(
                        "custom_components.ir_floor_heating.climate.TPIController"
                    ):
                        with patch(
                            "custom_components.ir_floor_heating.climate.async_entity_id_to_device"
                        ):
                            self.climate = IRFloorHeatingClimate(self.config)

        # Ensure we have a real budget bucket for testing
        self.climate._safety_budget = BudgetBucket(2.0, 1.0 / 300.0)

    @patch("custom_components.ir_floor_heating.tpi.datetime")
    def test_veto_budget_limit(self, mock_datetime):
        # Set start time
        start_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        mock_datetime.now.return_value = start_time

        # Ensure we have a real budget bucket for testing, initialized with start_time
        self.climate._safety_budget = BudgetBucket(2.0, 1.0 / 300.0)

        # Setup initial state
        self.climate._floor_temp = 25.0
        self.climate._room_temp = 20.0
        self.climate._safety_veto_active = False

        # 1. Engage veto (Floor too hot)
        self.climate._floor_temp = 29.0
        self.assertTrue(self.climate._check_safety_veto())
        self.climate._safety_veto_active = True
        self.assertEqual(self.climate._safety_budget.tokens, 1.0)

        # 2. Release veto (Floor cools down)
        self.climate._floor_temp = 26.0  # Below 28-1=27
        self.assertFalse(self.climate._check_safety_veto())
        self.climate._safety_veto_active = False
        self.assertEqual(self.climate._safety_budget.tokens, 0.0)

        # 3. Engage veto again (Floor hot again)
        self.climate._floor_temp = 29.0
        self.assertTrue(self.climate._check_safety_veto())
        self.climate._safety_veto_active = True
        self.assertEqual(self.climate._safety_budget.tokens, -1.0)  # Forced consume

        # 4. Try to release veto (Floor cool again)
        self.climate._floor_temp = 26.0
        # Budget is -1.0, need 1.0 to consume.
        self.assertTrue(
            self.climate._check_safety_veto()
        )  # SHOULD BE DELAYED (returns True meaning veto active)
        self.assertTrue(self.climate._safety_veto_active)

        # 5. Wait for budget (needs 2 tokens to go from -1.0 to 1.0)
        # 2 tokens * 300 seconds = 600 seconds
        mock_datetime.now.return_value = start_time + timedelta(seconds=600)
        # tokens should now be 1.0
        self.assertFalse(self.climate._check_safety_veto())  # Should now release!
        self.climate._safety_veto_active = False
        self.assertEqual(self.climate._safety_budget.tokens, 0.0)


if __name__ == "__main__":
    unittest.main()
