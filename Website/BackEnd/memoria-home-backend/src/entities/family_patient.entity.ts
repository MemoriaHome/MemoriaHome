import {
  Column,
  CreateDateColumn,
  Entity,
  JoinColumn,
  ManyToOne,
  PrimaryGeneratedColumn,
  Unique,
} from 'typeorm';
import { Family } from './family.entity';
import { Patient } from './patient.entity';

@Entity('family_patients')
@Unique(['family_id', 'patient_id'])
export class FamilyPatient {
  @PrimaryGeneratedColumn()
  family_patient_id: number;

  @Column()
  family_id: number;

  @ManyToOne(() => Family, (family) => family.patientLinks, {
    onDelete: 'CASCADE',
  })
  @JoinColumn({ name: 'family_id' })
  family: Family;

  @Column()
  patient_id: number;

  @ManyToOne(() => Patient, (patient) => patient.familyLinks, {
    onDelete: 'CASCADE',
  })
  @JoinColumn({ name: 'patient_id' })
  patient: Patient;

  @Column({ length: 50, nullable: true })
  relationship: string;

  @CreateDateColumn()
  created_at: Date;
}
