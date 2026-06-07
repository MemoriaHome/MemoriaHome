import { Controller,Post, Body } from '@nestjs/common';
import { AuthService } from './auth.service';
import { CreateCaregiverDto } from '../caregiver/dto/create-caregiver.dto';
import { CreateUserDto } from '../Common/create-user.dto';
import { UserLoginDto } from '../Common/userlogin.dto'

@Controller('auth')
export class AuthController {
  constructor(private readonly authService: AuthService) {}

@Post('signup') //http://example.com/auth/signup
signup(@Body() createCaregiverDto: CreateCaregiverDto) {
  return this.authService.signup(createCaregiverDto);
  }

@Post('login')
login(@Body() userlogindto: UserLoginDto){
  console.log('IN CONTROLLER');
  return this.authService.login(userlogindto);
}

@Post('break-glass')
requestBreakGlassAccess(@Body() body: {
  caregiverId: number | string;
  patientId: number | string;
  streamType: string;
  password: string;
  reason?: string;
}) {
  return this.authService.requestBreakGlassAccess(body);
}

@Post('break-glass/verify')
verifyBreakGlassAccess(@Body() body: {
  token: string;
  caregiverId: number | string;
  patientId: number | string;
  streamType: string;
}) {
  return this.authService.verifyBreakGlassAccess(body);
}

}
