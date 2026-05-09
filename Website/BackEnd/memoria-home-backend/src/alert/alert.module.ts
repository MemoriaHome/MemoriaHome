import { Module } from '@nestjs/common';
import { AlertController } from './alert.controller';
import { AlertService } from './alert.service';
import { CaregiverModule } from '../caregiver/caregiver.module';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Patient } from '../entities/patient.entity';
import { Alert } from '../entities/alert.entity';
import { PatientAlert } from '../entities/patient_alert.entity';
import { GatewayModule } from '../signaling/signaling.module';

@Module({
  imports: [
    GatewayModule,
    CaregiverModule,
    TypeOrmModule.forFeature([Patient, Alert, PatientAlert]),
  ],
  controllers: [AlertController],
  providers: [AlertService],
  exports: [AlertService],
})
export class AlertModule {}