import { Injectable, NotFoundException, UnauthorizedException } from '@nestjs/common';
import { CreateCaregiverDto } from '../caregiver/dto/create-caregiver.dto';
import { CreateUserDto } from '../Common/create-user.dto';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Caregiver } from '../entities/caregiver.entity';
import { User } from '../entities/user.entity';
import * as bcrypt from 'bcrypt';
import { JwtService } from '@nestjs/jwt';

@Injectable()
export class AuthService {

  constructor(
    @InjectRepository(Caregiver)
    private caregiverRepository: Repository<Caregiver>,
    @InjectRepository(User)
    private userRepository: Repository<User>,
    private jwtService: JwtService,
  ) {}

  async signup(createCaregiverDto: CreateCaregiverDto) {
    const salt = await bcrypt.genSalt();
    const hash_pass = await bcrypt.hash((createCaregiverDto as any).pass, salt);

    const user = this.userRepository.create({
      email: createCaregiverDto.email,
      pass: hash_pass,
      role: createCaregiverDto.role,
      created_at: new Date(),
    });

    await this.userRepository.save(user);

    const caregiver = this.caregiverRepository.create({
      first_name: createCaregiverDto.first_name,
      last_name: createCaregiverDto.last_name,
      phone: createCaregiverDto.phone,
      specialization: createCaregiverDto.specialization,
      license_number: createCaregiverDto.license_number,
      years_experience: createCaregiverDto.years_experience,
    });

    return await this.caregiverRepository.save(caregiver);
  }

  async login(createUserDto: CreateUserDto) {
    const target = await this.userRepository.findOne({
      where: { email: createUserDto.email },
    });

    if (!target || !(await bcrypt.compare(createUserDto.pass, target.pass)))
  throw new UnauthorizedException('Invalid credentials');

    const isMatch = await bcrypt.compare(createUserDto.pass, target.pass);

    if (!isMatch)
      throw new UnauthorizedException('Invalid Credentials');

    const payload = {
      sub: target.user_id,
      email: target.email,
      role: target.role,
    };

    return {
      access_token: this.jwtService.sign(payload),
    };
  }
}