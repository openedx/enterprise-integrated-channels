"""
Tests for Snowflake Learning Time Client.
"""
from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache
from django.test import TestCase, override_settings

from channel_integrations.integrated_channel.snowflake_client import (
    LEARNING_TIME_CACHE_KEY_TEMPLATE,
    LEARNING_TIME_CACHE_TTL,
    SnowflakeLearningTimeClient,
)


@pytest.mark.django_db
class TestSnowflakeLearningTimeClient(TestCase):
    """Tests for SnowflakeLearningTimeClient."""

    def setUp(self):
        """Set up test fixtures."""
        super().setUp()
        self.client = SnowflakeLearningTimeClient()
        self.user_id = 123
        self.course_id = 'course-v1:edX+DemoX+Demo_Course'
        self.enterprise_uuid = 'test-enterprise-uuid'
        # Clear cache before each test
        cache.clear()

    def tearDown(self):
        """Clean up after tests."""
        cache.clear()
        super().tearDown()

    def test_cache_key_generation(self):
        """Test that cache key is generated correctly from template."""
        expected_key = 'learning_time:123:course-v1:edX+DemoX+Demo_Course:test-enterprise-uuid'
        actual_key = LEARNING_TIME_CACHE_KEY_TEMPLATE.format(
            user_id=self.user_id,
            course_id=self.course_id,
            enterprise_id=self.enterprise_uuid
        )
        assert actual_key == expected_key

    def test_cache_hit_with_data(self):
        """Test that cached learning time is returned when available."""
        # Pre-populate cache
        cache_key = LEARNING_TIME_CACHE_KEY_TEMPLATE.format(
            user_id=self.user_id,
            course_id=self.course_id,
            enterprise_id=self.enterprise_uuid
        )
        cache.set(cache_key, 7200)  # 2 hours

        result = self.client.get_learning_time(
            self.user_id,
            self.course_id,
            self.enterprise_uuid
        )

        assert result == 7200

    def test_cache_hit_with_zero(self):
        """Test that cached zero value (negative result) returns None."""
        # Pre-populate cache with 0 (meaning "no data")
        cache_key = LEARNING_TIME_CACHE_KEY_TEMPLATE.format(
            user_id=self.user_id,
            course_id=self.course_id,
            enterprise_id=self.enterprise_uuid
        )
        cache.set(cache_key, 0)

        result = self.client.get_learning_time(
            self.user_id,
            self.course_id,
            self.enterprise_uuid
        )

        # 0 is cached as "no data found", should return None
        assert result is None

    def test_cache_miss_with_data(self):
        """Test fetching from Snowflake on cache miss."""
        # Mock Snowflake cursor
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (7200,)  # 2 hours

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with patch.object(self.client, '_get_connection') as mock_get_connection:
            mock_get_connection.return_value.__enter__.return_value = mock_conn

            result = self.client.get_learning_time(
                self.user_id,
                self.course_id,
                self.enterprise_uuid
            )

            assert result == 7200
            # Verify data was cached
            cache_key = LEARNING_TIME_CACHE_KEY_TEMPLATE.format(
                user_id=self.user_id,
                course_id=self.course_id,
                enterprise_id=self.enterprise_uuid
            )
            cached = cache.get(cache_key)
            assert cached == 7200

    def test_cache_miss_no_data(self):
        """Test handling of NULL result from Snowflake (no data)."""
        # Mock Snowflake returning NULL
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (None,)

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with patch.object(self.client, '_get_connection') as mock_get_connection:
            mock_get_connection.return_value.__enter__.return_value = mock_conn

            result = self.client.get_learning_time(
                self.user_id,
                self.course_id,
                self.enterprise_uuid
            )

            assert result is None
            # Verify 0 was cached (to avoid repeated queries)
            cache_key = LEARNING_TIME_CACHE_KEY_TEMPLATE.format(
                user_id=self.user_id,
                course_id=self.course_id,
                enterprise_id=self.enterprise_uuid
            )
            cached = cache.get(cache_key)
            assert cached == 0

    def test_connection_returns_none(self):
        """Test graceful handling when connection returns None."""
        with patch.object(self.client, '_get_connection') as mock_get_connection:
            mock_get_connection.return_value.__enter__.return_value = None

            result = self.client.get_learning_time(
                self.user_id,
                self.course_id,
                self.enterprise_uuid
            )

            assert result is None
            # Should cache 0 on connection failure
            cache_key = LEARNING_TIME_CACHE_KEY_TEMPLATE.format(
                user_id=self.user_id,
                course_id=self.course_id,
                enterprise_id=self.enterprise_uuid
            )
            cached = cache.get(cache_key)
            assert cached == 0

    def test_connection_failure(self):
        """Test handling of connection exceptions."""
        with patch.object(self.client, '_get_connection') as mock_get_connection:
            mock_get_connection.return_value.__enter__.side_effect = Exception("Connection failed")

            result = self.client.get_learning_time(
                self.user_id,
                self.course_id,
                self.enterprise_uuid
            )

            assert result is None
            # Should cache 0 on error
            cache_key = LEARNING_TIME_CACHE_KEY_TEMPLATE.format(
                user_id=self.user_id,
                course_id=self.course_id,
                enterprise_id=self.enterprise_uuid
            )
            cached = cache.get(cache_key)
            assert cached == 0

    def test_query_execution_error(self):
        """Test handling of query execution errors."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = Exception("Query error")

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with patch.object(self.client, '_get_connection') as mock_get_connection:
            mock_get_connection.return_value.__enter__.return_value = mock_conn

            result = self.client.get_learning_time(
                self.user_id,
                self.course_id,
                self.enterprise_uuid
            )

            assert result is None
            # Should cache 0 on query error
            cache_key = LEARNING_TIME_CACHE_KEY_TEMPLATE.format(
                user_id=self.user_id,
                course_id=self.course_id,
                enterprise_id=self.enterprise_uuid
            )
            cached = cache.get(cache_key)
            assert cached == 0

    @override_settings(
        SNOWFLAKE_ACCOUNT='test-account',
        SNOWFLAKE_WAREHOUSE='TEST_WH',
        SNOWFLAKE_DATABASE='TEST_DB',
        SNOWFLAKE_SCHEMA='TEST_SCHEMA',
        SNOWFLAKE_ROLE='TEST_ROLE',
        SNOWFLAKE_SERVICE_USER='test_user',
        SNOWFLAKE_SERVICE_USER_PASSWORD='test_password'
    )
    def test_connection_with_correct_parameters(self):
        """Test that Snowflake connection is called with correct parameters."""
        # Create a mock connection
        mock_conn = MagicMock()

        # Patch snowflake.connector.connect directly
        with patch('snowflake.connector.connect', return_value=mock_conn) as mock_connect:
            # Create new client to pick up test settings
            client = SnowflakeLearningTimeClient()

            with client._get_connection() as conn:  # pylint: disable=protected-access
                assert conn == mock_conn

            # Verify connection was called with correct parameters
            mock_connect.assert_called_once_with(
                account='test-account',
                user='test_user',
                password='test_password',
                warehouse='TEST_WH',
                database='TEST_DB',
                schema='TEST_SCHEMA',
                role='TEST_ROLE',
            )
            # Verify connection is closed
            mock_conn.close.assert_called_once()

    def test_zero_learning_time(self):
        """Test handling of zero learning time (valid value but treated as no data)."""
        # Mock Snowflake returning 0
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (0,)

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with patch.object(self.client, '_get_connection') as mock_get_connection:
            mock_get_connection.return_value.__enter__.return_value = mock_conn

            result = self.client.get_learning_time(
                self.user_id,
                self.course_id,
                self.enterprise_uuid
            )

            # 0 is a valid result and should be returned
            assert result == 0
            # Should cache the 0 value
            cache_key = LEARNING_TIME_CACHE_KEY_TEMPLATE.format(
                user_id=self.user_id,
                course_id=self.course_id,
                enterprise_id=self.enterprise_uuid
            )
            cached = cache.get(cache_key)
            assert cached == 0

    def test_large_learning_time_value(self):
        """Test handling of large learning time values."""
        # Mock Snowflake returning large value (e.g., 1000 hours)
        large_value = 3600000  # 1000 hours in seconds
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (large_value,)

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with patch.object(self.client, '_get_connection') as mock_get_connection:
            mock_get_connection.return_value.__enter__.return_value = mock_conn

            result = self.client.get_learning_time(
                self.user_id,
                self.course_id,
                self.enterprise_uuid
            )

            assert result == large_value
            # Verify cached
            cache_key = LEARNING_TIME_CACHE_KEY_TEMPLATE.format(
                user_id=self.user_id,
                course_id=self.course_id,
                enterprise_id=self.enterprise_uuid
            )
            cached = cache.get(cache_key)
            assert cached == large_value

    def test_cache_ttl(self):
        """Test that cache TTL is set correctly."""
        assert LEARNING_TIME_CACHE_TTL == 3600  # 1 hour

    def test_client_initialization(self):
        """Test that client initializes with settings from Django config."""
        with override_settings(
            SNOWFLAKE_ACCOUNT='test-account',
            SNOWFLAKE_WAREHOUSE='WH',
            SNOWFLAKE_DATABASE='DB',
            SNOWFLAKE_SCHEMA='SCHEMA',
            SNOWFLAKE_ROLE='ROLE',
            SNOWFLAKE_SERVICE_USER='user',
            SNOWFLAKE_SERVICE_USER_PASSWORD='pass'
        ):
            client = SnowflakeLearningTimeClient()
            assert client.account == 'test-account'
            assert client.warehouse == 'WH'
            assert client.database == 'DB'
            assert client.schema == 'SCHEMA'
            assert client.role == 'ROLE'
            assert client.user == 'user'
            assert client.password == 'pass'

    def test_client_initialization_missing_settings(self):
        """Test that client handles missing settings gracefully."""
        # Create client without settings - should not crash
        client = SnowflakeLearningTimeClient()
        # Settings should be None if not configured
        assert client.account is None or isinstance(client.account, str)

    @override_settings(
        SNOWFLAKE_ACCOUNT='test-account',
        SNOWFLAKE_WAREHOUSE='WH',
        SNOWFLAKE_DATABASE='DB',
        SNOWFLAKE_SCHEMA='SCHEMA',
        SNOWFLAKE_ROLE='ROLE',
        SNOWFLAKE_SERVICE_USER='user',
        SNOWFLAKE_SERVICE_USER_PASSWORD='pass'
    )
    def test_connection_exception_raised(self):
        """Test that connection exceptions are properly raised (not swallowed)."""
        # Mock snowflake.connector.connect to raise an exception
        with patch('snowflake.connector.connect', side_effect=Exception("Snowflake connection error")):
            # The exception should be raised (lines 82-84 coverage)
            with pytest.raises(Exception, match="Snowflake connection error"):
                with self.client._get_connection():  # pylint: disable=protected-access
                    # Should never reach here
                    pass
