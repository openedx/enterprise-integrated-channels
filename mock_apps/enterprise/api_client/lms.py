"""
Utilities to get details from the course catalog API.
"""


class GradesApiClient:
    """
    The API client to make calls to the LMS Grades API.

    Note that this API client requires a JWT token, and so it keeps its token alive.
    """

    def get_course_assessment_grades(self, course_id, username):
        return []
