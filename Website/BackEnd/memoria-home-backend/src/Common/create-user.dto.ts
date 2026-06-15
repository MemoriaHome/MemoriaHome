import { IsEmail, IsNumber, IsString } from 'class-validator';
export class CreateUserDto {
        @IsEmail()
        email: string

        @IsString()
        pass: string

        @IsString()
        role: "patient" | "caregiver" | "admin" | "family"

        @IsNumber()
        domain_id: number

        created_at: Date
        last_login: Date

}
