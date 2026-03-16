import { CreateUserDto } from "src/Common/create-user.dto";

export class CreateCaregiverDto extends CreateUserDto {

     first_name: string
     last_name: string
     phone: string
     specialization: string
     license_number: string
     years_experience: number

}
