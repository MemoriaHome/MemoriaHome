import { PartialType } from '@nestjs/mapped-types';
import { CreateCaregiverDto } from './create-caregiver.dto';

export class UpdateCaregiverDto extends PartialType(CreateCaregiverDto) {}
