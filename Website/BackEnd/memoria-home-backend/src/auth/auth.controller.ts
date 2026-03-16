import { Controller,Post, Body } from '@nestjs/common';
import { AuthService } from './auth.service';
import { CreateCaregiverDto } from '../caregiver/dto/create-caregiver.dto';

@Controller('auth')
export class AuthController {
  constructor(private readonly authService: AuthService) {}

@Post('signup')
signup(@Body() createCaregiverDto: CreateCaregiverDto) {
  return this.authService.signup(createCaregiverDto);
}

}
