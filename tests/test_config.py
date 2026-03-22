from plonex.config import normalize_default_actions
from plonex.config import normalize_options
from tests.utils import DummyLogger

import unittest


class TestConfig(unittest.TestCase):

    def test_normalize_default_actions_from_string(self):
        result = normalize_default_actions({"default_action": "zeoclient fg"})
        self.assertEqual(result, [["zeoclient", "fg"]])

    def test_normalize_default_actions_from_list(self):
        result = normalize_default_actions(
            {"default_actions": [["supervisor", "start"], ["zeoclient", "fg"]]}
        )
        self.assertEqual(result, [["supervisor", "start"], ["zeoclient", "fg"]])

    def test_normalize_options_supervisor_graceful_interval(self):
        logger = DummyLogger()
        result = normalize_options({"supervisor_graceful_interval": "3.0"}, logger)
        self.assertEqual(result["supervisor_graceful_interval"], 3.0)
        self.assertEqual(logger.errors, [])

    def test_normalize_options_invalid_supervisor_graceful_interval(self):
        logger = DummyLogger()
        result = normalize_options({"supervisor_graceful_interval": "soon"}, logger)
        self.assertEqual(result["supervisor_graceful_interval"], 1.0)
        self.assertTrue(
            any("supervisor_graceful_interval" in str(error) for error in logger.errors)
        )
