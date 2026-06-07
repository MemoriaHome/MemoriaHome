import asyncio
import threading

from shared.config import Config
from webrtc.session_manager import WebRTCSessionManager
from webrtc.signaling_client import SignalingClient
from webrtc.stream_hub import AnnotatedStreamHub
from webrtc.tracks import MicrophoneAudioSource


class KinectWebRTCService:
    """Runs WebRTC signaling/session management on a background asyncio loop."""

    def __init__(self, config: Config, stream_hub: AnnotatedStreamHub):
        self._config = config
        self._stream_hub = stream_hub
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="KinectWebRTC",
        )
        self._task = None
        self._signaling = None
        self._sessions = None

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        if not self._loop.is_running():
            return
        future = asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop)
        try:
            future.result(timeout=5)
        except Exception as exc:
            print(f"[WEBRTC] Shutdown warning: {exc}")
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        audio_source = MicrophoneAudioSource(self._config.kinect_audio_device)
        self._sessions = WebRTCSessionManager(
            self._config,
            self._stream_hub,
            audio_source,
            self._emit,
        )
        self._signaling = SignalingClient(self._config, self._sessions)
        self._task = self._loop.create_task(self._signaling.connect_forever())
        self._loop.run_forever()

    async def _emit(self, event: str, payload: dict) -> None:
        if self._signaling is not None:
            await self._signaling.emit(event, payload)

    async def _shutdown(self) -> None:
        if self._task is not None:
            self._task.cancel()
        if self._sessions is not None:
            await self._sessions.close_all()
        if self._signaling is not None:
            await self._signaling.disconnect()
