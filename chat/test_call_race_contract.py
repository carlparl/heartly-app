from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class CallClientRaceContractTests(SimpleTestCase):
    def read_project_file(self, relative_path):
        return (
            Path(settings.BASE_DIR)
            / relative_path
        ).read_text(encoding="utf-8")

    def test_call_room_has_receiver_ready_handshake(self):
        source = self.read_project_file(
            "static/js/heartly-call-room.js"
        )

        self.assertIn('"call.ready"', source)
        self.assertIn(
            "announceReceiverReady",
            source,
        )
        self.assertIn(
            "scheduleOfferRetry",
            source,
        )
        self.assertIn(
            "offerRetryTimer",
            source,
        )

    def test_global_banner_ignores_stale_clear_events(self):
        source = self.read_project_file(
            "static/js/heartly-global-calls.js"
        )

        self.assertIn(
            "activeCallMatches",
            source,
        )
        self.assertIn(
            'payload.type === "call.none"',
            source,
        )
        self.assertIn(
            "if (!activeCall)",
            source,
        )

    def test_consumer_relays_receiver_ready_signal(self):
        source = self.read_project_file(
            "chat/consumers.py"
        )

        self.assertIn(
            '"call.ready"',
            source,
        )
        self.assertIn(
            "relay_call_signal",
            source,
        )
