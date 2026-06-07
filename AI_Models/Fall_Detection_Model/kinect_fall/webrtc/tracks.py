import asyncio
from fractions import Fraction
import queue
import threading

import av
import numpy as np
from aiortc import AudioStreamTrack, VideoStreamTrack

from webrtc.stream_hub import AnnotatedStreamHub, StreamSelector


class KinectVideoTrack(VideoStreamTrack):
    """aiortc video track that follows a per-viewer StreamSelector."""

    def __init__(self, stream_hub: AnnotatedStreamHub, selector: StreamSelector):
        super().__init__()
        self._stream_hub = stream_hub
        self._selector = selector
        self._versions: dict[str, int] = {}

    async def recv(self) -> av.VideoFrame:
        stream_type = self._selector.get()
        last_version = self._versions.get(stream_type, 0)
        frame, version = await asyncio.to_thread(
            self._stream_hub.wait_for_frame,
            stream_type,
            last_version,
            1.0,
        )
        self._versions[stream_type] = version

        if frame is None:
            frame = np.zeros(
                (self._stream_hub.height, self._stream_hub.width, 3),
                dtype=np.uint8,
            )

        video_frame = av.VideoFrame.from_ndarray(frame, format="bgr24")
        video_frame.pts, video_frame.time_base = await self.next_timestamp()
        return video_frame


class MicrophoneAudioSource:
    """Shared microphone reader that creates WebRTC audio tracks on demand."""

    sample_rate = 48000
    channels = 1
    frame_samples = 960

    def __init__(self, device=None):
        self._device = device
        self._tracks: list["MicrophoneAudioTrack"] = []
        self._lock = threading.Lock()
        self._stream = None

    def create_track(self) -> "MicrophoneAudioTrack":
        track = MicrophoneAudioTrack(self)
        with self._lock:
            self._tracks.append(track)
            if self._stream is None:
                self._start_stream()
        return track

    def remove_track(self, track: "MicrophoneAudioTrack") -> None:
        with self._lock:
            if track in self._tracks:
                self._tracks.remove(track)
            if not self._tracks:
                self._stop_stream()

    def _start_stream(self) -> None:
        try:
            import sounddevice as sd

            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                callback=self._audio_callback,
                blocksize=self.frame_samples,
                device=self._device,
            )
            self._stream.start()
            print("[WEBRTC AUDIO] Microphone streaming started.")
        except Exception as exc:
            self._stream = None
            print(f"[WEBRTC AUDIO] Microphone unavailable, sending silence: {exc}")

    def _stop_stream(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
            print("[WEBRTC AUDIO] Microphone streaming stopped.")

    def _audio_callback(self, indata, _frames, _time_info, status) -> None:
        if status:
            print(f"[WEBRTC AUDIO] Mic status: {status}")
        mono = indata[:, 0].astype(np.float32).copy()
        with self._lock:
            tracks = list(self._tracks)
        for track in tracks:
            track.put_samples(mono)


class MicrophoneAudioTrack(AudioStreamTrack):
    """Low-latency mono PCM track; sends silence if capture is unavailable."""

    def __init__(self, source: MicrophoneAudioSource):
        super().__init__()
        self._source = source
        self._queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=8)
        self._timestamp = 0

    def stop(self) -> None:
        super().stop()
        self._source.remove_track(self)

    def put_samples(self, samples: np.ndarray) -> None:
        try:
            self._queue.put_nowait(samples)
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(samples)
            except queue.Full:
                pass

    async def recv(self) -> av.AudioFrame:
        try:
            samples = await asyncio.to_thread(
                self._queue.get,
                True,
                0.2,
            )
        except queue.Empty:
            samples = np.zeros(self._source.frame_samples, dtype=np.float32)

        samples = np.clip(samples, -1.0, 1.0)
        pcm = (samples * 32767).astype(np.int16)
        frame = av.AudioFrame(format="s16", layout="mono", samples=len(pcm))
        frame.planes[0].update(pcm.tobytes())
        frame.sample_rate = self._source.sample_rate
        frame.pts = self._timestamp
        frame.time_base = Fraction(1, self._source.sample_rate)
        self._timestamp += len(pcm)
        return frame
