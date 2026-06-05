import { IsEmail, IsString } from 'class-validator';
export class CreateUserDto {
        @IsEmail()
        email: string

        @IsString()
        pass: string

        @IsString()
        role: "patient" | "caregiver" | "admin" | "family"

        created_at: Date
        last_login: Date

}