"""
Tests for the base transmitter.
"""

import unittest

from channel_integrations.integrated_channel.transmitters import Transmitter


class TestTransmitter(unittest.TestCase):
    """
    Tests for the base ``Transmitter`` class.
    """

    def test_transmit(self):
        """
        The ``transmit`` method is not implemented at the base, and so should raise ``NotImplementedError``.
        """
        with self.assertRaises(NotImplementedError):
            Transmitter(enterprise_configuration=None).transmit({}, {}, {})
