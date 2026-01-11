import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from custom_components.ir_floor_heating.tpi import BudgetBucket


class TestBudgetBucket(unittest.TestCase):
    @patch("custom_components.ir_floor_heating.tpi.datetime")
    def test_consume_and_refill(self, mock_datetime):
        start_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        mock_datetime.now.return_value = start_time
        mock_datetime.now.side_effect = None  # ensure it returns start_time initially

        # Capacity 2, refill 1 token per 100 seconds
        bucket = BudgetBucket(capacity=2.0, refill_rate=0.01)

        # Initial state: full
        self.assertEqual(bucket.tokens, 2.0)

        # Consume 1
        self.assertTrue(bucket.consume(1.0))
        self.assertEqual(bucket.tokens, 1.0)

        # Consume 1
        self.assertTrue(bucket.consume(1.0))
        self.assertEqual(bucket.tokens, 0.0)

        # Consume 1 (fail)
        self.assertFalse(bucket.consume(1.0))
        self.assertEqual(bucket.tokens, 0.0)

        # Force consume
        self.assertTrue(bucket.consume(1.0, force=True))
        self.assertEqual(bucket.tokens, -1.0)

        # Wait 100 seconds (should get 1 token back)
        mock_datetime.now.return_value = start_time + timedelta(seconds=100)
        bucket._refill()
        self.assertEqual(bucket.tokens, 0.0)

        # Wait another 200 seconds (should get 2 more tokens, but capped at capacity)
        mock_datetime.now.return_value = start_time + timedelta(seconds=300)
        bucket._refill()
        self.assertEqual(bucket.tokens, 2.0)


if __name__ == "__main__":
    unittest.main()
