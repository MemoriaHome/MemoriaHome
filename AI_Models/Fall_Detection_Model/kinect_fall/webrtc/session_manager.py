import asyncio

import requests
from aiortc import (
    RTCConfiguration,
    RTCPeerConnection,
    RTCSessionDescription,
    RTCRtpSender,
)
from aiortc.sdp import candidate_from_sdp, candidate_to_sdp

from shared.config import Config
from webrtc.stream_hub import AnnotatedStreamHub, StreamSelector, STREAM_TYPES
from webrtc.tracks import KinectVideoTrack, MicrophoneAudioSource


class WebRTCSessionManager:
    """Owns aiortc peer connections and per-caregiver stream selections."""

    def __init__(
        self,
        config: Config,
        stream_hub: AnnotatedStreamHub,
        audio_source: MicrophoneAudioSource,
        emit,
    ):
        self._config = config
        self._stream_hub = stream_hub
        self._audio_source = audio_source
        self._emit = emit
        self._sessions = {}

    async def handle_offer(self, payload: dict) -> None:
        viewer_socket_id = payload["viewerSocketId"]
        requested_stream = self._normalize_stream(payload.get("streamType", "depth"))
        initial_stream = await self._authorized_stream(requested_stream, payload)

        pc = RTCPeerConnection(
            RTCConfiguration(iceServers=[]),
        )
        selector = StreamSelector(initial_stream)
        self._stream_hub.subscribe(initial_stream)

        video_track = KinectVideoTrack(self._stream_hub, selector)
        audio_track = self._audio_source.create_track()
        video_sender = pc.addTrack(video_track)
        pc.addTrack(audio_track)
        self._prefer_h264(pc, video_sender)

        self._sessions[viewer_socket_id] = {
            "pc": pc,
            "selector": selector,
            "stream": initial_stream,
            "video_track": video_track,
            "audio_track": audio_track,
        }

        @pc.on("icecandidate")
        async def on_icecandidate(candidate):
            if candidate is None:
                return
            candidate_sdp = candidate_to_sdp(candidate)
            if not candidate_sdp.startswith("candidate:"):
                candidate_sdp = f"candidate:{candidate_sdp}"
            await self._emit("webrtc-ice-candidate", {
                "deviceId": self._config.device_id,
                "viewerSocketId": viewer_socket_id,
                "candidate": {
                    "candidate": candidate_sdp,
                    "sdpMid": candidate.sdpMid,
                    "sdpMLineIndex": candidate.sdpMLineIndex,
                },
            })

        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            if pc.connectionState in ("failed", "closed", "disconnected"):
                await self.close_session(viewer_socket_id)

        await pc.setRemoteDescription(
            RTCSessionDescription(sdp=payload["sdp"], type=payload["type"])
        )
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)

        await self._emit("webrtc-answer", {
            "deviceId": self._config.device_id,
            "viewerSocketId": viewer_socket_id,
            "viewerId": payload.get("viewerId"),
            "streamType": initial_stream,
            "sdp": pc.localDescription.sdp,
            "type": pc.localDescription.type,
        })

        if initial_stream != requested_stream:
            await self._emit("stream-switch-result", {
                "deviceId": self._config.device_id,
                "viewerSocketId": viewer_socket_id,
                "viewerId": payload.get("viewerId"),
                "ok": False,
                "requestedStreamType": requested_stream,
                "streamType": initial_stream,
                "reason": "break_glass_required",
            })

    async def handle_remote_candidate(self, payload: dict) -> None:
        session = self._sessions.get(payload.get("viewerSocketId"))
        if not session:
            return

        candidate_payload = payload.get("candidate")
        if not candidate_payload:
            await session["pc"].addIceCandidate(None)
            return

        candidate_text = candidate_payload.get("candidate", "")
        if candidate_text.startswith("candidate:"):
            candidate_text = candidate_text.split(":", 1)[1]
        candidate = candidate_from_sdp(candidate_text)
        candidate.sdpMid = candidate_payload.get("sdpMid")
        candidate.sdpMLineIndex = candidate_payload.get("sdpMLineIndex")
        await session["pc"].addIceCandidate(candidate)

    async def handle_stream_switch(self, payload: dict) -> None:
        viewer_socket_id = payload["viewerSocketId"]
        requested_stream = self._normalize_stream(payload.get("streamType", "depth"))
        session = self._sessions.get(viewer_socket_id)
        if not session:
            await self._emit_switch_result(payload, False, requested_stream, None, "session_not_found")
            return

        if not await self._is_stream_allowed(requested_stream, payload):
            await self._emit_switch_result(
                payload,
                False,
                requested_stream,
                session["stream"],
                "break_glass_required",
            )
            return

        old_stream = session["stream"]
        session["selector"].set(requested_stream)
        session["stream"] = requested_stream
        self._stream_hub.switch_subscription(old_stream, requested_stream)
        await self._emit_switch_result(payload, True, requested_stream, requested_stream, None)

    async def close_session(self, viewer_socket_id: str) -> None:
        session = self._sessions.pop(viewer_socket_id, None)
        if not session:
            return

        self._stream_hub.unsubscribe(session["stream"])
        session["audio_track"].stop()
        await session["pc"].close()

    async def close_all(self) -> None:
        for viewer_socket_id in list(self._sessions.keys()):
            await self.close_session(viewer_socket_id)

    async def _emit_switch_result(
        self,
        payload: dict,
        ok: bool,
        requested_stream: str,
        current_stream: str | None,
        reason: str | None,
    ) -> None:
        await self._emit("stream-switch-result", {
            "deviceId": self._config.device_id,
            "viewerSocketId": payload.get("viewerSocketId"),
            "viewerId": payload.get("viewerId"),
            "ok": ok,
            "requestedStreamType": requested_stream,
            "streamType": current_stream,
            "reason": reason,
        })

    async def _authorized_stream(self, requested_stream: str, payload: dict) -> str:
        if await self._is_stream_allowed(requested_stream, payload):
            return requested_stream
        return "depth"

    async def _is_stream_allowed(self, stream_type: str, payload: dict) -> bool:
        if stream_type == "depth":
            return True

        break_glass_token = payload.get("breakGlassToken")
        if not break_glass_token:
            return False

        def verify_break_glass_token() -> bool:
            try:
                response = requests.post(
                    f"{self._config.backend_url}/auth/break-glass/verify",
                    json={
                        "token": break_glass_token,
                        "caregiverId": payload.get("viewerId"),
                        "patientId": payload.get("patientId", self._config.patient_id),
                        "streamType": stream_type,
                    },
                    timeout=5,
                    verify=False,
                )
                response.raise_for_status()
                return bool(response.json().get("valid"))
            except Exception as exc:
                print(f"[WEBRTC] Break-glass verification failed: {exc}")
                return False

        return await asyncio.to_thread(verify_break_glass_token)

    @staticmethod
    def _normalize_stream(stream_type: str) -> str:
        normalized = str(stream_type).lower()
        if normalized == "infrared":
            normalized = "ir"
        if normalized not in STREAM_TYPES:
            return "depth"
        return normalized

    @staticmethod
    def _prefer_h264(pc: RTCPeerConnection, video_sender: RTCRtpSender) -> None:
        capabilities = RTCRtpSender.getCapabilities("video")
        h264_codecs = [
            codec for codec in capabilities.codecs
            if codec.mimeType.lower() == "video/h264"
        ]
        if not h264_codecs:
            return

        for transceiver in pc.getTransceivers():
            if transceiver.sender is video_sender:
                transceiver.setCodecPreferences(h264_codecs)
                return
