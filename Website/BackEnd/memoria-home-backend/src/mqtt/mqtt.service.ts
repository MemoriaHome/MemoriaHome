import { Injectable } from '@nestjs/common';
import { MqttClient, connect } from 'mqtt';

@Injectable()
export class MqttService {
    private readonly mqtt: MqttClient | null;
    private isConnected = false;
    private readonly subscriptions = new Map<string, Array<(msg: string) => void>>();

    constructor() {
      try {
        this.mqtt = connect('tcp://localhost:1883/', {
          clientId: 'mqtt-website',
          clean: true,
          connectTimeout: 4000,
          username: 'smartwatch',
          password: 'hhhhhh',
          reconnectPeriod: 1000,
        });

        this.mqtt.on('connect', () => {
          this.isConnected = true;
          for (const topic of this.subscriptions.keys()) {
            this.subscribeToBroker(topic);
          }
        });

        this.mqtt.on('close', () => {
          this.isConnected = false;
        });

        this.mqtt.on('error', () => {
          this.isConnected = false;
        });

        this.mqtt.on('message', (topic, payload) => {
          const handlers = this.subscriptions.get(topic) ?? [];
          for (const handler of handlers) {
            handler(payload.toString());
          }
        });
      } catch {
        this.mqtt = null;
      }
    }

    subscribe(topic: string, callback: (msg: string) => void) {
      const handlers = this.subscriptions.get(topic) ?? [];
      handlers.push(callback);
      this.subscriptions.set(topic, handlers);
      this.subscribeToBroker(topic);
    }

    publish(topic: string, message: string) {
      if (!this.mqtt || !this.isConnected) {
        return;
      }

      this.mqtt.publish(topic, message, (err) => {
        if (err) {
          console.error(`MQTT publish failed for ${topic}`, err);
        }
      });
    }

    private subscribeToBroker(topic: string) {
      if (!this.mqtt || !this.isConnected) {
        return;
      }

      this.mqtt.subscribe(topic, { qos: 1 }, (err) => {
        if (err) {
          console.error(`MQTT subscribe failed for ${topic}`, err);
        }
      });
    }
  }