import { Module } from '@nestjs/common';
import { AppGateway } from './signaling.gateway';

@Module({
  providers: [AppGateway],
  exports: [AppGateway],
})
export class GatewayModule {}