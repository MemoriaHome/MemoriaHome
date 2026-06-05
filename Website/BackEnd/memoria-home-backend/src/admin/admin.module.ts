import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { AdminController } from './admin.controller';
import { AdminService } from './admin.service';
import { Patient } from '../entities/patient.entity';
import { User } from '../entities/user.entity';
import { PatientCaregiver } from '../entities/patientToCaregiver.entity';
import { Caregiver } from '../entities/caregiver.entity';

 
@Module({
  imports: [TypeOrmModule.forFeature([Patient, User, PatientCaregiver, Caregiver])],
  controllers: [AdminController],
  providers: [AdminService],
})
export class AdminModule {}