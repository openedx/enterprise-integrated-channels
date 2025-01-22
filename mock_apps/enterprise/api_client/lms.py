"""
Utilities to get details from the course catalog API.
"""

import logging
import time
from urllib.parse import urljoin

from django.conf import settings
from enterprise.api_client.client import UserAPIClient
from requests.exceptions import HTTPError, Timeout

LOGGER = logging.getLogger(__name__)


class GradesApiClient(UserAPIClient):
    """
    The API client to make calls to the LMS Grades API.

    Note that this API client requires a JWT token, and so it keeps its token alive.
    """

    MAX_RETRIES = getattr(settings, "ENTERPRISE_DEGREED2_MAX_RETRIES", 4)
    API_BASE_URL = urljoin(f"{settings.LMS_INTERNAL_ROOT_URL}/", "api/grades/v1/")
    APPEND_SLASH = True

    def _calculate_backoff(self, attempt_count):
        """
        Calculate the seconds to sleep based on attempt_count
        """
        return (self.BACKOFF_FACTOR * (2 ** (attempt_count - 1)))

    @UserAPIClient.refresh_token
    def get_course_grade(self, course_id, username):
        """
        Retrieve the grade for the given username for the given course_id.

        Args:
        * ``course_id`` (str): The string value of the course's unique identifier
        * ``username`` (str): The username ID identifying the user for which to retrieve the grade.

        Raises:

        HTTPError if no grade found for the given user+course.

        Returns:

        a dict containing:

        * ``username``: A string representation of a user's username passed in the request.
        * ``course_key``: A string representation of a Course ID.
        * ``passed``: Boolean representing whether the course has been passed according the course's grading policy.
        * ``percent``: A float representing the overall grade for the course
        * ``letter_grade``: A letter grade as defined in grading_policy (e.g. 'A' 'B' 'C' for 6.002x) or None

        """
        api_url = self.get_api_url(f"courses/{course_id}")
        response = self.client.get(api_url, params={"username": username})
        response.raise_for_status()
        for row in response.json():
            if row.get('username') == username:
                return row

        raise HTTPError(f'No grade record found for course={course_id}, username={username}')

    @UserAPIClient.refresh_token
    def get_course_assessment_grades(self, course_id, username):
        """
        Retrieve the assessment grades for the given username for the given course_id.

        Args:
        * ``course_id`` (str): The string value of the course's unique identifier
        * ``username`` (str): The username ID identifying the user for which to retrieve the grade.

        Raises:

        HTTPError if no grade found for the given user+course.

        Returns:

        a list of dicts containing:

        * ``attempted``: A boolean representing whether the learner has attempted the subsection yet.
        * ``subsection_name``: String representation of the subsection's name.
        * ``category``: String representation of the subsection's category.
        * ``label``: String representation of the subsection's label.
        * ``score_possible``: The total amount of points that the learner could have earned on the subsection.
        * ``score_earned``: The total amount of points that the learner earned on the subsection.
        * ``percent``: A float representing the overall grade for the course.
        * ``module_id``: The ID of the subsection.
        """
        attempts = 0
        while True:
            attempts = attempts + 1
            api_url = self.get_api_url(f"gradebook/{course_id}")
            try:
                response = self.client.get(api_url, params={"username": username}, timeout=40)
                response.raise_for_status()
                break
            except Timeout as to_exception:
                if attempts <= self.MAX_RETRIES:
                    sleep_seconds = self._calculate_backoff(attempts)
                    LOGGER.warning(
                        f"[ATTEMPT: {attempts}] Request to the LMS grades API timeouted out with "
                        f"exception: {to_exception}, backing off for {sleep_seconds} seconds and retrying"
                    )
                    time.sleep(sleep_seconds)
                else:
                    LOGGER.warning(
                        f"Requests to the grades API has reached the max number of retries [{self.MAX_RETRIES}], "
                        f"attempting to retrieve grade data for learner: {username} under course {course_id}"
                    )
                    raise to_exception

        results = response.json()
        if results.get('username') == username:
            return results.get('section_breakdown')

        raise HTTPError(f"No assessment grade record found for course={course_id}, username={username}")
