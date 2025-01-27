"""
Utilities to get details from the course catalog API.
"""


class GradesApiClient:
    """
    The API client to make calls to the LMS Grades API.

    Note that this API client requires a JWT token, and so it keeps its token alive.
    """

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
        return []
