import { Injectable } from '@nestjs/common';
import { MqttService } from "./mqtt/mqtt.service"

@Injectable()
export class AppService {
  getHello(): string {
    return 'Hello World!';
  }

  constructor(private readonly mqttService: MqttService){
    this.mqttService.publish('to-watch', 'hello from backend!');
    this.mqttService.subscribe('watch-data', (msg) => console.log(msg));
  }
}
