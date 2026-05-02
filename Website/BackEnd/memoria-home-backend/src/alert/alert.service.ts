import { Injectable } from '@nestjs/common';
import { CreateFallAlertDto } from './dto/alert.fall.dto';
import { AppGateway } from '../signaling/signaling.gateway';
import { CaregiverService } from '../caregiver/caregiver.service';

@Injectable()
export class AlertService {
  constructor(
    private readonly gateway: AppGateway,
    private readonly caregiverService: CaregiverService,
  ) {}

  async handleFallAlert(dto: CreateFallAlertDto): Promise<void> {
    console.log(`[FALL ALERT] Patient ${dto.patientId} | Room: ${dto.room} | Event: ${dto.eventType}`);

    const caregiverId = await this.caregiverService.getCaregiverIdByPatient(Number(dto.patientId));

    if (!caregiverId) {
      console.warn(`[FALL ALERT] No caregiver assigned to patient ${dto.patientId}`);
      return;
    }

    this.gateway.server.to(`caregiver-${caregiverId}`).emit('fall-alert', {
      patientId: dto.patientId,
      room: dto.room,
      eventType: dto.eventType,
      timestamp: dto.timestamp,
      videoUrl: dto.videoUrl,
    });

    console.log(`[FALL ALERT] Emitted to caregiver-${caregiverId}`);
  }
}