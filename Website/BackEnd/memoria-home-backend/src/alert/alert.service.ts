import { forwardRef, Inject, Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { CreateFallAlertDto } from './dto/alert.fall.dto';
import { AppGateway } from '../signaling/signaling.gateway';
import { CaregiverService } from '../caregiver/caregiver.service';
import { Patient } from '../entities/patient.entity';
import { Alert } from '../entities/alert.entity';
import { PatientAlert } from '../entities/patient_alert.entity';

@Injectable()
export class AlertService {
  constructor(
    private readonly gateway: AppGateway,
    @Inject(forwardRef(() => CaregiverService))
    private readonly caregiverService: CaregiverService,
    @InjectRepository(Patient)
    private readonly patientRepo: Repository<Patient>,
    @InjectRepository(Alert)
    private readonly alertRepo: Repository<Alert>,
    @InjectRepository(PatientAlert)
    private readonly patientAlertRepo: Repository<PatientAlert>,
  ) {}

  async handleFallAlert(dto: CreateFallAlertDto): Promise<void> {
    console.log(`[FALL ALERT] Patient ${dto.patientId} | Room: ${dto.room} | Event: ${dto.eventType}`);

    // ── 1. Persist the alert row ──────────────────────────────────────────────
    const alert = this.alertRepo.create({
      event:       dto.eventType,
      room:        dto.room,
      video_url:   dto.videoUrl ?? null,
      from_device: dto.deviceId ?? null,
    });
    await this.alertRepo.save(alert);

    // ── 2. Persist the patient ↔ alert junction row ───────────────────────────
    const patientAlert = this.patientAlertRepo.create({
      patient_id: Number(dto.patientId),
      alert_id:   alert.alert_id,
    });
    await this.patientAlertRepo.save(patientAlert);

    // ── 3. Resolve patient name ───────────────────────────────────────────────
    const patient = await this.patientRepo.findOneBy({ patient_id: Number(dto.patientId) });
    const patientName = patient
      ? `${patient.first_name} ${patient.last_name}`
      : 'Unknown';

    // ── 4. Emit to every assigned caregiver ───────────────────────────────────
    const caregiverIds = await this.caregiverService.getCaregiverIdsByPatient(Number(dto.patientId));
    if (!caregiverIds.length) {
      console.warn(`[FALL ALERT] No caregiver assigned to patient ${dto.patientId}`);
      return;
    }

    for (const caregiverId of caregiverIds) {
      this.gateway.server.to(`caregiver-${caregiverId}`).emit('fall-alert', {
        alertId:     alert.alert_id,
        patientId:   dto.patientId,
        patientName,
        room:        dto.room,
        eventType:   dto.eventType,
        timestamp:   alert.timestamp,
        videoUrl:    dto.videoUrl ?? null,
        severity:    'critical',
      });
    }

    console.log(`[FALL ALERT] Saved (id=${alert.alert_id}) and emitted to caregivers: ${caregiverIds}`);
  }

  // ── Fetch all alerts for patients assigned to a caregiver ──────────────────
  // Used by GET /caregiver/:id/alerts to seed the frontend on page load.
  async getAlertsForCaregiver(caregiverId: number): Promise<object[]> {
    const patientIds = await this.caregiverService.getMyPatients(caregiverId);
    if (!patientIds) return [];

    // Join patient_alerts → alerts → patients in one query
    const rows = await this.patientAlertRepo
      .createQueryBuilder('pa')
      .innerJoinAndSelect('pa.alert',   'a')
      .innerJoinAndSelect('pa.patient', 'p')
      .where('pa.patient_id IN (:...ids)', { ids: patientIds })
      .orderBy('a.timestamp', 'DESC')
      .take(100)           // cap at 100 most-recent; adjust as needed
      .getMany();

    return rows.map((pa) => ({
      alertId:      pa.alert.alert_id,
      patientId:    pa.patient_id,
      patientName:  `${pa.patient.first_name} ${pa.patient.last_name}`,
      eventType:    pa.alert.event,
      room:         pa.alert.room,
      videoUrl:     pa.alert.video_url,
      timestamp:    pa.alert.timestamp,
      severity:     'critical',
      acknowledged: pa.acknowledged,
    }));
  }
}