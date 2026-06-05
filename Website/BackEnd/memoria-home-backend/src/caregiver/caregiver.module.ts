import { Module } from '@nestjs/common';
import { CaregiverService } from './caregiver.service';
import { CaregiverController } from './caregiver.controller';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Caregiver } from '../entities/caregiver.entity';
import { PatientCaregiver } from '../entities/patientToCaregiver.entity';
import { Patient } from '../entities/patient.entity';

@Module({
  imports: [
    TypeOrmModule.forFeature([Caregiver, PatientCaregiver, Patient]),
  ],
  exports: [TypeOrmModule, CaregiverService],
  controllers: [CaregiverController],
  providers: [CaregiverService],
})
export class CaregiverModule {}