import { Entity, PrimaryGeneratedColumn, Column } from 'typeorm';

@Entity('patients')
export class Patient {

    @PrimaryGeneratedColumn()
    patient_id!: number;

    @Column({ nullable: true })
    user_id!: number;

    @Column()
    first_name!: string;

    @Column()
    last_name!: string;

    @Column({ nullable: true })
    date_of_birth!: Date;

    @Column({ nullable: true })
    gender!: string;

    @Column({ nullable: true })
    emergency_contact!: string;

    @Column({ nullable: true })
    emergency_contact_name!: string;

    @Column({ nullable: true })
    address!: string;

    @Column({ type: 'jsonb', nullable: true })
    medical_history!: object;

    @Column({ nullable: true })
    dementia_stage!: string;

    @Column({ default: () => 'CURRENT_TIMESTAMP' })
    created_at!: Date;

    @Column({ default: () => 'CURRENT_TIMESTAMP' })
    updated_at!: Date;
}