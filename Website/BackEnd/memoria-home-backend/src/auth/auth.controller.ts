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

}
