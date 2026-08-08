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
        self._state_lock = threading.RLock()
        self._tts_condition = threading.Condition(self._state_lock)
        self._tts_worker = None
        self._tts_pending = None
        self._tts_generation = 0
        self._tts_shutdown = False
        self._enabled = True
        self._volume = 0.8
        self._tts_rate = 150
        self._winsound = None
        self._pyttsx3 = None
        self._tts_lock = threading.Lock()
        self._tts_unavailable = False
        self._tts_warning_logged = False
        self._current_engine = None
        self._refresh_config()

    def _refresh_config(self):
        try:
            cfg = load_app()
            voice = cfg.get("voice", {}) or {}
            symbol_mapping = cfg.get("symbol_mapping", {}) or {}
            enabled = bool(voice.get("enabled", True))
            vol = voice.get("volume", 80)
            volume = max(0.0, min(1.0, float(vol) / 100))
            rate = voice.get("tts_rate", 150)
            tts_rate = max(50, min(400, int(rate)))
        except Exception as e:
            logger.warning("读取 voice 配置失败: %s", e)
            return

        engine = None
        with self._state_lock:
            self._symbol_mapping = symbol_mapping
            self._enabled = enabled
            self._volume = volume
            self._tts_rate = tts_rate
            # reload() 是显式的恢复入口：音频设备暂时不可用时，后续配置保存
            # 可以允许下一次播报重新探测设备。
            self._tts_unavailable = False
            self._tts_warning_logged = False
            if not enabled:
                self._tts_generation += 1
                self._tts_pending = None
                self._tts_condition.notify_all()
                engine = self._current_engine

        if engine is not None:
            self._stop_engine(engine)

    def reload(self):
        self._refresh_config()

    @property
    def enabled(self):
        with self._state_lock:
            return self._enabled

    @property
    def volume(self):
        with self._state_lock:
            return self._volume

    @property
    def tts_rate(self):
        with self._state_lock:
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
        """异步朗读公式；快速触发时只保留最新一条请求。"""
        if not display_text:
            return

        engine = None
        with self._state_lock:
            if (not self._enabled or self._tts_shutdown
                    or self._tts_unavailable):
                return
            self._tts_generation += 1
            generation = self._tts_generation
            speakable = self._to_speakable(display_text, self._symbol_mapping)
            # 公式朗读属于瞬时反馈，保留最新内容比排队播报旧内容更符合
            # 计算器交互预期，也能避免快速点击时积累大量线程。
            self._tts_pending = (generation, speakable)
            self._ensure_tts_worker_locked()
            self._tts_condition.notify()
            engine = self._current_engine

        # runAndWait() 可能阻塞 worker；停止当前引擎让它尽快回到队列，
        # 但不影响已经被新请求替换的 pending 内容。
        if engine is not None:
            self._stop_engine(engine)

    def _ensure_tts_worker_locked(self):
        worker = self._tts_worker
        if worker is not None and worker.is_alive():
            return
        if self._tts_shutdown:
            return
        worker = threading.Thread(
            target=self._tts_worker_loop,
            name="VoiceEngine-TTS",
            daemon=True,
        )
        self._tts_worker = worker
        worker.start()

    def _tts_worker_loop(self):
        while True:
            with self._tts_condition:
                while self._tts_pending is None and not self._tts_shutdown:
                    self._tts_condition.wait()
                if self._tts_shutdown:
                    return
                generation, text = self._tts_pending
                self._tts_pending = None

            try:
                self._speak_sync(text, generation)
            except Exception as e:
                # 防止第三方驱动异常退出 worker，后续 stop/reload 仍可用。
                logger.warning("TTS worker 异常: %s", e)

    def _load_tts_module(self):
        with self._tts_lock:
            with self._state_lock:
                if self._pyttsx3 is not None:
                    return self._pyttsx3
                if self._tts_unavailable:
                    return None
            try:
                import pyttsx3
            except Exception as e:
                self._mark_tts_unavailable("pyttsx3 不可用，跳过 TTS 朗读", e)
                return None

            with self._state_lock:
                self._pyttsx3 = pyttsx3
            return pyttsx3

    def _mark_tts_unavailable(self, message, error=None):
        with self._state_lock:
            first_warning = not self._tts_warning_logged
            self._tts_unavailable = True
            self._tts_warning_logged = True
        if first_warning:
            if error is None:
                logger.warning(message)
            else:
                logger.warning("%s: %s", message, error)

    def _speak_sync(self, text, generation=None):
        """由唯一 worker 调用；保留同步入口便于测试和兼容内部调用。"""
        if not text:
            return

        with self._state_lock:
            if generation is None:
                generation = self._tts_generation
            if (not self._enabled or self._tts_shutdown
                    or generation != self._tts_generation
                    or self._tts_unavailable):
                return

        tts = self._load_tts_module()
        if tts is None:
            return

        try:
            engine = tts.init()
        except Exception as e:
            self._mark_tts_unavailable("TTS 引擎初始化失败，已静默降级", e)
            return

        if engine is None:
            self._mark_tts_unavailable("TTS 引擎初始化返回空对象，已静默降级")
            return

        try:
            with self._state_lock:
                if (not self._enabled or self._tts_shutdown
                        or generation != self._tts_generation):
                    return

                # 在 state lock 内完成 say，stop() 要么在 say 前取消请求，
                # 要么在 say 后中断 runAndWait，避免停止竞态遗漏。
                self._current_engine = engine
                self._configure_voice(engine)
                engine.setProperty("volume", self._volume)
                engine.setProperty("rate", self._tts_rate)
                engine.say(text)

            engine.runAndWait()
        except Exception as e:
            with self._state_lock:
                cancelled = (not self._enabled
                             or self._tts_shutdown
                             or generation != self._tts_generation)
            if not cancelled:
                self._mark_tts_unavailable("TTS 朗读失败，已静默降级", e)
        finally:
            # pyttsx3 没有统一的 close API，stop() 是官方引擎释放当前
            # driver/event loop 的方式；无论成功、取消还是异常都执行。
            self._stop_engine(engine)
            with self._state_lock:
                if self._current_engine is engine:
                    self._current_engine = None

    def stop(self):
        """取消待播内容并立即停止当前 TTS；多次调用安全。"""
        with self._state_lock:
            self._tts_generation += 1
            self._tts_pending = None
            self._tts_condition.notify_all()
            engine = self._current_engine
        if engine is None:
            return
        self._stop_engine(engine)

    def _stop_engine(self, engine):
        try:
            engine.stop()
        except Exception as e:
            logger.warning("TTS 停止失败: %s", e)

    def shutdown(self):
        """停止 worker 并释放当前引擎，供测试或应用退出时调用。"""
        with self._state_lock:
            self._tts_shutdown = True
            self._tts_generation += 1
            self._tts_pending = None
            self._tts_condition.notify_all()
            engine = self._current_engine
            worker = self._tts_worker
        if engine is not None:
            self._stop_engine(engine)
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=1.0)
        with self._state_lock:
            if self._tts_worker is worker and worker is not None and not worker.is_alive():
                self._tts_worker = None

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
