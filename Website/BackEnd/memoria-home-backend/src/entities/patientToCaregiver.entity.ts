// patient-caregiver.entity.ts
import {
  Entity,
  PrimaryGeneratedColumn,
  ManyToOne,
  JoinColumn,
  Column,
  Unique,
} from 'typeorm';
import { Patient } from './patient.entity';
import { Caregiver } from './caregiver.entity';

@Entity('patient_caregivers')
@Unique(['patient_id', 'caregiver_id'])
export class PatientCaregiver {

  @PrimaryGeneratedColumn()
  assignment_id: number;

  @Column()
  patient_id: number;

  @ManyToOne(() => Patient, (patient) => patient.assignments, { onDelete: 'CASCADE' })
  @JoinColumn({ name: 'patient_id' })
  patient: Patient;

  @Column()
  caregiver_id: number;

  @ManyToOne(() => Caregiver, (caregiver) => caregiver.assignments, { onDelete: 'CASCADE' })
  @JoinColumn({ name: 'caregiver_id' })
  caregiver: Caregiver;

  @Column({ nullable: true })
  relationship: string;

  @Column({ default: true })
  is_active: boolean;

  @Column({ default: 1 })
  notification_priority: number;
}