import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Patient } from '../entities/patient.entity';
import { EncryptionService } from '../encryption.service';

@Injectable()
export class PatientService {

  constructor(
    @InjectRepository(Patient)
    private patientRepository: Repository<Patient>,
    private encryptionService: EncryptionService,
  ) {}

  async create(data: Partial<Patient>) {
    const patient = this.patientRepository.create({
      ...data,
      first_name: this.encryptionService.encrypt(data.first_name!),
      last_name: this.encryptionService.encrypt(data.last_name!),
      emergency_contact: data.emergency_contact ? this.encryptionService.encrypt(data.emergency_contact) : undefined,
      emergency_contact_name: data.emergency_contact_name ? this.encryptionService.encrypt(data.emergency_contact_name) : undefined,
      address: data.address ? this.encryptionService.encrypt(data.address) : undefined,
      dementia_stage: data.dementia_stage ? this.encryptionService.encrypt(data.dementia_stage) : undefined,
    });

    const saved = await this.patientRepository.save(patient);
    return this.decrypt(saved);
  }

  async findAll() {
    const patients = await this.patientRepository.find();
    return patients.map(p => this.decrypt(p));
  }

  async findOne(id: number) {
    const patient = await this.patientRepository.findOne({ where: { patient_id: id } });
    if (!patient) throw new NotFoundException('Patient not found');
    return this.decrypt(patient);
  }

  async update(id: number, data: Partial<Patient>) {
    const patient = await this.patientRepository.findOne({ where: { patient_id: id } });
    if (!patient) throw new NotFoundException('Patient not found');

    if (data.first_name) patient.first_name = this.encryptionService.encrypt(data.first_name);
    if (data.last_name) patient.last_name = this.encryptionService.encrypt(data.last_name);
    if (data.emergency_contact) patient.emergency_contact = this.encryptionService.encrypt(data.emergency_contact);
    if (data.emergency_contact_name) patient.emergency_contact_name = this.encryptionService.encrypt(data.emergency_contact_name);
    if (data.address) patient.address = this.encryptionService.encrypt(data.address);
    if (data.dementia_stage) patient.dementia_stage = this.encryptionService.encrypt(data.dementia_stage);
    if (data.gender) patient.gender = data.gender;
    if (data.date_of_birth) patient.date_of_birth = data.date_of_birth;

    const saved = await this.patientRepository.save(patient);
    return this.decrypt(saved);
  }

  async remove(id: number) {
    const patient = await this.patientRepository.findOne({ where: { patient_id: id } });
    if (!patient) throw new NotFoundException('Patient not found');
    await this.patientRepository.remove(patient);
    return { message: 'Patient deleted successfully' };
  }

  private decrypt(patient: Patient) {
    return {
      ...patient,
      first_name: this.encryptionService.decrypt(patient.first_name),
      last_name: this.encryptionService.decrypt(patient.last_name),
      emergency_contact: patient.emergency_contact ? this.encryptionService.decrypt(patient.emergency_contact) : null,
      emergency_contact_name: patient.emergency_contact_name ? this.encryptionService.decrypt(patient.emergency_contact_name) : null,
      address: patient.address ? this.encryptionService.decrypt(patient.address) : null,
      dementia_stage: patient.dementia_stage ? this.encryptionService.decrypt(patient.dementia_stage) : null,
    };
  }
}