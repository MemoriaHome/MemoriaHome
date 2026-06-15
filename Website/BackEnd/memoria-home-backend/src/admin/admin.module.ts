import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { AdminController } from './admin.controller';
import { AdminService } from './admin.service';
import { Patient } from '../entities/patient.entity';
import { User } from '../entities/user.entity';
import { PatientCaregiver } from '../entities/patientToCaregiver.entity';
import { Caregiver } from '../entities/caregiver.entity';
import { BreakGlassAccessLog } from '../entities/break_glass_access_log.entity';
import { Domain } from '../entities/domain.entity';
import { Admin } from '../entities/admin.entity';
import { Family } from '../entities/family.entity';
import { FamilyPatient } from '../entities/family_patient.entity';
import { JwtModule } from '@nestjs/jwt';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';

 
@Module({
  imports: [
    TypeOrmModule.forFeature([
      Admin,
      Caregiver,
      Domain,
      Family,
      FamilyPatient,
      Patient,
      User,
      PatientCaregiver,
      BreakGlassAccessLog,
    ]),
    JwtModule.register({
      secret: process.env.JWT_SECRET || 'superSecretKey',
      signOptions: { expiresIn: '1d' },
    }),
  ],
  controllers: [AdminController],
  providers: [AdminService, JwtAuthGuard],
})
export class AdminModule {}
