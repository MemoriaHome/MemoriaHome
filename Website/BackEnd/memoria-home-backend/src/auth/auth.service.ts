import { BadRequestException, Injectable, NotFoundException, UnauthorizedException } from '@nestjs/common';
import { CreateCaregiverDto } from '../caregiver/dto/create-caregiver.dto'
import { CreateUserDto } from '../Common/create-user.dto'
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Caregiver } from '../entities/caregiver.entity';
import { User } from '../entities/user.entity'
import { BreakGlassAccessLog } from '../entities/break_glass_access_log.entity';
import * as bcrypt from 'bcrypt';
import { CaregiverService } from '../caregiver/caregiver.service';
import { JwtService } from '@nestjs/jwt';
import { UserLoginDto } from '../Common/userlogin.dto'

@Injectable()
export class AuthService {

    constructor(
    @InjectRepository(Caregiver)
    private caregiverRepository: Repository<Caregiver>,

    @InjectRepository(User)
    private userRepository: Repository<User>,

    @InjectRepository(BreakGlassAccessLog)
    private breakGlassAccessLogRepository: Repository<BreakGlassAccessLog>,

    private jwtService: JwtService,
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
    years_experience: createCaregiverDto.years_experience,
    user: user,
  });
  return await this.caregiverRepository.save(caregiver);

    }

  async login(userlogindto: UserLoginDto){
      const submitted_email = userlogindto.email; //email submitted in form

      const target = await this.userRepository.findOne({
        where: {email:submitted_email}
      }) //find target by email
      if(!target)
        throw new NotFoundException('User Does Not Exist'); //keep code determanistic (if user is not found)
      
      const isMatch = await bcrypt.compare(userlogindto.pass, target.pass) //comapares submitted password hash with stored hash

      if(!isMatch){
        throw new UnauthorizedException('Invalid Credentials');
      }
      else if(target.role == 'caregiver'){
         const target_role = await this.caregiverRepository.findOne({relations: ['user'], where: {user: {user_id: target.user_id}}})
         
         if(!target_role){
          throw new NotFoundException('Not registered with a role')
         }

          const payload = {
            sub: target.user_id,
            email: target.email,
            role: 'caregiver',
            rid: target_role.caregiver_id
    };
          return {
            access_token: this.jwtService.sign(payload),
            user: {
              uid: target.user_id,              
              rid: target_role.caregiver_id,
              username: target.email,
              name: target_role.first_name,
              role: 'caregiver'
            }
          }
      }
      return target
    }

  async requestBreakGlassAccess(body: {
    caregiverId: number | string;
    patientId: number | string;
    streamType: string;
    password: string;
    reason?: string;
  }) {
    const streamType = this.normalizeBreakGlassStream(body.streamType);
    const caregiverId = String(body.caregiverId ?? '');
    const patientId = String(body.patientId ?? '');

    if (
      !Number.isFinite(Number(caregiverId)) ||
      !Number.isFinite(Number(patientId))
    ) {
      throw new BadRequestException('caregiverId and patientId are required');
    }

    if (streamType === 'depth') {
      throw new BadRequestException('Break-glass authentication is only required for RGB/IR');
    }

    const authenticated = await this.verifyBreakGlassCredentials(
      caregiverId,
      body.password,
    );
    if (!authenticated) {
      throw new UnauthorizedException('Break-glass authentication failed');
    }

    await this.logBreakGlassAccess(caregiverId, patientId, streamType, body.reason);

    const expiresInSeconds = 5 * 60;
    const token = this.jwtService.sign(
      {
        purpose: 'break-glass-stream',
        caregiverId,
        patientId,
        streamType,
        reason: body.reason ?? null,
      },
      { expiresIn: expiresInSeconds },
    );

    return {
      token,
      expiresInSeconds,
      streamType,
    };
  }

  async verifyBreakGlassAccess(body: {
    token: string;
    caregiverId: number | string;
    patientId: number | string;
    streamType: string;
  }) {
    try {
      const payload = this.jwtService.verify(body.token);
      const streamType = this.normalizeBreakGlassStream(body.streamType);

      const valid =
        payload?.purpose === 'break-glass-stream' &&
        payload?.caregiverId === String(body.caregiverId ?? '') &&
        payload?.patientId === String(body.patientId ?? '') &&
        payload?.streamType === streamType &&
        streamType !== 'depth';

      return { valid };
    } catch {
      return { valid: false };
    }
  }

  private async verifyBreakGlassCredentials(
    caregiverId: string,
    password: string,
  ): Promise<boolean> {
    const numericCaregiverId = Number(caregiverId);
    if (!Number.isFinite(numericCaregiverId) || !password) {
      return false;
    }

    const caregiver = await this.caregiverRepository.findOne({
      relations: ['user'],
      where: { caregiver_id: numericCaregiverId },
    });

    if (!caregiver?.user || caregiver.user.role !== 'caregiver') {
      return false;
    }

    return bcrypt.compare(password, caregiver.user.pass);
  }

  private async logBreakGlassAccess(
    caregiverId: string,
    patientId: string,
    streamType: string,
    reason?: string,
  ): Promise<void> {
    const log = this.breakGlassAccessLogRepository.create({
      caregiver_id: Number(caregiverId),
      patient_id: Number(patientId),
      reason: reason?.trim() || 'Emergency break-glass access',
      accessed_stream: streamType,
    });

    await this.breakGlassAccessLogRepository.save(log);
  }

  private normalizeBreakGlassStream(streamType: string): string {
    const normalized = String(streamType || '').toLowerCase();
    if (normalized === 'infrared') return 'ir';
    if (normalized === 'rgb' || normalized === 'ir' || normalized === 'depth') {
      return normalized;
    }
    throw new BadRequestException('Unsupported streamType');
  }
}
