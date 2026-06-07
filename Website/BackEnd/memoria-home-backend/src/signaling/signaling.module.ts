import { Module } from '@nestjs/common';
import { AppGateway } from './signaling.gateway';
import { DeviceRegistryService } from './device-registry.service';

@Module({
  providers: [AppGateway, DeviceRegistryService],
  exports: [AppGateway, DeviceRegistryService],
})
export class GatewayModule {}
