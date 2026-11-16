"""
Channel level settings (global for all channels).
"""

import waffle  # pylint: disable=invalid-django-waffle-import

# Waffle switch that turns on failed-grade transmission for channels that opt in with TRANSMIT_FAILED_GRADES.
ENABLE_FAILED_GRADE_TRANSMISSION_SWITCH = 'enable_failed_grade_transmission'


class ChannelSettingsMixin:
    """
    Mixin for channel settings that apply to all channels.
    Provides common settings for all channels. Each channels is free to override settings at their
    Exporter or Transmitter or Client level, as needed

    Important: If you add a setting here, please add a test to cover this default, as well as
    any overrides you add on a per channel basis. See this test for an example:
    tests/test_integrated_channels/test_sap_success_factors/test_transmitters/test_learner_data.py
    """

    # a channel should override this to False if they don't want grade changes to
    # cause retransmission of completion records
    INCLUDE_GRADE_FOR_COMPLETION_AUDIT_CHECK = True

    # a channel should override this to True to transmit failed (completed but not passing) grades.
    # A learner whose failed grade was transmitted is then retransmitted once their grade changes,
    # even if INCLUDE_GRADE_FOR_COMPLETION_AUDIT_CHECK is False.
    # Takes effect only while the ENABLE_FAILED_GRADE_TRANSMISSION_SWITCH waffle switch is active.
    TRANSMIT_FAILED_GRADES = False

    @property
    def transmit_failed_grades(self):
        """
        Whether failed grades are transmitted: the channel opts in and the waffle switch is active.
        """
        return self.TRANSMIT_FAILED_GRADES and waffle.switch_is_active(ENABLE_FAILED_GRADE_TRANSMISSION_SWITCH)
