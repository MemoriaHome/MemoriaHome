import { Entity, PrimaryGeneratedColumn, Column, OneToMany} from 'typeorm';
import { PatientCaregiver } from '../entities/patientToCaregiver.entity';

@Entity('caregivers') //table name in the database
export class Caregiver {

    @PrimaryGeneratedColumn()
    caregiver_id: number;

    @Column()
    first_name: string;

    @Column()
    last_name: string;

    @Column()
    phone: string;

    @Column()
    specialization: string;

    @Column()
    license_number: string;

    @Column()
    years_experience: number;

    @OneToMany(() => PatientCaregiver, (pc) => pc.caregiver)
    assignments: PatientCaregiver[];

}
