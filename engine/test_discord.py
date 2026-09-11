"""Behavioral tests for the Discord operator transport."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import discord


class DiscordTransportTests(unittest.TestCase):
    def setUp(self):
        self.saved_state = dict(discord._state)
        self.saved_env = discord.ENV
        self.saved_modes_env = discord.MODES_ENV
        self.env = Path(tempfile.mkdtemp(prefix="discord-test-")) / ".env"
        self.env.write_text("DISCORD_BOT_TOKEN=token\n")
        discord.ENV = self.env
        discord._state.update(loaded=False, token=None, after=None)

    def tearDown(self):
        discord.ENV = self.saved_env
        discord.MODES_ENV = self.saved_modes_env
        discord._state.update(self.saved_state)

    def test_load_reads_the_shared_tron_modes_environment(self):
        modes_env = Path(tempfile.mkdtemp(prefix="discord-modes-")) / ".env"
        modes_env.write_text("DISCORD_BOT_TOKEN=modes-token\n")
        discord.ENV = self.env.with_name("missing.env")
        discord.MODES_ENV = modes_env
        discord._state.update(loaded=False, token=None, after=None)

        self.assertTrue(discord._load())
        self.assertEqual(discord._state["token"], "modes-token")

    def test_note_posts_to_the_tron_channel(self):
        calls = []

        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self): return b'{"id": "17"}'

        def open_(request, timeout):
            calls.append((request.full_url, dict(request.header_items()),
                          request.data, timeout))
            return Response()

        with patch("urllib.request.urlopen", open_):
            self.assertTrue(discord.note("fleet is green"))

        url, headers, body, timeout = calls[0]
        self.assertEqual(url, discord.MESSAGE_URL)
        self.assertEqual(headers["Authorization"], "Bot token")
        self.assertEqual(json.loads(body), {"content": "fleet is green"})
        self.assertEqual(timeout, 10)

    def test_inbox_returns_only_new_human_messages_from_tron_channel(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self):
                return json.dumps([
                    {"id": "23", "content": "status?", "author": {"bot": False}},
                    {"id": "22", "content": "ignore bot", "author": {"bot": True}},
                    {"id": "21", "content": "old", "author": {"bot": False}},
                ]).encode()

        def open_(request, timeout):
            if "after=23" in request.full_url:
                class EmptyResponse(Response):
                    def read(self): return b"[]"
                return EmptyResponse()
            return Response()

        with patch("urllib.request.urlopen", open_):
            self.assertEqual(discord.inbox(), ["old", "status?"])
            self.assertEqual(discord.inbox(), [])


if __name__ == "__main__":
    unittest.main()
