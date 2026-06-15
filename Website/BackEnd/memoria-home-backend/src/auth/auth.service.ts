import { BadRequestException, ConflictException, Injectable, NotFoundException, UnauthorizedException } from '@nestjs/common';
import { CreateCaregiverDto } from '../caregiver/dto/create-caregiver.dto'
import { InjectRepository } from '@nestjs/typeorm';
import { DataSource, EntityManager, Repository } from 'typeorm';
import { Caregiver } from '../entities/caregiver.entity';
import { User } from '../entities/user.entity'
import { BreakGlassAccessLog } from '../entities/break_glass_access_log.entity';
import * as bcrypt from 'bcrypt';
import { JwtService } from '@nestjs/jwt';
import { UserLoginDto } from '../Common/userlogin.dto'
import { EnrollDomainDto } from './dto/enroll-domain.dto';
import { Domain, DomainType } from '../entities/domain.entity';
import { Admin } from '../entities/admin.entity';
import { Family } from '../entities/family.entity';
import { Patient } from '../entities/patient.entity';
import { FamilyPatient } from '../entities/family_patient.entity';

@Injectable()
export class AuthService {

    constructor(
    @InjectRepository(Caregiver)
    private caregiverRepository: Repository<Caregiver>,

    @InjectRepository(User)
    private userRepository: Repository<User>,

    @InjectRepository(BreakGlassAccessLog)
    private breakGlassAccessLogRepository: Repository<BreakGlassAccessLog>,

    private dataSource: DataSource,

    private jwtService: JwtService,
  ) {}

  async enrollDomain(dto: EnrollDomainDto) {
    const existing = await this.userRepository.findOne({
      where: { email: dto.user.email },
    });
    if (existing) {
      throw new ConflictException('Email is already registered');
    }

    if (dto.domain_type === 'personal' && !dto.patient) {
      throw new BadRequestException('Patient details are required for personal domains');
    }

    return this.dataSource.transaction(async (manager) => {
      const domain = await manager.save(
        manager.create(Domain, {
          domain_type: dto.domain_type,
          name: dto.domain.name,
          contact_email: dto.domain.contact_email,
          phone: dto.domain.phone,
          address: dto.domain.address,
        }),
      );

      const role = dto.domain_type === 'institute' ? 'admin' : 'family';
      const user = await this.createUser(
        manager,
        dto.user.email,
        dto.user.pass,
        role,
        domain.domain_id,
      );

      if (dto.domain_type === 'institute') {
        const admin = await manager.save(
          manager.create(Admin, {
            user_id: user.user_id,
            first_name: dto.user.first_name,
            last_name: dto.user.last_name,
            phone: dto.user.phone,
            job_title: dto.user.job_title ?? 'Administrator',
          }),
        );

        return this.buildAuthResponse(user, domain, {
          admin_id: admin.admin_id,
          name: admin.first_name,
        });
      }

      const family = await manager.save(
        manager.create(Family, {
          user_id: user.user_id,
          first_name: dto.user.first_name,
          last_name: dto.user.last_name,
          phone: dto.user.phone,
        }),
      );

      const patient = await this.createPatientForDomain(
        manager,
        dto.patient!,
        domain.domain_id,
      );

      await manager.save(
        manager.create(FamilyPatient, {
          family_id: family.family_id,
          patient_id: patient.patient_id,
          relationship: dto.relationship,
        }),
      );

      return this.buildAuthResponse(user, domain, {
        family_id: family.family_id,
        name: family.first_name,
      });
    });
  }

    async signup(createCaregiverDto: CreateCaregiverDto) {
    if (!createCaregiverDto.domain_id) {
      throw new BadRequestException('domain_id is required for caregiver signup');
    }
    const salt = await bcrypt.genSalt(); //salt for hashing
    const plain_pass = createCaregiverDto.pass; //plain password
    const hash_pass = await bcrypt.hash(plain_pass, salt);
    
    const user = this.userRepository.create({
     email: createCaregiverDto.email,
     pass: hash_pass,
     role: createCaregiverDto.role,
     domain_id: createCaregiverDto.domain_id,
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
        where: {email:submitted_email},
        relations: ['domain'],
      }) //find target by email
      if(!target)
        throw new NotFoundException('User Does Not Exist'); //keep code determanistic (if user is not found)
      
      const isMatch = await bcrypt.compare(userlogindto.pass, target.pass) //comapares submitted password hash with stored hash

      if(!isMatch){
        throw new UnauthorizedException('Invalid Credentials');
      }
      else {
        return this.getLoginResponse(target);
      }
    }

  private async getLoginResponse(user: User) {
    const domain = user.domain;
    if (!domain) {
      throw new NotFoundException('User is not associated with a domain');
    }

    if (user.role === 'caregiver') {
      const caregiver = await this.caregiverRepository.findOne({
        where: { user_id: user.user_id },
      });
      if (!caregiver) throw new NotFoundException('Not registered with a caregiver profile');
      return this.buildAuthResponse(user, domain, {
        caregiver_id: caregiver.caregiver_id,
        rid: caregiver.caregiver_id,
        name: caregiver.first_name,
      });
    }

    if (user.role === 'admin') {
      const admin = await this.dataSource.getRepository(Admin).findOne({
        where: { user_id: user.user_id },
      });
      if (!admin) throw new NotFoundException('Not registered with an admin profile');
      return this.buildAuthResponse(user, domain, {
        admin_id: admin.admin_id,
        name: admin.first_name,
      });
    }

    if (user.role === 'family') {
      const family = await this.dataSource.getRepository(Family).findOne({
        where: { user_id: user.user_id },
      });
      if (!family) throw new NotFoundException('Not registered with a family profile');
      return this.buildAuthResponse(user, domain, {
        family_id: family.family_id,
        name: family.first_name,
      });
    }

    return this.buildAuthResponse(user, domain, { name: user.email });
  }

  private buildAuthResponse(
    user: User,
    domain: Domain,
    profile: {
      name: string;
      admin_id?: number;
      family_id?: number;
      caregiver_id?: number;
      rid?: number;
    },
  ) {
    const payload = {
      sub: user.user_id,
      email: user.email,
      role: user.role,
      domain_id: user.domain_id,
      domain_type: domain.domain_type,
      admin_id: profile.admin_id,
      family_id: profile.family_id,
      caregiver_id: profile.caregiver_id,
      rid: profile.rid,
    };

    return {
      access_token: this.jwtService.sign(payload),
      user: {
        uid: user.user_id,
        rid: profile.rid,
        admin_id: profile.admin_id,
        family_id: profile.family_id,
        caregiver_id: profile.caregiver_id,
        username: user.email,
        name: profile.name,
        role: user.role,
        domain_id: user.domain_id,
        domain_type: domain.domain_type,
        domain_name: domain.name,
      },
    };
  }

  private async createUser(
    manager: EntityManager,
    email: string,
    password: string,
    role: string,
    domainId: number,
  ) {
    const salt = await bcrypt.genSalt();
    const hash = await bcrypt.hash(password, salt);

    return manager.save(
      manager.create(User, {
        email,
        pass: hash,
        role,
        domain_id: domainId,
      }),
    );
  }

  private async createPatientForDomain(
    manager: EntityManager,
    patientDto: {
      first_name: string;
      last_name: string;
      date_of_birth: string;
      gender: string;
      emergency_contact?: string;
      emergency_contact_name?: string;
      address?: string;
      dementia_stage?: string;
    },
    domainId: number,
  ) {
    const patientUser = await manager.save(
      manager.create(User, {
        email: `patient_${patientDto.first_name.toLowerCase()}_${patientDto.last_name.toLowerCase()}_${Date.now()}@internal.memoriahome`,
        pass: 'N/A',
        role: 'patient',
        domain_id: domainId,
      }),
    );

    return manager.save(
      manager.create(Patient, {
        user_id: patientUser.user_id,
        first_name: patientDto.first_name,
        last_name: patientDto.last_name,
        date_of_birth: patientDto.date_of_birth,
        gender: patientDto.gender,
        emergency_contact: patientDto.emergency_contact,
        emergency_contact_name: patientDto.emergency_contact_name,
        address: patientDto.address,
        dementia_stage: patientDto.dementia_stage,
      }),
    );
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
