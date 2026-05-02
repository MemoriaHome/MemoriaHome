import { Controller, Post, Body } from '@nestjs/common';
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
}