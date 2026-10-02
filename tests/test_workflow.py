import json
import sys

from src import health_search
from src.health_search import PatientNotification, SearchRequest, answer_question


class FakeEmbedder:
    def embed(self, text):
        return [float(len(text)), 1.0]


class FakeGateway:
    def query(self, collection, vector, top_k):
        return [{"metadata": {"text": "Urgent: same day call now to reschedule."}}]


def test_urgent_note_becomes_patient_safe_call_notification():
    result = answer_question(SearchRequest(b"scan", "Can I move this visit?", "Mina"), FakeGateway(), FakeEmbedder())
    assert isinstance(result, PatientNotification)
    assert result.status == "needs_call"
    assert "call the clinic today" in result.message


def test_cli_indexes_supplied_pdf_before_querying(monkeypatch, tmp_path, capsys):
    pdf = tmp_path / "visit.pdf"
    pdf.write_bytes(b"scanned appointment")
    calls = []

    class Gateway:
        def ocr(self, contents):
            calls.append(("ocr", contents))
            return "Urgent: call now"

        def upsert(self, collection, vector, metadata):
            calls.append(("upsert", collection, vector, metadata))

        def query(self, collection, vector, top_k):
            calls.append(("query", collection, vector, top_k))
            return [{"metadata": {"text": "Urgent: call now"}}]

    monkeypatch.setattr(health_search, "InfraiClient", Gateway)
    monkeypatch.setattr(health_search, "OpenAIEmbeddings", FakeEmbedder)
    monkeypatch.setattr(sys, "argv", ["health_search", str(pdf), "Can I move this visit?", "Mina"])

    health_search.main()

    assert [call[0] for call in calls] == ["ocr", "upsert", "query"]
    assert calls[1][3]["id"] == "visit.pdf"
    assert json.loads(capsys.readouterr().out)["status"] == "needs_call"
