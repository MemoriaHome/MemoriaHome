import { Injectable, NotFoundException, UnauthorizedException } from '@nestjs/common';
import { CreateCaregiverDto } from '../caregiver/dto/create-caregiver.dto';
import { CreateUserDto } from '../Common/create-user.dto';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Caregiver } from '../entities/caregiver.entity';
import { User } from '../entities/user.entity';
import * as bcrypt from 'bcrypt';
import { JwtService } from '@nestjs/jwt';
import { EncryptionService } from '../encryption.service';

@Injectable()
export class AuthService {

  constructor(
    @InjectRepository(Caregiver)
    private caregiverRepository: Repository<Caregiver>,
    @InjectRepository(User)
    private userRepository: Repository<User>,
    private jwtService: JwtService,
    private encryptionService: EncryptionService,
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
      first_name: this.encryptionService.encrypt(createCaregiverDto.first_name),
      last_name: this.encryptionService.encrypt(createCaregiverDto.last_name),
      phone: this.encryptionService.encrypt(createCaregiverDto.phone),
      specialization: this.encryptionService.encrypt(createCaregiverDto.specialization),
      license_number: this.encryptionService.encrypt(createCaregiverDto.license_number),
      years_experience: createCaregiverDto.years_experience,
    });

    const saved = await this.caregiverRepository.save(caregiver);

    return {
      ...saved,
      first_name: this.encryptionService.decrypt(saved.first_name),
      last_name: this.encryptionService.decrypt(saved.last_name),
      phone: this.encryptionService.decrypt(saved.phone),
      specialization: this.encryptionService.decrypt(saved.specialization),
      license_number: this.encryptionService.decrypt(saved.license_number),
    };
  }

  async login(createUserDto: CreateUserDto) {
    const target = await this.userRepository.findOne({
      where: { email: createUserDto.email },
    });

    if (!target)
      throw new NotFoundException('User Does Not Exist');

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