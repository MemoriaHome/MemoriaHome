import {
  WebSocketGateway,
  WebSocketServer,
  SubscribeMessage,
  MessageBody,
  ConnectedSocket,
  OnGatewayDisconnect,
} from '@nestjs/websockets';
import { Server, Socket } from 'socket.io';
import { DeviceRegistryService } from './device-registry.service';

@WebSocketGateway({
  cors: {
    origin: '*',
  },
})
export class SignalingGateway implements OnGatewayDisconnect {
  @WebSocketServer()
  server: Server;

  constructor(private readonly deviceRegistry: DeviceRegistryService) {}

  // Called by the Kinect C# app on connect
  @SubscribeMessage('register-device')
  handleRegisterDevice(
    @MessageBody() data: [string, string, string], // [device_id, patient_id, room]
    @ConnectedSocket() client: Socket,
  ) {
    const [deviceId, patientId, room] = data;

    this.deviceRegistry.register({
      deviceId,
      patientId,
      room,
      socketId: client.id,
      connectedAt: new Date(),
    });

    // Acknowledge back to the device
    client.emit('device-registered', {
      success: true,
      deviceId,
      patientId,
      room,
    });

    console.log(`[SignalingGateway] Device registered: ${deviceId} (socket: ${client.id})`);
  }

  // Clean up when the device disconnects
  handleDisconnect(client: Socket) {
    const removed = this.deviceRegistry.unregister(client.id);
    if (removed) {
      console.log(`[SignalingGateway] Device disconnected and removed: ${removed.deviceId}`);
    }
  }
}
