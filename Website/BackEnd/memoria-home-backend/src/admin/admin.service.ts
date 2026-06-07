import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Patient } from '../entities/patient.entity';
import { User } from '../entities/user.entity';
import { Caregiver } from '../entities/caregiver.entity';
import { PatientCaregiver } from '../entities/patientToCaregiver.entity';
import { OnboardPatientDto } from '../patient/dto/onboard-patient.dto';
import { BreakGlassAccessLog } from '../entities/break_glass_access_log.entity';

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

    @InjectRepository(BreakGlassAccessLog)
    private breakGlassAccessLogRepo: Repository<BreakGlassAccessLog>,
  ) {}

  //==============PATIENTS==============

  async getAllPatients(): Promise<Patient[]> {
    return await this.patientRepository.find();
  }

  async onboardPatient(dto: OnboardPatientDto): Promise<Patient> {
    // Create a placeholder user row to satisfy the FK constraint
    // Patients don't log in themselves so no real credentials are needed
    const user = this.userRepository.create({
      email:      `patient_${dto.first_name.toLowerCase()}_${dto.last_name.toLowerCase()}_${Date.now()}@internal.memoriahome`,
      pass:       'N/A',
      role:       'patient',
      created_at: new Date(),
    });

    const savedUser = await this.userRepository.save(user);

    const patient = this.patientRepository.create({
      user_id:                savedUser.user_id,
      first_name:             dto.first_name,
      last_name:              dto.last_name,
      date_of_birth:          dto.date_of_birth,
      gender:                 dto.gender,
      emergency_contact:      dto.emergency_contact,
      emergency_contact_name: dto.emergency_contact_name,
      address:                dto.address,
      dementia_stage:         dto.dementia_stage,
    });

    return await this.patientRepository.save(patient);
  }

  async deletePatient(patientId: number): Promise<void> {
    const patient = await this.patientRepository.findOneBy({ patient_id: patientId });

    if (!patient) {
      throw new Error('Patient not found');
    }

    // Grab user_id before removing — patient_caregivers cascades automatically
    // but the placeholder user record needs manual cleanup
    const userId = patient.user_id;
    await this.patientRepository.remove(patient);
    await this.userRepository.delete({ user_id: userId });
  }


  //==============CAREGIVERS==============

  async getAllCaregivers(): Promise<Caregiver[]> {
    return await this.caregiverRepo.find();
  }

  async assignCaregiver(patientId: number, caregiverId: number) {
    const patient   = await this.patientRepository.findOneBy({ patient_id: patientId });
    const caregiver = await this.caregiverRepo.findOneBy({ caregiver_id: caregiverId });

    if (!patient || !caregiver) {
      throw new Error('Patient or Caregiver not found');
    }

    const assignment = this.patientCaregiverRepo.create({
      patient_id:   patientId,
      caregiver_id: caregiverId,
    });

    return await this.patientCaregiverRepo.save(assignment);
  }

  async unassignCaregiver(patientId: number, caregiverId: number) {
    const assignment = await this.patientCaregiverRepo.findOne({
      where: {
        patient_id:   patientId,
        caregiver_id: caregiverId,
      },
    });

    if (!assignment) {
      throw new Error('Assignment not found');
    }

    return await this.patientCaregiverRepo.remove(assignment);
  }

  async getCaregiversForPatient(patientId: number) {
    return await this.patientCaregiverRepo.find({
      where:     { patient_id: patientId },
      relations: ['caregiver'],
    });
  }

  async getPatientsForCaregiver(caregiverId: number) {
    return await this.patientCaregiverRepo.find({
      where:     { caregiver_id: caregiverId },
      relations: ['patient'],
    });
  }

  //==============SECURITY==============

  async getBreakGlassAccessLogs() {
    const logs = await this.breakGlassAccessLogRepo.find({
      relations: ['caregiver', 'patient'],
      order: { timestamp: 'DESC' },
      take: 100,
    });

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

}
