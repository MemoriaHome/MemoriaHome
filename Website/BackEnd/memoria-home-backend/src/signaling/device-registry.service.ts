import { Injectable } from '@nestjs/common';

export interface RegisteredDevice {
  deviceId: string;
  patientId: string;
  room: string;
  socketId: string;
  connectedAt: Date;
}

@Injectable()
export class DeviceRegistryService {
  private readonly devices = new Map<string, RegisteredDevice>();

  register(device: RegisteredDevice): void {
    this.devices.set(device.deviceId, device);
    console.log(`[DeviceRegistry] Registered device: ${device.deviceId} for patient ${device.patientId} in "${device.room}"`);
  }

  unregister(socketId: string): RegisteredDevice | undefined {
    for (const [deviceId, device] of this.devices) {
      if (device.socketId === socketId) {
        this.devices.delete(deviceId);
        console.log(`[DeviceRegistry] Unregistered device: ${deviceId}`);
        return device;
      }
    }
    return undefined;
  }

  getByPatientId(patientId: string): RegisteredDevice[] {
    return [...this.devices.values()].filter(d => d.patientId === patientId);
  }

  getByDeviceId(deviceId: string): RegisteredDevice | undefined {
    return this.devices.get(deviceId);
  }

  getAll(): RegisteredDevice[] {
    return [...this.devices.values()];
  }
}
