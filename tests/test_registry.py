"""The grantor registry: each issuer's reporting group and privacy keep rules (entities.yaml)."""

import tempfile
import unittest
from pathlib import Path

from tinos.config import load_registry
from tinos.curated_grants import keep_rules_for

YAML = """\
version: 1
in_scope:
  - {uid: "6296", name: ΔΗΜΟΣ ΤΗΝΟΥ, afm: "800302968"}
grantors:
  - {uid: "100054492", name: ΥΠΟΥΡΓΕΙΟ ΕΣΩΤΕΡΙΚΩΝ, latin_name: ypes_2019}
  - {uid: "99206908", name: ΙΔΡΥΜΑ, group: evangelistria, keep: [tinos_body]}
  - {uid: "50203", name: ΑΠΟΚΕΝΤΡΩΜΕΝΗ ΔΙΟΙΚΗΣΗ ΑΙΓΑΙΟΥ, group: decentralised, keep: [grant_words]}
"""


def registry(text: str = YAML):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "entities.yaml"
        path.write_text(text, encoding="utf-8")
        return load_registry(path)


class Registry(unittest.TestCase):
    def test_groups_and_keep_rules(self):
        reg = registry()
        self.assertEqual(reg.grantor_group("100054492"), "interior")  # the default: the Interior Ministry
        self.assertEqual(reg.grantor_group("99206908"), "evangelistria")
        self.assertEqual(reg.keep_rules("99206908"), ("tinos_body",))
        self.assertEqual(reg.keep_rules("100054492"), ("grant_words", "investment_acts", "tinos_body"))
        # a co-issuer that is no grantor of ours counts with the ministry, under every rule
        self.assertEqual(reg.grantor_group("100081912"), "interior")
        self.assertEqual(reg.keep_rules("100081912"), ("grant_words", "investment_acts", "tinos_body"))

    def test_an_unknown_keep_rule_is_refused(self):
        with self.assertRaises(ValueError):
            registry(YAML.replace("keep: [grant_words]", "keep: [grant_word]"))

    def test_a_record_is_judged_by_the_grantors_whose_searches_kept_it(self):
        reg = registry()
        # a joint decision stored under the foundation's uid but found by a ministry search keeps the ministry's rules
        orgs = {"Α": {"100054492"}, "Β": {"99206908", "50203"}}
        self.assertEqual(keep_rules_for("Α", "99206908", orgs, reg), ("grant_words", "investment_acts", "tinos_body"))
        self.assertEqual(keep_rules_for("Β", "99206908", orgs, reg), ("grant_words", "tinos_body"))
        self.assertEqual(keep_rules_for("Γ", "50203", orgs, reg), ("grant_words",))  # no page: its issuer's rules


if __name__ == "__main__":
    unittest.main()


class FoundationRule(unittest.TestCase):
    def test_the_curated_check_keeps_the_foundations_own_rule(self):
        # the curated layer applies the whitelist again with each record's rules: the foundation's statutory_grant
        # must survive the union, or its statutory grants never reach grant_decision
        from tinos.config import load_registry, load_settings
        from tinos.curated_grants import keep_rules_for
        reg = load_registry(load_settings().entities_file)
        self.assertEqual(keep_rules_for("X", "99206908", {"X": {"99206908"}}, reg), ("tinos_body", "statutory_grant"))
        self.assertNotIn("statutory_grant", keep_rules_for("X", "5011", {}, reg))
