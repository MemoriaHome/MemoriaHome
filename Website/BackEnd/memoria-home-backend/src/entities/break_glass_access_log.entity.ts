import { Column, Entity, JoinColumn, ManyToOne, PrimaryGeneratedColumn } from 'typeorm';
import { Caregiver } from './caregiver.entity';
import { Patient } from './patient.entity';

@Entity('break_glass_access_logs')
export class BreakGlassAccessLog {
  @PrimaryGeneratedColumn()
  break_glass_access_log_id: number;

  @Column()
  caregiver_id: number;

  @ManyToOne(() => Caregiver, { onDelete: 'CASCADE' })
  @JoinColumn({ name: 'caregiver_id' })
  caregiver: Caregiver;

  @Column()
  patient_id: number;

  @ManyToOne(() => Patient, { onDelete: 'CASCADE' })
  @JoinColumn({ name: 'patient_id' })
  patient: Patient;

  @Column({ type: 'text' })
  reason: string;

  @Column({ name: 'accessed_stream', length: 20 })
  accessed_stream: string;

  @Column({ type: 'timestamp', default: () => 'CURRENT_TIMESTAMP' })
  timestamp: Date;
}
