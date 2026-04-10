import { Entity, PrimaryGeneratedColumn, Column, Timestamp, OneToOne } from 'typeorm';
import { Caregiver } from './caregiver.entity';

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
    
    @OneToOne(() => Caregiver, (caregiver) => caregiver.user)
    caregiver: Caregiver;

    @Column()
    created_at: Date;

}