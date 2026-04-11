import { Module } from '@nestjs/common';
import { SignalingGateway } from './signaling.gateway';
import { DeviceRegistryService } from './device-registry.service';

@Module({
  providers: [SignalingGateway, DeviceRegistryService],
  exports: [DeviceRegistryService], // export so other modules (e.g. caregiver) can query devices
})
export class SignalingModule {}
