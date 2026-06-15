import {
  Column,
  CreateDateColumn,
  Entity,
  JoinColumn,
  OneToMany,
  OneToOne,
  PrimaryGeneratedColumn,
  UpdateDateColumn,
} from 'typeorm';
import { User } from './user.entity';
import { FamilyPatient } from './family_patient.entity';

@Entity('families')
export class Family {
  @PrimaryGeneratedColumn()
  family_id: number;

  @Column({ unique: true })
  user_id: number;

  @OneToOne(() => User, (user) => user.family, { onDelete: 'CASCADE' })
  @JoinColumn({ name: 'user_id' })
  user: User;

  @Column({ length: 100 })
  first_name: string;

  @Column({ length: 100 })
  last_name: string;

  @Column({ length: 20, nullable: true })
  phone: string;

  @CreateDateColumn()
  created_at: Date;

  @UpdateDateColumn()
  updated_at: Date;

  @OneToMany(() => FamilyPatient, (familyPatient) => familyPatient.family)
  patientLinks: FamilyPatient[];
}
