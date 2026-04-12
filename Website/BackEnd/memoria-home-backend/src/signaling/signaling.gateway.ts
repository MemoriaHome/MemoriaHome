import {
  WebSocketGateway,
  WebSocketServer,
  SubscribeMessage,
  ConnectedSocket,
  MessageBody,
  OnGatewayDisconnect,
} from '@nestjs/websockets';
import { Server, Socket } from 'socket.io';

interface DeviceInfo {
  deviceId: string;
  patientId: string;
  room: string;
  socketId: string;
}

@WebSocketGateway({
  cors: {
    origin: '*',
  },
})
export class WebrtcGateway implements OnGatewayDisconnect {
  @WebSocketServer()
  server: Server;

  // Map socketId → DeviceInfo
  private devices = new Map<string, DeviceInfo>();

  // ── DEVICE REGISTRATION ────────────────────────────────────────────────────
  @SubscribeMessage('register-device')
  handleRegisterDevice(
    @MessageBody() data: [string, string, string],
    @ConnectedSocket() client: Socket,
  ) {
    const [deviceId, patientId, room] = data;

    const device: DeviceInfo = {
      deviceId,
      patientId,
      room,
      socketId: client.id,
    };

    this.devices.set(client.id, device);
    client.join(`patient-${patientId}`);

    console.log(
      `[Gateway] Device registered: ${deviceId} (patient ${patientId}, socket ${client.id})`,
    );
  }

  // ── CAREGIVER JOINS ────────────────────────────────────────────────────────
  @SubscribeMessage('join-as-caregiver')
  handleJoinAsCaregiver(
    @MessageBody() body: { patientId: string },
    @ConnectedSocket() client: Socket,
  ) {
    const { patientId } = body;
    client.join(`patient-${patientId}`);

    const devices = Array.from(this.devices.values()).filter(
      (d) => d.patientId === patientId,
    );

    if (devices.length > 0) {
      client.emit('devices-available', { devices });
    } else {
      client.emit('no-devices');
    }

    console.log(
      `[Gateway] Caregiver ${client.id} joined patient ${patientId}`,
    );
  }

  // ── WEBRTC OFFER ───────────────────────────────────────────────────────────
  @SubscribeMessage('webrtc-offer')
  handleWebrtcOffer(
    @MessageBody()
    body: { targetSocketId: string; sdp: string },
    @ConnectedSocket() client: Socket,
  ) {
    const { targetSocketId, sdp } = body;

    this.server.to(targetSocketId).emit('webrtc-offer', {
      sdp,
      caregiverSocketId: client.id,
    });

    console.log(
      `[Gateway] Offer from caregiver ${client.id} → device ${targetSocketId}`,
    );
  }

  // ── WEBRTC ANSWER ──────────────────────────────────────────────────────────
  @SubscribeMessage('webrtc-answer')
  handleWebrtcAnswer(
    @MessageBody() data: [string, string],
    @ConnectedSocket() client: Socket,
  ) {
    const [caregiverSocketId, sdp] = data;

    this.server.to(caregiverSocketId).emit('webrtc-answer', {
      sdp,
      deviceSocketId: client.id,
    });

    console.log(
      `[Gateway] Answer from device ${client.id} → caregiver ${caregiverSocketId}`,
    );
  }

  // ── ICE CANDIDATE ──────────────────────────────────────────────────────────
  @SubscribeMessage('ice-candidate')
  handleIceCandidate(
    @MessageBody()
    body: { targetSocketId: string; candidate: any },
    @ConnectedSocket() client: Socket,
  ) {
    const { targetSocketId, candidate } = body;

    this.server.to(targetSocketId).emit('ice-candidate', {
      candidate,
      fromSocketId: client.id,
    });

    console.log(
      `[Gateway] ICE candidate from ${client.id} → ${targetSocketId}`,
    );
  }


    // ── SWITCH FEED ──────────────────────────────────────────────────────────
@SubscribeMessage('switch-camera-feed')
handleSwitchCameraFeed(
  @MessageBody()
  body: { targetSocketId: string; feedType: string },
  @ConnectedSocket() client: Socket,
) {
  const { targetSocketId, feedType } = body;

  this.server.to(targetSocketId).emit('switch-camera-feed', {
    feedType,
    caregiverSocketId: client.id,
  });

  console.log(
    `[Gateway] Caregiver ${client.id} requested ${feedType} feed from device ${targetSocketId}`,
  );
}

  // ── DISCONNECT HANDLING ────────────────────────────────────────────────────
  handleDisconnect(client: Socket) {
    if (this.devices.has(client.id)) {
      console.log(
        `[Gateway] Device disconnected: ${this.devices.get(client.id)} (${client.id})`,
      );
      this.devices.delete(client.id);
    } else {
      console.log(`[Gateway] Client disconnected: ${client.id}`);
    }
  }
}