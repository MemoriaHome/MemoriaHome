import { Body, Controller, Post, HttpCode, HttpStatus, Get, Param, Delete} from '@nestjs/common';
import { AdminService } from './admin.service';
import { OnboardPatientDto } from '../patient/dto/onboard-patient.dto';

@Controller('administrator')
export class AdminController {

  constructor(private readonly adminService: AdminService) {}

//==========Patients==========

  @Post('onboard')
  @HttpCode(HttpStatus.CREATED)
  async onboardPatient(@Body() dto: OnboardPatientDto) {
    return this.adminService.onboardPatient(dto);
  }

  @Delete('patient/:id')
  @HttpCode(HttpStatus.NO_CONTENT)
  async deletePatient(@Param('id') id: number) {
      return this.adminService.deletePatient(id);
  }

  @Get('patients')
  getAllPatients() {
    return this.adminService.getAllPatients();
  }

//==========Caregivers==========
  
  @Post('assign-caregiver')
  assignCaregiver(
    @Body() body: { patient_id: number; caregiver_id: number },
) {
  return this.adminService.assignCaregiver(
    body.patient_id,
    body.caregiver_id,
  );
 }

  @Get('patient/:id/caregivers')
  getCaregivers(@Param('id') id: number) {
    return this.adminService.getCaregiversForPatient(id);
}

  @Delete('patient/:patientId/caregiver/:caregiverId')
  unassignCaregiver(
    @Param('patientId') patientId: number,
    @Param('caregiverId') caregiverId: number,
  ) {
    return this.adminService.unassignCaregiver(patientId, caregiverId);
  }

  @Get('caregivers')
  getAllCaregivers() {
    return this.adminService.getAllCaregivers();
  }

}