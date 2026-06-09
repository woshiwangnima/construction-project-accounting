"""语音播报引擎：按键预录音频（winsound 播放）+ 整段公式实时 TTS（pyttsx3）。

按需懒加载第三方库：pyttsx3 不存在时只静默丢失 TTS；winsound 仅在 Windows 可用。
"""
import os
import sys
import threading

from .config_loader import load_app
from .logger import logger
from .symbol_mapping import voice_key_for_char, voice_speakable_map


if getattr(sys, "frozen", False):
    _BASE_DIR = sys._MEIPASS
else:
    _BASE_DIR = os.path.dirname(os.path.dirname(__file__))
AUDIO_DIR = os.path.join(_BASE_DIR, "assets", "audio")


# 计算器按键 → WAV 文件名
KEY_TO_AUDIO = {
    "0": "0.wav", "1": "1.wav", "2": "2.wav", "3": "3.wav", "4": "4.wav",
    "5": "5.wav", "6": "6.wav", "7": "7.wav", "8": "8.wav", "9": "9.wav",
    "+": "jia.wav", "-": "jian.wav",
    "×": "cheng.wav", "÷": "chu.wav",
    "(": "zuokuohao.wav", ")": "youkuohao.wav",
    ".": "dian.wav",
    "清空": "qingkong.wav", "删除": "shanchu.wav",
}


# 键盘 keysym → 计算器按键
KEYSYM_TO_KEY = {
    **{str(i): str(i) for i in range(10)},
    "plus": "+", "KP_Add": "+",
    "minus": "-", "KP_Subtract": "-",
    "asterisk": "×", "X": "×", "x": "×",
    "slash": "÷", "KP_Divide": "÷",
    "period": ".", "KP_Decimal": ".",
    "parenleft": "(", "parenright": ")",
    "BackSpace": "删除",
}


_SPEAKABLE_MAP = {
    "×": "乘", "÷": "除",
    "[": "中括号 ", "]": " 中括号",
    "{": "大括号 ", "}": " 大括号",
    "(": "左括号", ")": "右括号",
    "+": "加", "-": "减",
    "*": "乘", "/": "除",
}


class VoiceEngine:
    """全局单例：懒加载 pyttsx3 与 winsound，缺失时静默降级。"""

    _instance = None
    _init_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._setup()
                    cls._instance = inst
        return cls._instance

    def _setup(self):
        self._enabled = True
        self._volume = 0.8
        self._tts_rate = 150
        self._winsound = None
        self._pyttsx3 = None
        self._tts_lock = threading.Lock()
        self._current_engine = None
        self._refresh_config()

    def _refresh_config(self):
        try:
            cfg = load_app()
            voice = cfg.get("voice", {}) or {}
            self._symbol_mapping = cfg.get("symbol_mapping", {}) or {}
            self._enabled = bool(voice.get("enabled", True))
            vol = voice.get("volume", 80)
            self._volume = max(0.0, min(1.0, float(vol) / 100))
            rate = voice.get("tts_rate", 150)
            self._tts_rate = max(50, min(400, int(rate)))
        except Exception as e:
            logger.warning("读取 voice 配置失败: %s", e)

    def reload(self):
        self._refresh_config()

    @property
    def enabled(self):
        return self._enabled

    @property
    def volume(self):
        return self._volume

    @property
    def tts_rate(self):
        return self._tts_rate

    def play_key(self, key):
        """播放按键预录音频。非阻塞；缺失文件或不支持的按键直接静默返回。"""
        if not self._enabled:
            return
        filename = KEY_TO_AUDIO.get(key)
        if not filename:
            return
        path = os.path.join(AUDIO_DIR, filename)
        if not os.path.isfile(path):
            return
        if self._winsound is None:
            try:
                import winsound
                self._winsound = winsound
            except ImportError:
                self._winsound = False
        if self._winsound:
            try:
                flags = (self._winsound.SND_FILENAME
                         | self._winsound.SND_ASYNC
                         | self._winsound.SND_NODEFAULT)
                self._winsound.PlaySound(path, flags)
            except Exception as e:
                logger.warning("winsound 播放失败: %s", e)
        else:
            self._fallback_play(path)

    def _fallback_play(self, path):
        """非 Windows 平台的兜底：放到后台线程用 playsound 播（可选依赖）。"""
        def _run():
            try:
                from playsound import playsound
                playsound(path)
            except Exception as e:
                logger.warning("playsound 播放失败: %s", e)
        threading.Thread(target=_run, daemon=True).start()

    def speak_formula(self, display_text):
        """用 TTS 朗读展示形式。异步执行；voice 关闭时直接返回。"""
        if not self._enabled or not display_text:
            return
        speakable = self._to_speakable(display_text, self._symbol_mapping)
        threading.Thread(target=self._speak_sync, args=(speakable,),
                         daemon=True).start()

    def _speak_sync(self, text):
        if self._pyttsx3 is None:
            try:
                import pyttsx3
                self._pyttsx3 = pyttsx3
            except ImportError:
                logger.warning("未安装 pyttsx3，跳过 TTS 朗读")
                return
        with self._tts_lock:
            try:
                engine = self._pyttsx3.init()
                self._current_engine = engine
                self._configure_voice(engine)
                engine.setProperty("volume", self._volume)
                engine.setProperty("rate", self._tts_rate)
                engine.say(text)
                engine.runAndWait()
                engine.stop()
            except Exception as e:
                logger.warning("TTS 朗读失败: %s", e)
            finally:
                self._current_engine = None

    def stop(self):
        """立即停止当前正在朗读的 TTS。多次调用安全（无单例时静默）。"""
        engine = self._current_engine
        if engine is None:
            return
        try:
            engine.stop()
        except Exception as e:
            logger.warning("TTS 停止失败: %s", e)

    def _configure_voice(self, engine):
        try:
            voices = engine.getProperty("voices") or []
            for v in voices:
                ident = (v.id or "").lower()
                name = (v.name or "").lower()
                if ("chinese" in name or "zh" in ident
                        or "cn" in ident or "mandarin" in name):
                    engine.setProperty("voice", v.id)
                    return
        except Exception:
            pass

    @staticmethod
    def _to_speakable(text, symbol_mapping=None):
        speakable = voice_speakable_map(symbol_mapping)
        speakable.update(_SPEAKABLE_MAP)
        for k, v in speakable.items():
            text = text.replace(k, v)
        return text


def get_voice() -> VoiceEngine:
    return VoiceEngine()
