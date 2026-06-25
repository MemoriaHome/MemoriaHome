import { IsString, IsNotEmpty, IsDateString, IsOptional } from 'class-validator';

export class CreateFallAlertDto {
  @IsString()
  @IsNotEmpty()
  deviceId: string;

  @IsString()
  @IsNotEmpty()
  patientId: string;

  @IsOptional()
  @IsString()
  recognizedPatientId?: string | null;

  @IsOptional()
  @IsString()
  recognizedPatientName?: string | null;

  @IsOptional()
  @IsString()
  subjectLabel?: string | null;

  @IsString()
  @IsNotEmpty()
  room: string;

  @IsString()
  @IsNotEmpty()
  eventType: string;

  @IsDateString()
  @IsNotEmpty()
  timestamp: string;

  @IsString()
  @IsNotEmpty()
  videoUrl: string;

  @IsString()
  @IsNotEmpty()
  incidentName: string;
}
