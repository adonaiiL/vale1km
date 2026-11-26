from __future__ import annotations

from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SiteMarkup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.label_depth = 0
        self.labelled_ids = set()
        self.controls = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        element_id = attrs.get("id")
        if element_id:
            self.ids.append(element_id)
        if tag == "label":
            self.label_depth += 1
            if attrs.get("for"):
                self.labelled_ids.add(attrs["for"])
        if tag in ("input", "select", "textarea") and element_id:
            self.controls.append(element_id)
            if self.label_depth or attrs.get("aria-label"):
                self.labelled_ids.add(element_id)

    def handle_endtag(self, tag):
        if tag == "label" and self.label_depth:
            self.label_depth -= 1


class SiteContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "index.html").read_text(encoding="utf-8")
        cls.js = (ROOT / "viewer.js").read_text(encoding="utf-8")
        cls.parser = SiteMarkup()
        cls.parser.feed(cls.html)

    def test_document_has_unique_ids(self):
        counts = Counter(self.parser.ids)
        duplicates = sorted(key for key, count in counts.items() if count > 1)
        self.assertEqual(duplicates, [])

    def test_literal_viewer_selectors_exist(self):
        referenced = set(re.findall(r"\$\(['\"]#([A-Za-z0-9_-]+)['\"]\)", self.js))
        missing = sorted(referenced - set(self.parser.ids))
        self.assertEqual(missing, [])

    def test_form_controls_have_accessible_names(self):
        missing = sorted(set(self.parser.controls) - self.parser.labelled_ids)
        self.assertEqual(missing, [])

    def test_viewer_script_is_versioned_for_cache_refresh(self):
        self.assertRegex(self.html, r'<script[^>]+src=["\']viewer\.js\?v=\d+["\']')

    def test_desktop_and_mobile_layouts_are_declared(self):
        self.assertRegex(self.html, r"@media\s*\(min-width:\s*981px\)")
        self.assertRegex(self.html, r"@media\s*\(max-width:\s*980px\)")
        self.assertIn("prefers-reduced-motion", self.html)

    def test_github_token_is_not_persisted(self):
        self.assertNotRegex(self.js, r"remember\(['\"]tk['\"]")
        self.assertNotRegex(self.js, r"(localStorage|sessionStorage)\.setItem\(['\"]token")

if __name__ == "__main__":
    unittest.main()
