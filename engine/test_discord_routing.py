"""Behavioral tests for Discord-to-TRON routing."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import tron
import transcript


class DiscordRoutingTests(unittest.TestCase):
    def test_operator_page_is_delivered_to_telegram_and_discord(self):
        page = "[TRON] Hey boss — the fleet needs you.\n\ndo this\n\nReply here; your answer goes straight back in."
        with patch.object(transcript.tg, "ask", return_value="continue"), \
             patch.object(transcript.discord, "note") as discord:
            self.assertEqual(transcript.operator("do this"), "continue")

        discord.assert_called_once_with(page)

    def test_milestone_is_delivered_to_telegram_and_discord(self):
        with patch.object(tron.tg, "note") as telegram, \
             patch.object(tron.discord, "note") as discord:
            tron.milestone("trunk green")

        telegram.assert_called_once_with("trunk green")
        discord.assert_called_once_with("trunk green")

    def test_each_normal_discord_message_is_routed_through_parley(self):
        project = Path(tempfile.mkdtemp(prefix="discord-route-"))
        received = []

        def parley(path, architect):
            message = path / "parley.md"
            if message.exists():
                received.append(message.read_text())
                message.unlink()

        with patch.object(tron.discord, "inbox", return_value=["status?", "next?"]), \
             patch.object(tron, "parley", side_effect=parley), \
             patch.object(tron, "report_request"):
            tron.channels(project, object())

        self.assertEqual(received, ["status?", "next?"])


if __name__ == "__main__":
    unittest.main()
