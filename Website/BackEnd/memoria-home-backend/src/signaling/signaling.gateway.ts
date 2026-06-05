import {
  WebSocketGateway,
  WebSocketServer,
  SubscribeMessage,
  ConnectedSocket,
  MessageBody,
  OnGatewayDisconnect,
} from '@nestjs/websockets';
import { Server, Socket } from 'socket.io';

@WebSocketGateway({ cors: { origin: '*' } })
export class AppGateway implements OnGatewayDisconnect {
  @WebSocketServer()
  server: Server;

  @SubscribeMessage('join-as-caregiver')
  handleJoinAsCaregiver(
    @MessageBody() body: { caregiverId: string },
    @ConnectedSocket() client: Socket,
  ) {
    const { caregiverId } = body;
    client.join(`caregiver-${caregiverId}`);
    console.log(`[Gateway] Caregiver ${caregiverId} connected (socket ${client.id})`);
  }

  handleDisconnect(client: Socket) {
    console.log(`[Gateway] Client disconnected: ${client.id}`);
  }
}