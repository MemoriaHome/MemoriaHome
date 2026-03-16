import { Injectable } from '@nestjs/common';
import { CreateCaregiverDto } from '../caregiver/dto/create-caregiver.dto'
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Caregiver } from '../entities/caregiver.entity';
import { User } from '../entities/user.entity'

@Injectable()
export class AuthService {

    constructor(
    @InjectRepository(Caregiver)
    private caregiverRepository: Repository<Caregiver>,

    @InjectRepository(User)
    private userRepository: Repository<User>
  ) {}

    async signup(createCaregiverDto: CreateCaregiverDto) {
    const user = this.userRepository.create({
     email: createCaregiverDto.email,
     pass: createCaregiverDto.pass,
     role: createCaregiverDto.role
  });

  await this.userRepository.save(user);


  const caregiver = this.caregiverRepository.create({
    first_name: createCaregiverDto.first_name,
    last_name: createCaregiverDto.last_name,
    phone: createCaregiverDto.phone,
    specialization: createCaregiverDto.specialization,
    license_number: createCaregiverDto.license_number,
    years_experience: createCaregiverDto.years_experience
  });
  return await this.caregiverRepository.save(caregiver);

    }
  }
