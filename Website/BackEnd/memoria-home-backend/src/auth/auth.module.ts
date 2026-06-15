import { Module } from '@nestjs/common';
import { JwtModule } from '@nestjs/jwt';
import { PassportModule } from '@nestjs/passport';
import { AuthService } from './auth.service';
import { Caregiver } from '../entities/caregiver.entity';
import { TypeOrmModule } from '@nestjs/typeorm';
import { CaregiverModule } from '../caregiver/caregiver.module';
import { AuthController } from './auth.controller';
import { User } from '../entities/user.entity';
import { BreakGlassAccessLog } from '../entities/break_glass_access_log.entity';
import { Domain } from '../entities/domain.entity';
import { Admin } from '../entities/admin.entity';
import { Family } from '../entities/family.entity';
import { Patient } from '../entities/patient.entity';
import { FamilyPatient } from '../entities/family_patient.entity';
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
      BreakGlassAccessLog,
    ]),
    PassportModule,
    JwtModule.register({
      secret: process.env.JWT_SECRET || 'superSecretKey', // Use env variable in production
      signOptions: { expiresIn: '1d' }, // Token validity
    }),
    CaregiverModule,
  ],
  controllers: [AuthController],
  providers: [AuthService],
  exports: [AuthService, JwtModule]
})
export class AuthModule {}
