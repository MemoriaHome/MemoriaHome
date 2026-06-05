import { IsString, IsNumber, IsEmail, Min, Max } from 'class-validator';
import { CreateUserDto } from "../../Common/create-user.dto";

export class CreateCaregiverDto extends CreateUserDto {

     @IsString()
     first_name: string;

     @IsString()
     last_name: string;

     @IsString()
     phone: string;

     @IsString()
     specialization: string;

     @IsString()
     license_number: string;

     @IsNumber()
     @Min(0)
     @Max(255)
     years_experience: number;

}
