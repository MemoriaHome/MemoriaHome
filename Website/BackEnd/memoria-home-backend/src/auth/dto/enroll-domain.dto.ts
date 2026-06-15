import {
  IsEmail,
  IsIn,
  IsNotEmpty,
  IsOptional,
  IsString,
  MaxLength,
  ValidateIf,
  ValidateNested,
} from 'class-validator';
import { Type } from 'class-transformer';
import { OnboardPatientDto } from '../../patient/dto/onboard-patient.dto';

class EnrollDomainDetailsDto {
  @IsString()
  @IsNotEmpty()
  @MaxLength(255)
  name: string;

  @IsEmail()
  contact_email: string;

  @IsString()
  @IsNotEmpty()
  @MaxLength(20)
  phone: string;

  @IsString()
  @IsNotEmpty()
  address: string;
}

class EnrollUserDto {
  @IsString()
  @IsNotEmpty()
  @MaxLength(100)
  first_name: string;

  @IsString()
  @IsNotEmpty()
  @MaxLength(100)
  last_name: string;

  @IsString()
  @IsNotEmpty()
  @MaxLength(20)
  phone: string;

  @IsOptional()
  @IsString()
  @MaxLength(100)
  job_title?: string;

  @IsEmail()
  email: string;

  @IsString()
  @IsNotEmpty()
  pass: string;
}

export class EnrollDomainDto {
  @IsIn(['personal', 'institute'])
  domain_type: 'personal' | 'institute';

  @ValidateNested()
  @Type(() => EnrollDomainDetailsDto)
  domain: EnrollDomainDetailsDto;

  @ValidateNested()
  @Type(() => EnrollUserDto)
  user: EnrollUserDto;

  @ValidateIf((dto: EnrollDomainDto) => dto.domain_type === 'personal')
  @ValidateNested()
  @Type(() => OnboardPatientDto)
  patient?: OnboardPatientDto;

  @ValidateIf((dto: EnrollDomainDto) => dto.domain_type === 'personal')
  @IsString()
  @IsNotEmpty()
  @MaxLength(50)
  relationship?: string;
}
