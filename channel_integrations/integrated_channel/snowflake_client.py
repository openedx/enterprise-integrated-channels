"""
Snowflake client for querying learning time data.

This module provides a client for querying total learning time from the
Snowflake data warehouse. Learning time is cached to minimize database load.
"""
import logging
from contextlib import contextmanager

import snowflake.connector
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Cache configuration
LEARNING_TIME_CACHE_KEY_TEMPLATE = 'learning_time:{user_id}:{course_id}:{enterprise_id}'
LEARNING_TIME_CACHE_TTL = 3600  # 1 hour


class SnowflakeLearningTimeClient:
    """
    Client for querying learning time data from Snowflake.

    This client provides methods to retrieve total learning time for a user/course/enterprise
    combination. Results are cached to minimize database load.

    Example:
        >>> client = SnowflakeLearningTimeClient()
        >>> learning_time = client.get_learning_time(
        ...     user_id=12345,
        ...     course_id='course-v1:edX+DemoX+Demo',
        ...     enterprise_customer_uuid='a1b2c3d4-...'
        ... )
        >>> if learning_time:
        ...     print(f'Total learning time: {learning_time} seconds')
    """

    def __init__(self):
        """Initialize Snowflake client with configuration from Django settings."""
        self.account = getattr(settings, 'SNOWFLAKE_ACCOUNT', None)
        self.warehouse = getattr(settings, 'SNOWFLAKE_WAREHOUSE', None)
        self.database = getattr(settings, 'SNOWFLAKE_DATABASE', None)
        self.schema = getattr(settings, 'SNOWFLAKE_SCHEMA', None)
        self.role = getattr(settings, 'SNOWFLAKE_ROLE', None)
        self.user = getattr(settings, 'SNOWFLAKE_SERVICE_USER', None)
        self.password = getattr(settings, 'SNOWFLAKE_SERVICE_USER_PASSWORD', None)

    @contextmanager
    def _get_connection(self):
        """
        Context manager for Snowflake database connections.

        Yields:
            snowflake.connector.connection: Active database connection

        Raises:
            Exception: If connection fails

        Example:
            >>> client = SnowflakeLearningTimeClient()
            >>> with client._get_connection() as conn:
            ...     cursor = conn.cursor()
            ...     cursor.execute("SELECT 1")
        """
        conn = None
        try:
            conn = snowflake.connector.connect(
                account=self.account,
                user=self.user,
                password=self.password,
                warehouse=self.warehouse,
                database=self.database,
                schema=self.schema,
                role=self.role,
            )
            logger.debug(f'[LearningTime] Connected to Snowflake: {self.database}.{self.schema}')
            yield conn
        except Exception as e:
            logger.error(f'[LearningTime] Failed to connect to Snowflake: {e}')
            raise
        finally:
            if conn:
                conn.close()
                logger.debug('[LearningTime] Closed Snowflake connection')

    def get_learning_time(self, user_id, course_id, enterprise_customer_uuid):
        """
        Query total learning time for a user/course/enterprise combination.

        This method first checks the cache for existing learning time data. If not found,
        it queries Snowflake and caches the result. If Snowflake is unavailable or returns
        no data, it returns None (enabling graceful degradation).

        Args:
            user_id (int): LMS user ID
            course_id (str): Course key (e.g., 'course-v1:edX+DemoX+Demo_Course')
            enterprise_customer_uuid (str): Enterprise customer UUID

        Returns:
            int: Total learning time in seconds, or None if not found

        Example:
            >>> client = SnowflakeLearningTimeClient()
            >>> seconds = client.get_learning_time(12345, 'course-v1:edX+Demo+2024', 'abc-123')
            >>> if seconds:
            ...     hours = round(seconds / 3600, 2)
            ...     print(f'Learning time: {hours} hours')
        """
        # Check cache first
        cache_key = LEARNING_TIME_CACHE_KEY_TEMPLATE.format(
            user_id=user_id,
            course_id=course_id,
            enterprise_id=enterprise_customer_uuid
        )
        cached_value = cache.get(cache_key)
        if cached_value is not None:
            logger.info(f'[LearningTime] Cache hit: {cache_key}')
            return cached_value if cached_value > 0 else None

        # Query Snowflake
        query = """
        SELECT SUM(LEARNING_TIME_SECONDS) as total_learning_time
        FROM PROD.BUSINESS_INTELLIGENCE.LEARNING_TIME
        WHERE USER_ID = %s
          AND COURSERUN_KEY = %s
          AND ENTERPRISE_CUSTOMER_UUID = %s
        """

        try:
            with self._get_connection() as conn:
                if conn is None:
                    # Connection failed or snowflake not installed - graceful degradation
                    logger.warning('[LearningTime] No Snowflake connection available')
                    cache.set(cache_key, 0, LEARNING_TIME_CACHE_TTL)
                    return None

                cursor = conn.cursor()
                cursor.execute(query, (user_id, course_id, enterprise_customer_uuid))
                result = cursor.fetchone()
                cursor.close()

                if result and result[0] is not None:
                    learning_time = int(result[0])
                    # Cache the result
                    cache.set(cache_key, learning_time, LEARNING_TIME_CACHE_TTL)
                    logger.info(
                        f'[LearningTime] Retrieved from Snowflake: {learning_time}s '
                        f'for user_id={user_id}, course_id={course_id}'
                    )
                    return learning_time
                else:
                    logger.warning(
                        f'[LearningTime] No data found for '
                        f'user_id={user_id}, course_id={course_id}, enterprise={enterprise_customer_uuid}'
                    )
                    # Cache negative result to avoid repeated queries
                    cache.set(cache_key, 0, LEARNING_TIME_CACHE_TTL)
                    return None

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error(f'[LearningTime] Error querying Snowflake: {e}', exc_info=True)
            # Cache negative result on error to avoid hammering Snowflake
            cache.set(cache_key, 0, LEARNING_TIME_CACHE_TTL)
            return None
