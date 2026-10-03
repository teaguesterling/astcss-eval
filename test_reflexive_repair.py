#!/usr/bin/env python3
"""Unit tests for Reflexive Execution-Feedback Prompting and Error Handling System."""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tune"))

from reflexive_repair import ExecutionFeedbackEngine, ReflexivePromptFormatter


class TestReflexiveRepair(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = ExecutionFeedbackEngine()

    def test_01_syntax_error_diagnosis(self):
        """Test that malformed syntax triggers clean ASTCSS syntax error feedback."""
        res = self.engine.evaluate_selector_on_fixture("py-variety", ".fn[unclosed_bracket")
        self.assertEqual(res["status"], "parse_error")
        self.assertIn("malformed selector", res["error_message"].lower())
        
        fb = self.engine.build_feedback("find functions with decorator", ".fn[unclosed_bracket", res, fixture="py-variety")
        self.assertIn("[ASTCSS Syntax Error]", fb)
        self.assertIn("failed to parse", fb)
        self.assertIn("ensure matching brackets", fb.lower())

    def test_02_unknown_pseudoclass_diagnosis(self):
        """Test that unsupported pseudo-classes trigger clear replacement feedback."""
        res = self.engine.evaluate_selector_on_fixture("py-variety", ".fn:unknown_custom_pseudo")
        self.assertEqual(res["status"], "unknown_pseudo")
        self.assertIn("unknown pseudo-class", res["error_message"].lower())

        fb = self.engine.build_feedback("find typed functions", ".fn:unknown_custom_pseudo", res, fixture="py-variety")
        self.assertIn("[ASTCSS Unsupported Pseudo-Class]", fb)
        self.assertIn("standard ASTCSS pseudo-classes", fb)

    def test_03_empty_match_prefix_hints(self):
        """Test that 0 matches on an exact name search introspects AST for prefix hints."""
        res = self.engine.evaluate_selector_on_fixture("py-variety", ".fn#main_nonexistent")
        self.assertEqual(res["status"], "empty_match")
        self.assertEqual(res["match_count"], 0)

        # Introspect for 'main' in py-variety
        similar = self.engine.introspect_fixture_names("py-variety", "main")
        self.assertIn("main", similar)

        fb = self.engine.build_feedback("the main function", ".fn#main_nonexistent", res, fixture="py-variety")
        self.assertIn("[Execution Feedback: 0 Matches]", fb)
        self.assertIn("Found related identifiers in the codebase", fb)

    def test_04_python_idiom_hints(self):
        """Test cross-language naming hints (e.g. __constructor -> __init__, push -> append)."""
        res_empty = {"status": "empty_match", "match_count": 0, "nodes": []}
        
        # Test __constructor
        fb1 = self.engine.diagnose_empty_match("classes without constructor", ".class:not(:has(.fn#__constructor))", lang="python")
        self.assertTrue(any("__init__" in h for h in fb1))

        # Test push -> append
        fb2 = self.engine.diagnose_empty_match("loops that push items", ".loop:has(.call#push)", lang="python")
        self.assertTrue(any("append" in h for h in fb2))

        # Test finally_statement -> .finally
        fb3 = self.engine.diagnose_empty_match("finally blocks", "finally_statement", lang="python")
        self.assertTrue(any(".finally" in h for h in fb3))

    def test_05_graph_relation_inversion_hints(self):
        """Test diagnosis of caller vs callee graph inversions."""
        # Query used callers when intent is callees (outgoing calls)
        fb_callees = self.engine.diagnose_empty_match("what are all functions called by validate_email", ".fn#validate_email::callers")
        self.assertTrue(any("callees" in h for h in fb_callees))

        # Query used callees when intent is callers (incoming calls)
        fb_callers = self.engine.diagnose_empty_match("what functions call escape_string", ".fn#escape_string::callees")
        self.assertTrue(any("callers" in h for h in fb_callers))

    def test_06_multi_turn_prompt_format(self):
        """Test formatting of standard 2-turn ChatML prompt."""
        prompt = ReflexivePromptFormatter.format_shot2_prompt(
            system_card="Vocabulary card:\n- .fn: function definitions",
            nl_intent="the update functions",
            shot1_selector=".fn#update",
            feedback_message="[Execution Feedback: 0 Matches]\nSelector '.fn#update' returned 0 matches.\n- Found related identifiers: ['update_user']. Consider [name^=\"update_\"]"
        )
        self.assertIn("<|im_start|>system", prompt)
        self.assertIn("<|im_start|>user\nthe update functions<|im_end|>", prompt)
        self.assertIn("<|im_start|>assistant\n.fn#update<|im_end|>", prompt)
        self.assertIn("<|im_start|>user\n[Execution Feedback: 0 Matches]", prompt)
        self.assertTrue(prompt.endswith("<|im_start|>assistant\n"))


if __name__ == "__main__":
    unittest.main()
