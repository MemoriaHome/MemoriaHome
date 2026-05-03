import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { CreateFallAlertDto } from './dto/alert.fall.dto';
import { AppGateway } from '../signaling/signaling.gateway';
import { CaregiverService } from '../caregiver/caregiver.service';
import { Patient } from '../entities/patient.entity';

@Injectable()
export class AlertService {
  constructor(
    private readonly gateway: AppGateway,
    private readonly caregiverService: CaregiverService,
    @InjectRepository(Patient)
    private readonly patientRepo: Repository<Patient>,
  ) {}

async handleFallAlert(dto: CreateFallAlertDto): Promise<void> {
  console.log(`[FALL ALERT] Patient ${dto.patientId} | Room: ${dto.room} | Event: ${dto.eventType}`);

  const caregiverIds = await this.caregiverService.getCaregiverIdsByPatient(Number(dto.patientId));

  if (!caregiverIds.length) {
    console.warn(`[FALL ALERT] No caregiver assigned to patient ${dto.patientId}`);
    return;
  }

  const patient = await this.patientRepo.findOneBy({ patient_id: Number(dto.patientId) });
  const patientName = patient ? `${patient.first_name} ${patient.last_name}` : 'Unknown';

  for (const caregiverId of caregiverIds) {
    this.gateway.server.to(`caregiver-${caregiverId}`).emit('fall-alert', {
      patientId: dto.patientId,
      patientName,
      room: dto.room,
      eventType: dto.eventType,
      timestamp: dto.timestamp,
      videoUrl: dto.videoUrl,
    });
  }

  console.log(`[FALL ALERT] Emitted to caregivers: ${caregiverIds}`);
  }
}