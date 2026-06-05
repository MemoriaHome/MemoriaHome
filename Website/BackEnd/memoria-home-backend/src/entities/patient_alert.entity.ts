import {
  Entity,
  PrimaryGeneratedColumn,
  Column,
  ManyToOne,
  JoinColumn,
  Unique,
} from 'typeorm';
import { Patient } from './patient.entity';
import { Alert } from './alert.entity';

@Entity('patient_alerts')
@Unique(['patient_id', 'alert_id'])
export class PatientAlert {
  @PrimaryGeneratedColumn()
  patient_alert_id: number;

  @Column()
  patient_id: number;

  @Column()
  alert_id: number;

  @Column({ default: false })
  acknowledged: boolean;

  @Column({ type: 'timestamp', nullable: true })
  acknowledged_at: Date;

  @Column({ nullable: true })
  acknowledged_by: number;   // user_id of the caregiver/admin who dismissed it

  @ManyToOne(() => Patient, { onDelete: 'CASCADE' })
  @JoinColumn({ name: 'patient_id' })
  patient: Patient;

  @ManyToOne(() => Alert, (a) => a.patientAlerts, { onDelete: 'CASCADE' })
  @JoinColumn({ name: 'alert_id' })
  alert: Alert;
}