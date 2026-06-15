import { Body, Controller, Post, HttpCode, HttpStatus, Get, Param, Delete, ParseIntPipe, Req, UseGuards} from '@nestjs/common';
import { AdminService } from './admin.service';
import { OnboardPatientDto } from '../patient/dto/onboard-patient.dto';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';
import type { AuthenticatedRequest } from '../auth/jwt-auth.guard';
import { CreateDomainCaregiverDto } from './dto/create-domain-caregiver.dto';
import { CreateDomainAdminDto } from './dto/create-domain-admin.dto';

@Controller('administrator')
@UseGuards(JwtAuthGuard)
export class AdminController {

  constructor(private readonly adminService: AdminService) {}

//==========Patients==========

  @Post('onboard')
  @HttpCode(HttpStatus.CREATED)
  async onboardPatient(@Body() dto: OnboardPatientDto, @Req() req: AuthenticatedRequest) {
    return this.adminService.onboardPatient(dto, req.user);
  }

  @Delete('patient/:id')
  @HttpCode(HttpStatus.NO_CONTENT)
  async deletePatient(@Param('id', ParseIntPipe) id: number, @Req() req: AuthenticatedRequest) {
      return this.adminService.deletePatient(id, req.user);
  }

  @Get('patients')
  getAllPatients(@Req() req: AuthenticatedRequest) {
    return this.adminService.getAllPatients(req.user);
  }

//==========Caregivers==========
  
  @Post('assign-caregiver')
  assignCaregiver(
    @Body() body: { patient_id: number; caregiver_id: number },
    @Req() req: AuthenticatedRequest,
) {
  return this.adminService.assignCaregiver(
    body.patient_id,
    body.caregiver_id,
    req.user,
  );
 }

  @Get('patient/:id/caregivers')
  getCaregivers(@Param('id', ParseIntPipe) id: number, @Req() req: AuthenticatedRequest) {
    return this.adminService.getCaregiversForPatient(id, req.user);
}

  @Delete('patient/:patientId/caregiver/:caregiverId')
  unassignCaregiver(
    @Param('patientId', ParseIntPipe) patientId: number,
    @Param('caregiverId', ParseIntPipe) caregiverId: number,
    @Req() req: AuthenticatedRequest,
  ) {
    return this.adminService.unassignCaregiver(patientId, caregiverId, req.user);
  }

  @Get('caregivers')
  getAllCaregivers(@Req() req: AuthenticatedRequest) {
    return this.adminService.getAllCaregivers(req.user);
  }

  @Post('caregivers')
  @HttpCode(HttpStatus.CREATED)
  createCaregiver(@Body() dto: CreateDomainCaregiverDto, @Req() req: AuthenticatedRequest) {
    return this.adminService.createCaregiver(dto, req.user);
  }

  @Get('admins')
  getAllAdmins(@Req() req: AuthenticatedRequest) {
    return this.adminService.getAllAdmins(req.user);
  }

  @Post('admins')
  @HttpCode(HttpStatus.CREATED)
  createAdmin(@Body() dto: CreateDomainAdminDto, @Req() req: AuthenticatedRequest) {
    return this.adminService.createAdmin(dto, req.user);
  }

//==========Security==========

  @Get('break-glass-logs')
  getBreakGlassAccessLogs(@Req() req: AuthenticatedRequest) {
    return this.adminService.getBreakGlassAccessLogs(req.user);
  }

}
