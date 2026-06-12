import { Module } from '@nestjs/common';
import { CaregiverService } from './caregiver.service';
import { CaregiverController } from './caregiver.controller';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Caregiver } from '../entities/caregiver.entity';
import { EncryptionService } from '../encryption.service';

@Module({
  imports: [TypeOrmModule.forFeature([Caregiver])],
  exports: [TypeOrmModule],
  controllers: [CaregiverController],
  providers: [CaregiverService, EncryptionService],
})
export class CaregiverModule {}
