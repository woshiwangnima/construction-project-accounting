import copy
import sys
import threading
import time
import types
import unittest
from unittest.mock import patch

from src.voice import VoiceEngine


class FakeEngine:
    def __init__(self, block=False, release_on_stop=True):
        self.block = block
        self.release_on_stop = release_on_stop
        self.run_started = threading.Event()
        self.release = threading.Event()
        self.stop_calls = 0
        self.said = []
        self.properties = {}

    def getProperty(self, name):
        if name == "voices":
            return []
        return self.properties.get(name)

    def setProperty(self, name, value):
        self.properties[name] = value

    def say(self, text):
        self.said.append(text)

    def runAndWait(self):
        self.run_started.set()
        if self.block:
            self.release.wait(timeout=2)

    def stop(self):
        self.stop_calls += 1
        if self.release_on_stop:
            self.release.set()


class FakeTts:
    def __init__(self, engines=None, init_error=None):
        self.engines = list(engines or [])
        self.init_error = init_error
        self.init_calls = 0

    def init(self):
        self.init_calls += 1
        if self.init_error is not None:
            raise self.init_error
        if not self.engines:
            raise AssertionError("unexpected extra pyttsx3.init() call")
        return self.engines.pop(0)


class VoiceEngineTests(unittest.TestCase):
    def setUp(self):
        old_instance = VoiceEngine._instance
        if old_instance is not None:
            old_instance.shutdown()
        VoiceEngine._instance = None

        self.config = {
            "voice": {"enabled": True, "volume": 80, "tts_rate": 150},
            "symbol_mapping": {},
        }
        self.load_app_patcher = patch(
            "src.voice.load_app",
            side_effect=lambda: copy.deepcopy(self.config),
        )
        self.load_app_patcher.start()
        self.addCleanup(self.load_app_patcher.stop)
        self.voice = VoiceEngine()
        self.addCleanup(self._cleanup_voice)

    def _cleanup_voice(self):
        if getattr(self, "voice", None) is not None:
            self.voice.shutdown()
        VoiceEngine._instance = None

    @staticmethod
    def _wait_for(predicate, timeout=2):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.01)
        return predicate()

    def test_rapid_requests_use_one_worker_and_keep_latest_text(self):
        first = FakeEngine(block=True, release_on_stop=False)
        second = FakeEngine()
        fake_tts = FakeTts([first, second])

        with patch.dict(sys.modules, {"pyttsx3": types.SimpleNamespace(init=fake_tts.init)}):
            self.voice.speak_formula("1+1")
            self.assertTrue(first.run_started.wait(1))
            worker = self.voice._tts_worker

            self.voice.speak_formula("2+2")
            self.voice.speak_formula("3+3")
            self.voice.speak_formula("4+4")
            first.release.set()

            self.assertTrue(second.run_started.wait(1))
            self.assertTrue(self._wait_for(lambda: second.said == ["4加4"]))
            self.assertIs(worker, self.voice._tts_worker)
            self.assertEqual(fake_tts.init_calls, 2)

    def test_stop_cancels_pending_request_and_current_engine(self):
        first = FakeEngine(block=True, release_on_stop=False)
        second = FakeEngine()
        fake_tts = FakeTts([first, second])

        with patch.dict(sys.modules, {"pyttsx3": types.SimpleNamespace(init=fake_tts.init)}):
            self.voice.speak_formula("1+1")
            self.assertTrue(first.run_started.wait(1))
            self.voice.speak_formula("2+2")
            self.voice.stop()
            first.release.set()

            self.assertTrue(self._wait_for(lambda: self.voice._current_engine is None))
            self.assertEqual(fake_tts.init_calls, 1)
            self.assertEqual(second.said, [])
            self.assertGreaterEqual(first.stop_calls, 1)

    def test_reload_disabling_voice_stops_current_speech(self):
        first = FakeEngine(block=True, release_on_stop=False)
        fake_tts = FakeTts([first])

        with patch.dict(sys.modules, {"pyttsx3": types.SimpleNamespace(init=fake_tts.init)}):
            self.voice.speak_formula("1+1")
            self.assertTrue(first.run_started.wait(1))

            self.config["voice"]["enabled"] = False
            self.voice.reload()
            first.release.set()

            self.assertFalse(self.voice.enabled)
            self.assertGreaterEqual(first.stop_calls, 1)
            self.assertTrue(self._wait_for(lambda: self.voice._current_engine is None))
            self.voice.speak_formula("2+2")
            self.assertEqual(fake_tts.init_calls, 1)

    def test_reload_values_apply_to_next_speech(self):
        engine = FakeEngine()
        fake_tts = FakeTts([engine])

        with patch.dict(sys.modules, {"pyttsx3": types.SimpleNamespace(init=fake_tts.init)}):
            self.config["voice"].update(volume=25, tts_rate=225)
            self.voice.reload()
            self.voice.speak_formula("2+3")

            self.assertTrue(self._wait_for(lambda: engine.said == ["2加3"]))
            self.assertEqual(engine.properties["volume"], 0.25)
            self.assertEqual(engine.properties["rate"], 225)

    def test_missing_audio_engine_degrades_without_repeated_initialization(self):
        with patch.dict(sys.modules, {"pyttsx3": None}):
            self.voice.speak_formula("1+1")
            self.assertTrue(self._wait_for(lambda: self.voice._tts_unavailable))
            worker = self.voice._tts_worker

            for _ in range(5):
                self.voice.speak_formula("2+2")
            time.sleep(0.05)

            self.assertIs(worker, self.voice._tts_worker)
            self.assertTrue(self.voice._tts_unavailable)

    def test_audio_device_failure_is_caught_and_degraded(self):
        fake_tts = FakeTts(init_error=OSError("no audio device"))

        with patch.dict(sys.modules, {"pyttsx3": types.SimpleNamespace(init=fake_tts.init)}):
            self.voice.speak_formula("1+1")
            self.assertTrue(self._wait_for(lambda: self.voice._tts_unavailable))
            self.voice.speak_formula("2+2")
            time.sleep(0.05)

            self.assertEqual(fake_tts.init_calls, 1)
            self.assertIsNone(self.voice._current_engine)


if __name__ == "__main__":
    unittest.main()
