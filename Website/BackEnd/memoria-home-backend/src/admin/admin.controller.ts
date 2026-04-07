import { Body, Controller, Post, HttpCode, HttpStatus } from '@nestjs/common';
import { AdminService } from './admin.service';
import { OnboardPatientDto } from '../patient/dto/onboard-patient.dto';

@Controller('administrator')          // matches /administrator/onboard in admin.js
export class AdminController {

  constructor(private readonly adminService: AdminService) {}

  @Post('onboard')
  @HttpCode(HttpStatus.CREATED)
  async onboardPatient(@Body() dto: OnboardPatientDto) {
    return this.adminService.onboardPatient(dto);
  }

}