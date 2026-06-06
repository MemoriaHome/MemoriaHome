import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { CreateFallAlertDto } from './dto/alert.fall.dto';
import { AppGateway } from '../signaling/signaling.gateway';
import { CaregiverService } from '../caregiver/caregiver.service';
import { Patient } from '../entities/patient.entity';
import { Alert } from '../entities/alert.entity';
import { PatientAlert } from '../entities/patient_alert.entity';

const ESCALATION_MS = 10_000;

@Injectable()
export class AlertService {

  // Tracks pending escalation timers by alert_id — cleared on acknowledge
  private readonly escalationTimers = new Map<number, NodeJS.Timeout>();

  constructor(
    private readonly gateway: AppGateway,
    private readonly caregiverService: CaregiverService,
    @InjectRepository(Patient)
    private readonly patientRepo: Repository<Patient>,
    @InjectRepository(Alert)
    private readonly alertRepo: Repository<Alert>,
    @InjectRepository(PatientAlert)
    private readonly patientAlertRepo: Repository<PatientAlert>,
  ) {}

  // ── Handle incoming fall alert ─────────────────────────────────────────────
  async handleFallAlert(dto: CreateFallAlertDto): Promise<void> {
    console.log(`[FALL ALERT] Patient ${dto.patientId} | Room: ${dto.room} | Event: ${dto.eventType}`);

    // 1. Persist alert row
    const alert = this.alertRepo.create({
      event:       dto.eventType,
      room:        dto.room,
      video_url:   dto.videoUrl   ?? null,
      from_device: dto.deviceId   ?? null,
    });
    await this.alertRepo.save(alert);

    // 2. Persist patient <-> alert junction
    const patientAlert = this.patientAlertRepo.create({
      patient_id: Number(dto.patientId),
      alert_id:   alert.alert_id,
    });
    await this.patientAlertRepo.save(patientAlert);

    // 3. Resolve patient name
    const patient = await this.patientRepo.findOneBy({ patient_id: Number(dto.recognizedPatientId) });
    const patientName = patient ? `${patient.first_name} ${patient.last_name}` : 'Unknown';

    // 4. Emit to assigned caregivers
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

    console.log(`[FALL ALERT] Saved (id=${alert.alert_id}) — escalation in ${ESCALATION_MS / 1000}s`);

    // 5. Start escalation countdown
    const timer = setTimeout(
      () => this.escalate(alert.alert_id, patientName, dto.room),
      ESCALATION_MS,
    );
    this.escalationTimers.set(alert.alert_id, timer);
  }

  // ── Escalation (fires when not acknowledged in time) ──────────────────────
  private async escalate(alertId: number, patientName: string, room: string): Promise<void> {
    this.escalationTimers.delete(alertId);
    await this.alertRepo.update(alertId, { escalated: true });
    console.warn(
      `[ESCALATED] Alert #${alertId} | Patient: ${patientName} | Room: ${room} | ` +
      `Not acknowledged within ${ESCALATION_MS / 1000}s`,
    );
  }

  // ── Acknowledge ────────────────────────────────────────────────────────────
  async acknowledgeAlert(alertId: number, caregiverId: number): Promise<{ success: boolean }> {
    const timer = this.escalationTimers.get(alertId);
    if (timer) {
      clearTimeout(timer);
      this.escalationTimers.delete(alertId);
      console.log(`[ACK] Alert #${alertId} acknowledged by caregiver #${caregiverId} — escalation cancelled`);
    } else {
      console.log(`[ACK] Alert #${alertId} acknowledged by caregiver #${caregiverId} (timer already expired)`);
    }

    // acknowledged_by is a FK to users(user_id) — resolve from caregiver_id
    const userId = await this.caregiverService.getUserIdByCaregiver(caregiverId);

    await this.patientAlertRepo.update(
      { alert_id: alertId },
      {
        acknowledged:    true,
        acknowledged_at: new Date(),
        acknowledged_by: userId ?? undefined,
      },
    );

    return { success: true };
  }

  // ── Fetch alerts for a caregiver's patients (seeds frontend on page load) ──
  async getAlertsForCaregiver(caregiverId: number): Promise<object[]> {
    const patientIds = await this.caregiverService.getPatientIdsByCaregiver(caregiverId);
    if (!patientIds.length) return [];

    const rows = await this.patientAlertRepo
      .createQueryBuilder('pa')
      .innerJoinAndSelect('pa.alert',   'a')
      .innerJoinAndSelect('pa.patient', 'p')
      .where('pa.patient_id IN (:...ids)', { ids: patientIds })
      .orderBy('a.timestamp', 'DESC')
      .take(100)
      .getMany();

    return rows.map((pa) => ({
      alertId:        pa.alert.alert_id,
      patientId:      pa.patient_id,
      patientName:    `${pa.patient.first_name} ${pa.patient.last_name}`,
      eventType:      pa.alert.event,
      room:           pa.alert.room,
      videoUrl:       pa.alert.video_url,
      timestamp:      pa.alert.timestamp,
      severity:       'critical',
      acknowledged:   pa.acknowledged,
      acknowledgedAt: pa.acknowledged_at,
    }));
  }
}