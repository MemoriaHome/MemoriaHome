import { Controller, Post, Body, Get, Param, ParseIntPipe } from '@nestjs/common';
import { AlertService } from './alert.service';
import { CreateFallAlertDto } from './dto/alert.fall.dto';

@Controller('alert')
export class AlertController {
  constructor(private readonly alertService: AlertService) {}

  @Post('fall')
  async handleFallAlert(@Body() dto: CreateFallAlertDto) {
    await this.alertService.handleFallAlert(dto);
    return { message: 'Alert received' };
  }

  // GET /alert/caregiver/:id — fetch all alerts for a caregiver's patients
  @Get('caregiver/:id')
  async getAlertsForCaregiver(@Param('id', ParseIntPipe) id: number) {
    return this.alertService.getAlertsForCaregiver(id);
  }
}