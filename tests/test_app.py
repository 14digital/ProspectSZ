import os
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from prospectsz.pipeline import draft
from prospectsz.store import Store
from test_pipeline import ready


class AppTests(unittest.TestCase):
    def test_all_pages_start_without_secrets(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"PROSPECTSZ_DB": folder + "/app.sqlite3"}):
            app = AppTest.from_file("app.py").run()
            self.assertFalse(app.exception)
            self.assertEqual(app.title[0].value, "Command centre")
            for page in ["Discover & import", "Research & enrich", "Approval queue", "Export & audit"]:
                app.sidebar.radio[0].set_value(page).run()
                self.assertFalse(app.exception, page)
                self.assertEqual(app.title[0].value, page)

    def test_human_approval_is_required_and_persisted(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"PROSPECTSZ_DB": folder + "/app.sqlite3"}):
            store = Store()
            p = ready()
            draft(p)
            store.save(p, "fixture")
            app = AppTest.from_file("app.py").run()
            app.sidebar.radio[0].set_value("Approval queue").run()
            app.button(key="approve:" + p.website).click().run()
            self.assertTrue(app.error)
            self.assertEqual(store.all()[0].review_status, "pending_approval")
            app.checkbox(key="review:" + p.website).check().run()
            app.button(key="approve:" + p.website).click().run()
            self.assertFalse(app.exception)
            self.assertEqual(store.all()[0].review_status, "approved")
            app.button(key="save:" + p.website).click().run()
            self.assertEqual(store.all()[0].review_status, "pending_approval")
