import csv
import io
import tempfile
import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup

from prospectsz.pipeline import (PipelineError, Prospect, draft, export_csv, extract_contacts,
                                 handoff, import_csv, is_directory_url, public_url, rank, research_csv, run_batch,
                                 discover)
from prospectsz.store import Store


def ready():
    return Prospect("Example Care", "https://example.com", employee_count=100,
                    employee_source="https://example.com/about (2026-11-02)",
                    regulator_url="https://www.cqc.org.uk/provider/example",
                    target_name="Alex Smith", target_role="Registered Manager",
                    contact_source="https://example.com/team", verified_email="alex@example.com",
                    verification_status="source_confirmed", email_source="https://example.com/team")


class PipelineTests(unittest.TestCase):
    def test_draft_sequence_and_length(self):
        p = ready()
        message = draft(p)
        self.assertLess(len(message.split()), 150)
        fragments = ["interrupting", "paperwork", "At 14Digital", "Are you opposed"]
        self.assertEqual(sorted(message.index(s) for s in fragments), [message.index(s) for s in fragments])
        self.assertEqual(p.review_status, "pending_approval")
        self.assertEqual(handoff([p]), {"pipeline": []})
        p.review_status = "approved"
        self.assertEqual(handoff([p])["pipeline"][0]["Target Name"], "Alex Smith")

    def test_eligibility_gates(self):
        for field, value in [("employee_count", 20), ("employee_count", 251),
                             ("employee_source", ""), ("regulator_url", ""),
                             ("contact_source", ""), ("target_role", "CEO"),
                             ("verification_status", "accept_all")]:
            with self.subTest(field=field, value=value):
                p = ready()
                setattr(p, field, value)
                with self.assertRaises(PipelineError):
                    draft(p)

    def test_contact_extraction(self):
        soup = BeautifulSoup('<article><h3>Alex Smith</h3><p>Registered Manager</p></article>', "html.parser")
        self.assertEqual(extract_contacts(soup, "source"), [("Alex Smith", "Registered Manager", "source")])

    def test_csv_and_formula_safety(self):
        p = ready()
        draft(p)
        p.company_name = "=DANGEROUS()"
        p.review_status = "approved"
        row = next(csv.DictReader(io.StringIO(export_csv([p]))))
        self.assertTrue(row["Company Name"].startswith("'="))
        self.assertEqual(import_csv("company_name,website\nExample,https://example.com\n")[0].company_name, "Example")
        with self.assertRaises(PipelineError):
            import_csv("name,url\nX,Y")

    @patch("prospectsz.pipeline.socket.getaddrinfo")
    def test_private_addresses_rejected(self, dns):
        dns.return_value = [(2, 1, 6, "", ("127.0.0.1", 443))]
        with self.assertRaises(PipelineError):
            public_url("https://internal.example")

    def test_persistence_and_deletion(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(folder + "/test.sqlite3")
            p = ready()
            store.save(p, "test")
            self.assertEqual(store.all()[0].target_name, p.target_name)
            self.assertEqual(store.audit()[0]["action"], "test")
            store.delete(p.website)
            self.assertEqual(store.all(), [])
            self.assertEqual(store.audit(), [])

    def test_ranking_uses_business_evidence_and_suppression(self):
        p = ready()
        p.cqc_rating = "Inadequate"
        p.review_signal = "Awaiting review"
        p.cqc_source = "https://www.cqc.org.uk/location/example (checked 2026-11-02)"
        score, reasons = rank(p)
        self.assertEqual(score, 93)
        self.assertTrue(any("CQC" in reason for reason in reasons))
        p.target_name = "A Person"
        self.assertEqual(rank(p)[0], 93)  # Names and perceived identity do not affect priority.
        p.do_not_contact = True
        self.assertEqual(rank(p), (0, ["Suppressed: do not contact"]))

    def test_research_exchange_and_batch_are_bounded(self):
        p = ready()
        p.review_status = "research"
        p.cqc_rating, p.cqc_source = "Requires improvement", "https://www.cqc.org.uk/example"
        exported = research_csv([p])
        self.assertIn("priority_score", exported)
        saved = []
        with patch("prospectsz.pipeline.draft") as create:
            processed = run_batch([p], 1, lambda prospect, action: saved.append(action))
        self.assertEqual(processed, [p])
        create.assert_called_once_with(p)
        self.assertEqual(saved, ["on_demand_batch; no automatic approval or sending"])
        with self.assertRaises(PipelineError):
            run_batch([p], 51, lambda *_: None)

    @patch("prospectsz.pipeline.api_get")
    def test_google_discovery(self, api):
        api.return_value = {"items": [
            {"title": "Example Home Care", "snippet": "Domiciliary care", "link": "https://www.cqc.org.uk/location/1"},
            {"title": "Second Care", "snippet": "Care provider", "link": "https://www.cqc.org.uk/location/2"},
        ]}
        found = discover("care", "key", "engine", 10)
        self.assertEqual(len(found), 2)
        self.assertEqual(found[0].website, "https://www.cqc.org.uk/location/1")
        self.assertEqual(found[0].regulator_url, found[0].website)
        self.assertTrue(is_directory_url(found[0].website))
        self.assertIn("Directory candidate", found[0].notes[0])


if __name__ == "__main__":
    unittest.main()
