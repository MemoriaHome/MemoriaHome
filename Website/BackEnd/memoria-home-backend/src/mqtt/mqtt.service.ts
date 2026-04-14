import { Injectable } from '@nestjs/common';
import { MqttClient, connect } from 'mqtt';

@Injectable()
export class MqttService {
  public readonly mqtt: MqttClient;

  constructor() {
    this.mqtt = connect("tcp://localhost:1883/", {
      clientId: 'mqtt-website',
      clean: true,
      connectTimeout: 4000,
      username: "smartwatch",
      password: "hhhhhh",
      reconnectPeriod: 1000,
    });

    this.mqtt.on('connect', () => {console.log('Connected to MQTT server');});
    this.mqtt.on('error', (err) => {console.error('MQTT error:', err);})
    }

    subscribe(topic: string, callback: (msg: string) => void){
        this.mqtt.subscribe(topic, { qos: 1 });
        this.mqtt.on('message', (t, msg) => {
            if(t == topic) callback(msg.toString())
        });
    }

    publish(topic: string, message: string){
        this.mqtt.publish(topic, message);
    }
}