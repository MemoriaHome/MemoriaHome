import { Module } from '@nestjs/common';
import { AlertController } from './alert.controller';
import { AlertService } from './alert.service';
import { GatewayModule } from '../signaling/signaling.module';
import { CaregiverModule } from '../caregiver/caregiver.module';
import { CaregiverService } from '../caregiver/caregiver.service'

@Module({
  imports: [GatewayModule, CaregiverModule],
  controllers: [AlertController],
  providers: [AlertService, CaregiverService],
})
export class AlertModule {}