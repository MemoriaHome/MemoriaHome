import {
    Column,
    CreateDateColumn,
    Entity,
    JoinColumn,
    ManyToOne,
    OneToOne,
    PrimaryGeneratedColumn,
} from 'typeorm';
import { Caregiver } from './caregiver.entity';
import { Admin } from './admin.entity';
import { Domain } from './domain.entity';
import { Family } from './family.entity';

@Entity('users') //table name in the database
export class User {

    @PrimaryGeneratedColumn()
    user_id: number;

    @Column()
    email: string;

    @Column()
    pass: string;

    @Column()
    role: string;

    @Column()
    domain_id: number;

    @ManyToOne(() => Domain, (domain) => domain.users, { onDelete: 'RESTRICT' })
    @JoinColumn({ name: 'domain_id' })
    domain: Domain;
    
    @OneToOne(() => Caregiver, (caregiver) => caregiver.user)
    caregiver: Caregiver;

    @OneToOne(() => Admin, (admin) => admin.user)
    admin: Admin;

    @OneToOne(() => Family, (family) => family.user)
    family: Family;

    @CreateDateColumn()
    created_at: Date;

    @Column({ type: 'timestamp', nullable: true })
    last_login: Date;

}
