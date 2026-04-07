import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Patient } from '../entities/patient.entity';
import { User } from '../entities/user.entity';
import { OnboardPatientDto } from '../patient/dto/onboard-patient.dto';

@Injectable()
export class AdminService {

  constructor(
    @InjectRepository(Patient)
    private patientRepository: Repository<Patient>,

    @InjectRepository(User)
    private userRepository: Repository<User>,
  ) {}

  async onboardPatient(dto: OnboardPatientDto): Promise<Patient> {
    // Step 1: Create a user record to satisfy the FK constraint (patients.user_id → users.user_id)
    // Patients don't log in themselves, so we generate a placeholder credential
    const user = this.userRepository.create({
      email: `patient_${dto.first_name.toLowerCase()}_${dto.last_name.toLowerCase()}_${Date.now()}@internal.memoriahome`,
      pass: 'N/A',        // no login — placeholder only
      role: 'patient',
      created_at: new Date(),
    });

    const savedUser = await this.userRepository.save(user);

    // Step 2: Create the patient record linked to that user
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

}