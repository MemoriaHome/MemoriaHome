import { Entity, PrimaryGeneratedColumn, Column } from 'typeorm';

@Entity('caregivers')
export class Caregiver {

    @PrimaryGeneratedColumn()
    caregiver_id!: number;

    @Column()
    first_name!: string;

    @Column()
    last_name!: string;

    @Column()
    phone!: string;

    @Column()
    specialization!: string;

    @Column()
    license_number!: string;

    @Column()
    years_experience!: number;
}

