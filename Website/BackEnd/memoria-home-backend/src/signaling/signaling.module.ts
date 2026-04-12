import { Module } from '@nestjs/common';
import { WebrtcGateway } from './signaling.gateway';
import { DeviceRegistryService } from './device-registry.service';

@Module({
  providers: [WebrtcGateway, DeviceRegistryService],
  exports: [DeviceRegistryService, ], // export so other modules (e.g. caregiver) can query devices
})
export class SignalingModule {}
