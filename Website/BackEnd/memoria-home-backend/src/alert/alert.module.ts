import { Module } from '@nestjs/common';
import { AlertController } from './alert.controller';
import { AlertService } from './alert.service';
import { GatewayModule } from '../signaling/signaling.module';
import { CaregiverModule } from '../caregiver/caregiver.module';
import { CaregiverService } from '../caregiver/caregiver.service';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Patient } from '../entities/patient.entity';

@Module({
  imports: [GatewayModule, CaregiverModule, TypeOrmModule.forFeature([Patient]),],
  controllers: [AlertController],
  providers: [AlertService, CaregiverService],
})
export class AlertModule {}