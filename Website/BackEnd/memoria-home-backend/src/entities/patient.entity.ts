import { Entity, PrimaryGeneratedColumn, Column, ManyToOne, JoinColumn, CreateDateColumn, UpdateDateColumn, OneToMany } from 'typeorm';
import { User } from './user.entity';
import { PatientCaregiver } from '../entities/patientToCaregiver.entity';

@Entity('patients')
export class Patient {

  @PrimaryGeneratedColumn()
  patient_id: number;

  @Column({ unique: true })
  user_id: number;

  @ManyToOne(() => User, { onDelete: 'CASCADE' })
  @JoinColumn({ name: 'user_id' })
  user: User;

  @Column({ length: 100 })
  first_name: string;

  @Column({ length: 100 })
  last_name: string;

  @Column({ type: 'date', nullable: true })
  date_of_birth: string;

  @Column({ length: 20, nullable: true })
  gender: string;

  @Column({ length: 20, nullable: true })
  emergency_contact: string;

  @Column({ length: 100, nullable: true })
  emergency_contact_name: string;

  @Column({ type: 'text', nullable: true })
  address: string;

  @Column({ type: 'jsonb', nullable: true })
  medical_history: object;

  @Column({ length: 50, nullable: true })
  dementia_stage: string;

  @CreateDateColumn()
  created_at: Date;

  @UpdateDateColumn()
  updated_at: Date;

  @OneToMany(() => PatientCaregiver, (pc) => pc.patient)
  assignments: PatientCaregiver[];

}