import { Entity, PrimaryGeneratedColumn, Column, OneToMany, OneToOne, JoinColumn} from 'typeorm';
import { PatientCaregiver } from '../entities/patientToCaregiver.entity';
import { User } from './user.entity'
@Entity('caregivers') //table name in the database
export class Caregiver{

    @PrimaryGeneratedColumn()
    caregiver_id: number;

    @OneToOne(() => User, {onDelete: 'CASCADE'})
    @JoinColumn({ name: 'user_id' })
    user: User;

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
