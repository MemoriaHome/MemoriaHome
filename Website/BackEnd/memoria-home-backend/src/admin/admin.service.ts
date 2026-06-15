import {
  BadRequestException,
  ForbiddenException,
  Injectable,
  NotFoundException,
} from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { DataSource, EntityManager, Repository } from 'typeorm';
import * as bcrypt from 'bcrypt';
import { Patient } from '../entities/patient.entity';
import { User } from '../entities/user.entity';
import { Caregiver } from '../entities/caregiver.entity';
import { PatientCaregiver } from '../entities/patientToCaregiver.entity';
import { OnboardPatientDto } from '../patient/dto/onboard-patient.dto';
import { BreakGlassAccessLog } from '../entities/break_glass_access_log.entity';
import { FamilyPatient } from '../entities/family_patient.entity';
import { Admin } from '../entities/admin.entity';
import { Family } from '../entities/family.entity';
import { CreateDomainAdminDto } from './dto/create-domain-admin.dto';
import { CreateDomainCaregiverDto } from './dto/create-domain-caregiver.dto';
import { AuthenticatedUser } from '../auth/jwt-auth.guard';

@Injectable()
export class AdminService {
  constructor(
    @InjectRepository(Patient)
    private patientRepository: Repository<Patient>,

    @InjectRepository(User)
    private userRepository: Repository<User>,

    @InjectRepository(PatientCaregiver)
    private patientCaregiverRepo: Repository<PatientCaregiver>,

    @InjectRepository(Caregiver)
    private caregiverRepo: Repository<Caregiver>,

    @InjectRepository(Admin)
    private adminRepo: Repository<Admin>,

    @InjectRepository(Family)
    private familyRepo: Repository<Family>,

    @InjectRepository(BreakGlassAccessLog)
    private breakGlassAccessLogRepo: Repository<BreakGlassAccessLog>,

    private dataSource: DataSource,
  ) {}

  //==============PATIENTS==============

  async getAllPatients(user: AuthenticatedUser): Promise<Patient[]> {
    this.assertDashboardUser(user);

    return this.patientRepository
      .createQueryBuilder('patient')
      .innerJoin('patient.user', 'user')
      .where('user.domain_id = :domainId', { domainId: user.domain_id })
      .orderBy('patient.patient_id', 'ASC')
      .getMany();
  }

  async onboardPatient(
    dto: OnboardPatientDto,
    user: AuthenticatedUser,
  ): Promise<Patient> {
    this.assertDashboardUser(user);

    return this.dataSource.transaction(async (manager) => {
      const patient = await this.createPatientForDomain(
        manager,
        dto,
        user.domain_id,
      );

      if (user.role === 'family') {
        const familyId = await this.resolveFamilyId(user);
        await manager.save(
          manager.create(FamilyPatient, {
            family_id: familyId,
            patient_id: patient.patient_id,
            relationship: dto.relationship ?? 'family',
          }),
        );
      }

      return patient;
    });
  }

  async deletePatient(
    patientId: number,
    user: AuthenticatedUser,
  ): Promise<void> {
    this.assertDashboardUser(user);

    const patient = await this.getPatientInDomain(patientId, user.domain_id);
    const userId = patient.user_id;

    await this.patientRepository.remove(patient);
    await this.userRepository.delete({ user_id: userId });
  }

  //==============CAREGIVERS==============

  async getAllCaregivers(user: AuthenticatedUser): Promise<Caregiver[]> {
    this.assertDashboardUser(user);

    return this.caregiverRepo
      .createQueryBuilder('caregiver')
      .innerJoin('caregiver.user', 'user')
      .where('user.domain_id = :domainId', { domainId: user.domain_id })
      .orderBy('caregiver.caregiver_id', 'ASC')
      .getMany();
  }

  async createCaregiver(
    dto: CreateDomainCaregiverDto,
    user: AuthenticatedUser,
  ): Promise<Caregiver> {
    this.assertDashboardUser(user);

    return this.dataSource.transaction(async (manager) => {
      const savedUser = await this.createUser(
        manager,
        dto.email,
        dto.pass,
        'caregiver',
        user.domain_id,
      );

      return manager.save(
        manager.create(Caregiver, {
          user_id: savedUser.user_id,
          first_name: dto.first_name,
          last_name: dto.last_name,
          phone: dto.phone,
          specialization: dto.specialization,
          license_number: dto.license_number ?? '',
          years_experience: dto.years_experience,
        }),
      );
    });
  }

  async assignCaregiver(
    patientId: number,
    caregiverId: number,
    user: AuthenticatedUser,
  ) {
    this.assertDashboardUser(user);

    await this.getPatientInDomain(patientId, user.domain_id);
    await this.getCaregiverInDomain(caregiverId, user.domain_id);

    const assignment = this.patientCaregiverRepo.create({
      patient_id: patientId,
      caregiver_id: caregiverId,
    });

    return await this.patientCaregiverRepo.save(assignment);
  }

  async unassignCaregiver(
    patientId: number,
    caregiverId: number,
    user: AuthenticatedUser,
  ) {
    this.assertDashboardUser(user);

    await this.getPatientInDomain(patientId, user.domain_id);
    await this.getCaregiverInDomain(caregiverId, user.domain_id);

    const assignment = await this.patientCaregiverRepo.findOne({
      where: {
        patient_id: patientId,
        caregiver_id: caregiverId,
      },
    });

    if (!assignment) {
      throw new NotFoundException('Assignment not found');
    }

    return await this.patientCaregiverRepo.remove(assignment);
  }

  async getCaregiversForPatient(patientId: number, user: AuthenticatedUser) {
    this.assertDashboardUser(user);
    await this.getPatientInDomain(patientId, user.domain_id);

    return await this.patientCaregiverRepo.find({
      where: { patient_id: patientId },
      relations: ['caregiver'],
    });
  }

  async getPatientsForCaregiver(caregiverId: number, user: AuthenticatedUser) {
    this.assertDashboardUser(user);
    await this.getCaregiverInDomain(caregiverId, user.domain_id);

    return await this.patientCaregiverRepo.find({
      where: { caregiver_id: caregiverId },
      relations: ['patient'],
    });
  }

  //==============ADMINS==============

  async getAllAdmins(user: AuthenticatedUser): Promise<Admin[]> {
    this.assertDashboardUser(user);

    return this.adminRepo
      .createQueryBuilder('admin')
      .innerJoin('admin.user', 'user')
      .where('user.domain_id = :domainId', { domainId: user.domain_id })
      .orderBy('admin.admin_id', 'ASC')
      .getMany();
  }

  async createAdmin(
    dto: CreateDomainAdminDto,
    user: AuthenticatedUser,
  ): Promise<Admin> {
    this.assertDashboardUser(user);

    return this.dataSource.transaction(async (manager) => {
      const savedUser = await this.createUser(
        manager,
        dto.email,
        dto.pass,
        'admin',
        user.domain_id,
      );

      return manager.save(
        manager.create(Admin, {
          user_id: savedUser.user_id,
          first_name: dto.first_name,
          last_name: dto.last_name,
          phone: dto.phone,
          job_title: dto.job_title ?? 'Administrator',
        }),
      );
    });
  }

  //==============SECURITY==============

  async getBreakGlassAccessLogs(user: AuthenticatedUser) {
    this.assertDashboardUser(user);

    const logs = await this.breakGlassAccessLogRepo
      .createQueryBuilder('log')
      .innerJoinAndSelect('log.caregiver', 'caregiver')
      .innerJoinAndSelect('caregiver.user', 'caregiverUser')
      .innerJoinAndSelect('log.patient', 'patient')
      .innerJoinAndSelect('patient.user', 'patientUser')
      .where('caregiverUser.domain_id = :domainId', {
        domainId: user.domain_id,
      })
      .andWhere('patientUser.domain_id = :domainId', {
        domainId: user.domain_id,
      })
      .orderBy('log.timestamp', 'DESC')
      .take(100)
      .getMany();

    return logs.map((log) => ({
      logId: log.break_glass_access_log_id,
      caregiverId: log.caregiver_id,
      caregiverName: log.caregiver
        ? `${log.caregiver.first_name} ${log.caregiver.last_name}`
        : 'Unknown',
      patientId: log.patient_id,
      patientName: log.patient
        ? `${log.patient.first_name} ${log.patient.last_name}`
        : 'Unknown',
      reason: log.reason,
      accessedStream: log.accessed_stream,
      timestamp: log.timestamp,
    }));
  }

  private assertDashboardUser(user: AuthenticatedUser) {
    if (!['admin', 'family'].includes(user.role)) {
      throw new ForbiddenException('Dashboard access is restricted');
    }
  }

  private async getPatientInDomain(patientId: number, domainId: number) {
    const patient = await this.patientRepository
      .createQueryBuilder('patient')
      .innerJoinAndSelect('patient.user', 'user')
      .where('patient.patient_id = :patientId', { patientId })
      .andWhere('user.domain_id = :domainId', { domainId })
      .getOne();

    if (!patient) {
      throw new NotFoundException('Patient not found in this domain');
    }

    return patient;
  }

  private async getCaregiverInDomain(caregiverId: number, domainId: number) {
    const caregiver = await this.caregiverRepo
      .createQueryBuilder('caregiver')
      .innerJoinAndSelect('caregiver.user', 'user')
      .where('caregiver.caregiver_id = :caregiverId', { caregiverId })
      .andWhere('user.domain_id = :domainId', { domainId })
      .getOne();

    if (!caregiver) {
      throw new NotFoundException('Caregiver not found in this domain');
    }

    return caregiver;
  }

  private async resolveFamilyId(user: AuthenticatedUser) {
    if (user.family_id) return user.family_id;

    const family = await this.familyRepo.findOne({
      where: { user_id: user.sub },
    });

    if (!family) {
      throw new NotFoundException('Family profile not found');
    }

    return family.family_id;
  }

  private async createUser(
    manager: EntityManager,
    email: string,
    password: string,
    role: string,
    domainId: number,
  ) {
    const existing = await manager.findOne(User, { where: { email } });
    if (existing) {
      throw new BadRequestException('Email is already registered');
    }

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
    dto: OnboardPatientDto,
    domainId: number,
  ) {
    const user = await manager.save(
      manager.create(User, {
        email: `patient_${dto.first_name.toLowerCase()}_${dto.last_name.toLowerCase()}_${Date.now()}@internal.memoriahome`,
        pass: 'N/A',
        role: 'patient',
        domain_id: domainId,
      }),
    );

    return manager.save(
      manager.create(Patient, {
        user_id: user.user_id,
        first_name: dto.first_name,
        last_name: dto.last_name,
        date_of_birth: dto.date_of_birth,
        gender: dto.gender,
        emergency_contact: dto.emergency_contact,
        emergency_contact_name: dto.emergency_contact_name,
        address: dto.address,
        dementia_stage: dto.dementia_stage,
      }),
    );
  }
}
