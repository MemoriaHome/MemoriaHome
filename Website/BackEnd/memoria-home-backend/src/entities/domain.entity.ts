import {
  Column,
  CreateDateColumn,
  Entity,
  OneToMany,
  PrimaryGeneratedColumn,
  UpdateDateColumn,
} from 'typeorm';
import { User } from './user.entity';

export type DomainType = 'personal' | 'institute';

@Entity('domains')
export class Domain {
  @PrimaryGeneratedColumn()
  domain_id: number;

  @Column({ length: 20 })
  domain_type: DomainType;

  @Column({ length: 255 })
  name: string;

  @Column({ length: 255, nullable: true })
  contact_email: string;

  @Column({ length: 20, nullable: true })
  phone: string;

  @Column({ type: 'text', nullable: true })
  address: string;

  @CreateDateColumn()
  created_at: Date;

  @UpdateDateColumn()
  updated_at: Date;

  @OneToMany(() => User, (user) => user.domain)
  users: User[];
}
