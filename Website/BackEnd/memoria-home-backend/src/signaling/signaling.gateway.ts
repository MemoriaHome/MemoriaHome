import {
  WebSocketGateway,
  WebSocketServer,
  SubscribeMessage,
  ConnectedSocket,
  MessageBody,
  OnGatewayDisconnect,
} from '@nestjs/websockets';
import { Server, Socket } from 'socket.io';
import { DeviceRegistryService } from './device-registry.service';

@WebSocketGateway({ cors: { origin: '*' } })
export class AppGateway implements OnGatewayDisconnect {
  @WebSocketServer()
  server: Server;

  private readonly viewerDevices = new Map<string, Set<string>>();

  constructor(private readonly devices: DeviceRegistryService) {}

  @SubscribeMessage('join-as-caregiver')
  handleJoinAsCaregiver(
    @MessageBody() body: { caregiverId: string },
    @ConnectedSocket() client: Socket,
  ) {
    const { caregiverId } = body;
    client.join(`caregiver-${caregiverId}`);
    console.log(`[Gateway] Caregiver ${caregiverId} connected (socket ${client.id})`);
  }

  @SubscribeMessage('register-device')
  handleRegisterDevice(
    @MessageBody() body: {
      deviceId: string;
      patientId?: string;
      patientIds?: string[];
      room?: string;
      streams?: string[];
    },
    @ConnectedSocket() client: Socket,
  ) {
    const patientIds = body.patientIds?.length
      ? body.patientIds.map(String)
      : body.patientId
        ? [String(body.patientId)]
        : [];

    this.devices.register({
      deviceId: String(body.deviceId),
      patientIds,
      room: body.room ?? 'Unknown',
      socketId: client.id,
      connectedAt: new Date(),
      streams: body.streams?.length ? body.streams : ['rgb', 'depth', 'ir'],
    });

    client.join(`device-${body.deviceId}`);
    client.emit('device-registered', {
      deviceId: body.deviceId,
      socketId: client.id,
      patientIds,
    });
  }

  @SubscribeMessage('device-list')
  handleDeviceList(
    @MessageBody() body: { patientId: string },
    @ConnectedSocket() client: Socket,
  ) {
    const devices = this.devices.getByPatientId(String(body.patientId));
    client.emit('device-list-result', {
      patientId: String(body.patientId),
      devices: devices.map((device) => ({
        deviceId: device.deviceId,
        room: device.room,
        streams: device.streams,
        connectedAt: device.connectedAt,
      })),
    });
  }

  @SubscribeMessage('webrtc-offer')
  handleWebrtcOffer(
    @MessageBody() body: Record<string, any>,
    @ConnectedSocket() client: Socket,
  ) {
    const device = this.devices.getByDeviceId(String(body.deviceId));
    if (!device) {
      client.emit('webrtc-error', {
        reason: 'device_not_found',
        deviceId: body.deviceId,
      });
      return;
    }

    this.server.to(device.socketId).emit('webrtc-offer', {
      ...body,
      viewerSocketId: client.id,
    });
    this.rememberViewerDevice(client.id, device.deviceId);
  }

  @SubscribeMessage('webrtc-answer')
  handleWebrtcAnswer(@MessageBody() body: Record<string, any>) {
    if (body.viewerSocketId) {
      this.server.to(String(body.viewerSocketId)).emit('webrtc-answer', body);
    }
  }

  @SubscribeMessage('webrtc-ice-candidate')
  handleWebrtcIceCandidate(
    @MessageBody() body: Record<string, any>,
    @ConnectedSocket() client: Socket,
  ) {
    if (body.viewerSocketId) {
      this.server.to(String(body.viewerSocketId)).emit('webrtc-ice-candidate', body);
      return;
    }

    if (body.deviceId) {
      const device = this.devices.getByDeviceId(String(body.deviceId));
      if (device && device.socketId !== client.id) {
        this.server.to(device.socketId).emit('webrtc-ice-candidate', {
          ...body,
          viewerSocketId: client.id,
        });
      }
    }
  }

  @SubscribeMessage('stream-switch-request')
  handleStreamSwitchRequest(
    @MessageBody() body: Record<string, any>,
    @ConnectedSocket() client: Socket,
  ) {
    const device = this.devices.getByDeviceId(String(body.deviceId));
    if (!device) {
      client.emit('stream-switch-result', {
        ...body,
        ok: false,
        reason: 'device_not_found',
      });
      return;
    }

    this.server.to(device.socketId).emit('stream-switch-request', {
      ...body,
      viewerSocketId: client.id,
    });
  }

  @SubscribeMessage('stream-switch-result')
  handleStreamSwitchResult(@MessageBody() body: Record<string, any>) {
    if (body.viewerSocketId) {
      this.server.to(String(body.viewerSocketId)).emit('stream-switch-result', body);
    }
  }

  @SubscribeMessage('peer-disconnect')
  handlePeerDisconnect(
    @MessageBody() body: Record<string, any>,
    @ConnectedSocket() client: Socket,
  ) {
    if (body.deviceId) {
      const device = this.devices.getByDeviceId(String(body.deviceId));
      if (device && device.socketId !== client.id) {
        this.server.to(device.socketId).emit('peer-disconnect', {
          ...body,
          viewerSocketId: client.id,
        });
      }
      this.forgetViewerDevice(client.id, String(body.deviceId));
    }

    if (body.viewerSocketId) {
      this.server.to(String(body.viewerSocketId)).emit('peer-disconnect', body);
    }
  }

  handleDisconnect(client: Socket) {
    const device = this.devices.unregister(client.id);
    if (device) {
      this.server.emit('device-disconnected', { deviceId: device.deviceId });
      this.removeDeviceFromViewers(device.deviceId);
    } else {
      this.notifyDevicesForViewer(client.id);
    }
    console.log(`[Gateway] Client disconnected: ${client.id}`);
  }

  private rememberViewerDevice(viewerSocketId: string, deviceId: string): void {
    const devices = this.viewerDevices.get(viewerSocketId) ?? new Set<string>();
    devices.add(deviceId);
    this.viewerDevices.set(viewerSocketId, devices);
  }

  private forgetViewerDevice(viewerSocketId: string, deviceId: string): void {
    const devices = this.viewerDevices.get(viewerSocketId);
    if (!devices) return;
    devices.delete(deviceId);
    if (!devices.size) {
      this.viewerDevices.delete(viewerSocketId);
    }
  }

  private notifyDevicesForViewer(viewerSocketId: string): void {
    const deviceIds = this.viewerDevices.get(viewerSocketId);
    if (!deviceIds) return;

    for (const deviceId of deviceIds) {
      const device = this.devices.getByDeviceId(deviceId);
      if (device) {
        this.server.to(device.socketId).emit('peer-disconnect', {
          deviceId,
          viewerSocketId,
        });
      }
    }
    this.viewerDevices.delete(viewerSocketId);
  }

  private removeDeviceFromViewers(deviceId: string): void {
    for (const [viewerSocketId, devices] of this.viewerDevices.entries()) {
      devices.delete(deviceId);
      if (!devices.size) {
        this.viewerDevices.delete(viewerSocketId);
      }
    }
  }
}
