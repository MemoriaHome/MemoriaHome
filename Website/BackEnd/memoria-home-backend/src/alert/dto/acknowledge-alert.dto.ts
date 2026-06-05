import { IsInt, IsNotEmpty } from 'class-validator';
import { Type } from 'class-transformer';

export class AcknowledgeAlertDto {
  @Type(() => Number)
  @IsInt()
  @IsNotEmpty()
  caregiverId: number;
}