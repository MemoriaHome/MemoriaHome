import { Entity, PrimaryGeneratedColumn, Column, Timestamp } from 'typeorm';

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
    created_at: Date;

}