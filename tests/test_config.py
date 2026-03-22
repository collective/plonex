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

    def test_normalize_options_sources_mapping(self):
        logger = DummyLogger()
        result = normalize_options(
            {
                "sources": {
                    "my.package": {"repo": "https://github.com/example/my.package.git"}
                }
            },
            logger,
        )
        self.assertEqual(
            result["sources"],
            {"my.package": {"repo": "https://github.com/example/my.package.git"}},
        )
        self.assertEqual(logger.errors, [])

    def test_normalize_options_sources_update_before_dependencies_invalid(self):
        logger = DummyLogger()
        result = normalize_options(
            {"sources_update_before_dependencies": "yes"},
            logger,
        )
        self.assertFalse(result["sources_update_before_dependencies"])
        self.assertTrue(
            any(
                "sources_update_before_dependencies" in str(error)
                for error in logger.errors
            )
        )

    def test_normalize_options_invalid_sources(self):
        logger = DummyLogger()
        result = normalize_options({"sources": []}, logger)
        self.assertEqual(result["sources"], {})
        self.assertTrue(
            any("'sources' option" in str(error) for error in logger.errors)
        )
