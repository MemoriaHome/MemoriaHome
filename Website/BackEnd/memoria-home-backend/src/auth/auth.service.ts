import { Injectable, NotFoundException, UnauthorizedException } from '@nestjs/common';
import { CreateCaregiverDto } from '../caregiver/dto/create-caregiver.dto'
import { CreateUserDto } from '../Common/create-user.dto'
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Caregiver } from '../entities/caregiver.entity';
import { User } from '../entities/user.entity'
import * as bcrypt from 'bcrypt';


@Injectable()
export class AuthService {

    constructor(
    @InjectRepository(Caregiver)
    private caregiverRepository: Repository<Caregiver>,

    @InjectRepository(User)
    private userRepository: Repository<User>
  ) {}

    async signup(createCaregiverDto: CreateCaregiverDto) {  
    const salt = await bcrypt.genSalt(); //salt for hashing
    const plain_pass = createCaregiverDto.pass; //plain password
    const hash_pass = await bcrypt.hash(plain_pass, salt);
    
    const user = this.userRepository.create({
     email: createCaregiverDto.email,
     pass: hash_pass,
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

  async login(createUserDto: CreateUserDto){
      const submitted_email = createUserDto.email; //email submitted in form

      const target = await this.userRepository.findOne({
        where: {email:submitted_email}
      }) //find target by email

      if(!target)
        throw new NotFoundException('User Does Not Exist'); //keep code determanistic (if user is not found)
      
      const isMatch = await bcrypt.compare(createUserDto.pass, target.pass) //comapares submitted password hash with stored hash

      console.log(target.pass)
      console.log(createUserDto.pass)

      if(!isMatch)
        throw new UnauthorizedException('Invalid Credentials');

      return target
    }
  }
