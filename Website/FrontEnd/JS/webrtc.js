// ── webrtc.js ────────────────────────────────────────────────────────────────
// Handles Socket.IO signaling + WebRTC peer connection for the caregiver.
// Depends on: caregiver-dash.js (for currentPatient)
// ─────────────────────────────────────────────────────────────────────────────

const WS_BASE = 'https://localhost:3000';

const ICE_SERVERS = {
  iceServers: [{ urls: 'stun:stun.l.google.com:19302' }]
};

let socket = null;
let peerConnection = null;
let deviceSocketId = null; // Socket.IO ID of the Kinect device
let activeDeviceId = null; // Device identifier string

// ── STATUS UI ────────────────────────────────────────────────────────────────

function setCamStatus(state, text) {
  const dot = document.getElementById('cam-dot');
  const label = document.getElementById('cam-status-text');
  const disconnectBtn = document.getElementById('cam-disconnect-btn');

  if (!dot || !label || !disconnectBtn) return;

  dot.className = 'cam-status-dot cam-status-dot--' + state;
  label.textContent = text;
  disconnectBtn.style.display = state === 'connected' ? 'inline-block' : 'none';
}

function showVideo(show) {
  const placeholder = document.getElementById('cam-placeholder');
  const video = document.getElementById('cam-video');

  if (placeholder) placeholder.style.display = show ? 'none' : 'flex';
  if (video) video.style.display = show ? 'block' : 'none';
}

// ── INITIALIZATION ───────────────────────────────────────────────────────────

function initCamera() {
  if (socket && socket.connected) return;

  if (!currentPatient) {
    setCamStatus('error', 'No patient selected');
    return;
  }

  setCamStatus('searching', 'Connecting to server...');
  showVideo(false);

  socket = io(WS_BASE, {
    transports: ['websocket'],
    rejectUnauthorized: false,
  });

  // Connected to backend
  socket.on('connect', () => {
    console.log('[WebRTC] Connected to signaling server:', socket.id);
    setCamStatus('searching', 'Looking for devices...');
    socket.emit('join-as-caregiver', {
      patientId: String(currentPatient.patient_id),
    });
  });

  // List of available devices
  socket.on('devices-available', (data) => {
    const devices = data?.devices || data || [];
    console.log('[WebRTC] Devices available:', devices);

    if (!devices.length) {
      setCamStatus('idle', 'No camera devices online for this patient');
      return;
    }

    if (devices.length === 1) {
      startCall(devices[0].deviceId, devices[0].socketId);
    } else {
      renderDevicePicker(devices);
    }
  });

  socket.on('no-devices', () => {
    setCamStatus('idle', 'No camera devices online for this patient');
  });

  // SDP answer from the Kinect device
  socket.on('webrtc-answer', async (data) => {
    // Support both array and object payloads
    const payload = Array.isArray(data)
      ? { deviceSocketId: data[0], sdp: data[1] }
      : data;

    const { sdp, deviceSocketId: dSocketId } = payload || {};
    console.log('[WebRTC] Received answer');

    if (dSocketId) deviceSocketId = dSocketId;
    if (!peerConnection || !sdp) return;

    try {
      await peerConnection.setRemoteDescription(
        new RTCSessionDescription({ type: 'answer', sdp })
      );
      console.log('[WebRTC] Remote description set successfully');
    } catch (e) {
      console.error('[WebRTC] setRemoteDescription error:', e);
      setCamStatus('error', 'Failed to establish connection');
    }
  });

  // ICE candidate from the device
  socket.on('ice-candidate', async (data) => {
    const candidate = data?.candidate || (Array.isArray(data) ? data[0]?.candidate : null);
    if (!peerConnection || !candidate) return;

    console.log('[WebRTC] Received ICE candidate from device');
    try {
      await peerConnection.addIceCandidate(new RTCIceCandidate(candidate));
    } catch (e) {
      console.error('[WebRTC] addIceCandidate error:', e);
    }
  });

  socket.on('signaling-error', ({ message }) => {
    console.error('[WebRTC] Signaling error:', message);
    setCamStatus('error', 'Error: ' + message);
  });

  socket.on('disconnect', () => {
    console.log('[WebRTC] Disconnected from signaling server');
    setCamStatus('idle', 'Disconnected');
    showVideo(false);
  });
}

// ── DEVICE PICKER ────────────────────────────────────────────────────────────

function renderDevicePicker(devices) {
  const list = document.getElementById('cam-device-list');
  if (!list) return;

  list.innerHTML = '<p class="cam-device-label">Select a camera:</p>';

  devices.forEach((d) => {
    const btn = document.createElement('button');
    btn.className = 'cam-device-btn';
    btn.textContent = `📷 ${d.room} (${d.deviceId})`;
    btn.onclick = () => {
      list.style.display = 'none';
      startCall(d.deviceId, d.socketId);
    };
    list.appendChild(btn);
  });

  list.style.display = 'block';
  setCamStatus('searching', 'Select a camera to connect');
}

// ── START CALL ───────────────────────────────────────────────────────────────

async function startCall(deviceId, socketId) {
  activeDeviceId = deviceId;
  deviceSocketId = socketId;

  console.log('[WebRTC] Starting call → device:', deviceId, 'socket:', socketId);
  setCamStatus('searching', 'Initiating call...');

  peerConnection = new RTCPeerConnection(ICE_SERVERS);

  // Receive remote video
  peerConnection.ontrack = (event) => {
    console.log('[WebRTC] Remote track received');
    const video = document.getElementById('cam-video');
    if (video) {
      video.srcObject = event.streams[0];
      video.play().catch(() => {});
    }
    showVideo(true);
    setCamStatus('connected', 'Live — ' + activeDeviceId);
  };

  // Send ICE candidates to the device
  peerConnection.onicecandidate = (event) => {
    if (!event.candidate || !deviceSocketId) return;

    console.log('[WebRTC] Sending ICE candidate →', deviceSocketId);
    socket.emit('ice-candidate', {
      targetSocketId: deviceSocketId,
      candidate: event.candidate.toJSON(),
    });
  };

  peerConnection.onconnectionstatechange = () => {
    console.log('[WebRTC] Connection state:', peerConnection.connectionState);

    if (peerConnection.connectionState === 'failed' ||
        peerConnection.connectionState === 'disconnected') {
      setCamStatus('error', 'Connection lost');
      showVideo(false);
    }
  };

  peerConnection.oniceconnectionstatechange = () => {
    console.log('[WebRTC] ICE state:', peerConnection.iceConnectionState);
  };

  // Receive-only video from the Kinect
  peerConnection.addTransceiver('video', { direction: 'recvonly' });

  try {
    const offer = await peerConnection.createOffer({
      offerToReceiveVideo: true,
    });

    await peerConnection.setLocalDescription(offer);

    console.log('[WebRTC] Offer created, sending to backend...');
    socket.emit('webrtc-offer', {
      targetSocketId: deviceSocketId,
      sdp: offer.sdp,
    });

    setCamStatus('searching', 'Waiting for camera response...');
  } catch (e) {
    console.error('[WebRTC] Offer error:', e);
    setCamStatus('error', 'Failed to create offer');
  }

  const feedSelector = document.getElementById('feedSelector');

  feedSelector.addEventListener('change', (e) => {
  const feedType = e.target.value;

  if (!socket || !deviceSocketId) {
    console.warn('[WebRTC] Cannot switch feed: device not connected');
    return;
  }

  socket.emit('switch-camera-feed', {
    targetSocketId: deviceSocketId,
    feedType,
  });

  console.log('[WebRTC] Requested feed switch to:', feedType);
});

}

// ── DISCONNECT ───────────────────────────────────────────────────────────────

function disconnectCamera() {
  console.log('[WebRTC] Disconnecting camera');

  if (peerConnection) {
    peerConnection.close();
    peerConnection = null;
  }

  if (socket) {
    socket.disconnect();
    socket = null;
  }

  deviceSocketId = null;
  activeDeviceId = null;
  showVideo(false);
  setCamStatus('idle', 'Disconnected');

  const list = document.getElementById('cam-device-list');
  if (list) list.style.display = 'none';
}