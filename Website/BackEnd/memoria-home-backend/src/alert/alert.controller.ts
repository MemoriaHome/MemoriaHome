import { Controller, Post, Patch, Body, Get, Param, ParseIntPipe } from '@nestjs/common';
import { AlertService } from './alert.service';
import { CreateFallAlertDto } from './dto/alert.fall.dto';
import { AcknowledgeAlertDto } from './dto/acknowledge-alert.dto';

@Controller('alert')
export class AlertController {
  constructor(private readonly alertService: AlertService) {}

  // POST /alert/fall — receives alert from Python monitoring app
  @Post('fall')
  async handleFallAlert(@Body() dto: CreateFallAlertDto) {
    await this.alertService.handleFallAlert(dto);
    return { message: 'Alert received' };
  }

  // PATCH /alert/:id/acknowledge — caregiver acknowledges an alert
  @Patch(':id/acknowledge')
  async acknowledgeAlert(
    @Param('id', ParseIntPipe) id: number,
    @Body() dto: AcknowledgeAlertDto,
  ) {
    return this.alertService.acknowledgeAlert(id, dto.caregiverId);
  }

  // GET /alert/caregiver/:id — seeds frontend with past alerts on page load
  @Get('caregiver/:id')
  async getAlertsForCaregiver(@Param('id', ParseIntPipe) id: number) {
    return this.alertService.getAlertsForCaregiver(id);
  }
}