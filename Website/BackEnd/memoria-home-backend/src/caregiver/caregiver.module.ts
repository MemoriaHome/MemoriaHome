import { Module } from '@nestjs/common';
import { CaregiverService } from './caregiver.service';
import { CaregiverController } from './caregiver.controller';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Caregiver } from '../entities/caregiver.entity';
import { PatientCaregiver } from '../entities/patientToCaregiver.entity';
import { Patient } from '../entities/patient.entity';
import { JwtModule } from '@nestjs/jwt';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';

@Module({
  imports: [
    TypeOrmModule.forFeature([Caregiver, PatientCaregiver, Patient]),
    JwtModule.register({
      secret: process.env.JWT_SECRET || 'superSecretKey',
      signOptions: { expiresIn: '1d' },
    }),
  ],
  exports: [TypeOrmModule, CaregiverService],
  controllers: [CaregiverController],
  providers: [CaregiverService, JwtAuthGuard],
})
export class CaregiverModule {}
