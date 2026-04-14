import { WebSocketGateway, WebSocketServer, OnGatewayInit, OnGatewayConnection, OnGatewayDisconnect } from '@nestjs/websockets';
import { Server } from 'socket.io';
import { MqttService } from './mqtt.service';

@WebSocketGateway({ cors: { origin: '*' } })
export class MqttGateway implements OnGatewayInit, OnGatewayConnection, OnGatewayDisconnect {
  @WebSocketServer() server: Server;

  constructor(private readonly mqttService: MqttService) {}

  afterInit() {
    console.log("afterinit called");
    try {
        this.mqttService.subscribe('watch-data', (msg) => {
        this.server.emit('heartrate', msg);
        });
    }
    catch (err) {
        console.error("Mqtt subscription failed: ", err);
    }
  }

  handleConnection(client: any) { 
    console.log('Client connected:', client.id);
  }

  handleDisconnect(client: any) { 
    console.log('Client disconnected:', client.id);
  }

}