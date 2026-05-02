import { Injectable } from '@nestjs/common';
import { CreateFallAlertDto } from './dto/alert.fall.dto';

@Injectable()
export class AlertService {
  async handleFallAlert(dto: CreateFallAlertDto): Promise<void> {
    console.log(`[FALL ALERT] Patient ${dto.patientId} | Room: ${dto.room} | Event: ${dto.eventType} | ${dto.timestamp}`);
    // Socket.IO push to caregiver dashboard will go here
  }
}