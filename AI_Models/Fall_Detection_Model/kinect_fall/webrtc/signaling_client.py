import asyncio

import socketio

from shared.config import Config
from webrtc.session_manager import WebRTCSessionManager


class SignalingClient:
    """Socket.IO signaling client for the Kinect WebRTC sender."""

    def __init__(self, config: Config, sessions: WebRTCSessionManager):
        self._config = config
        self._sessions = sessions
        self._client = socketio.AsyncClient(
            reconnection=True,
            ssl_verify=False,
        )
        self._register_handlers()

    async def emit(self, event: str, payload: dict) -> None:
        await self._client.emit(event, payload)

    async def connect_forever(self) -> None:
        while True:
            try:
                await self._client.connect(self._config.signaling_url)
                await self._client.wait()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"[WEBRTC SIGNALING] Connection failed: {exc}")
                await asyncio.sleep(5)

    async def disconnect(self) -> None:
        if self._client.connected:
            await self._client.disconnect()

    def _register_handlers(self) -> None:
        @self._client.event
        async def connect():
            print("[WEBRTC SIGNALING] Connected.")
            await self._client.emit("register-device", {
                "deviceId": self._config.device_id,
                "patientIds": [str(self._config.patient_id)],
                "room": self._config.room,
                "streams": ["rgb", "depth", "ir"],
            })

        @self._client.event
        async def disconnect():
            print("[WEBRTC SIGNALING] Disconnected.")

        @self._client.on("webrtc-offer")
        async def on_webrtc_offer(payload):
            await self._sessions.handle_offer(payload)

        @self._client.on("webrtc-ice-candidate")
        async def on_webrtc_ice_candidate(payload):
            await self._sessions.handle_remote_candidate(payload)

        @self._client.on("stream-switch-request")
        async def on_stream_switch_request(payload):
            await self._sessions.handle_stream_switch(payload)

        @self._client.on("peer-disconnect")
        async def on_peer_disconnect(payload):
            viewer_socket_id = payload.get("viewerSocketId")
            if viewer_socket_id:
                await self._sessions.close_session(viewer_socket_id)
