import {
  Entity,
  PrimaryGeneratedColumn,
  Column,
  CreateDateColumn,
  OneToMany,
} from 'typeorm';
import { PatientAlert } from './patient_alert.entity';

@Entity('alerts')
export class Alert {
  @PrimaryGeneratedColumn()
  alert_id: number;

  @Column({ length: 100 })
  event: string;

  @Column({ default: false })
  escalated: boolean;

  @Column({ length: 100, nullable: true })
  from_device: string;

  @Column({ length: 100, nullable: true })
  room: string;

  @Column({ type: 'text', nullable: true })
  video_url: string;

  @CreateDateColumn()
  timestamp: Date;

  @OneToMany(() => PatientAlert, (pa) => pa.alert)
  patientAlerts: PatientAlert[];
}