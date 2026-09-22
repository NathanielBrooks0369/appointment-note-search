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
