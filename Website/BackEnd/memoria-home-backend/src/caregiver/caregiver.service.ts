import { Injectable, NotFoundException } from '@nestjs/common';
import { CreateCaregiverDto } from './dto/create-caregiver.dto';
import { UpdateCaregiverDto } from './dto/update-caregiver.dto';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Patient } from '../entities/patient.entity';
import { PatientCaregiver } from '../entities/patientToCaregiver.entity';
import { Caregiver } from '../entities/caregiver.entity';

@Injectable()
export class CaregiverService {

  constructor(
      @InjectRepository(PatientCaregiver)
      private patientCaregiverRepo: Repository<PatientCaregiver>,
  
      @InjectRepository(Caregiver)
      private caregiverRepo: Repository<Caregiver>,
    ) {}

  create(createCaregiverDto: CreateCaregiverDto) {
    return 'This action adds a new caregiver';
  }

  findAll() {
    return `This action returns all caregiver`;
  }

  findOne(id: number) {
    return `This action returns a #${id} caregiver`;
  }

  update(id: number, updateCaregiverDto: UpdateCaregiverDto) {
    return `This action updates a #${id} caregiver`;
  }

  remove(id: number) {
    return `This action removes a #${id} caregiver`;
  }

    async getMyPatients(caregiverId: number) {
    const caregiver = await this.caregiverRepo.findOneBy({ caregiver_id: caregiverId });
    if (!caregiver) throw new NotFoundException(`Caregiver #${caregiverId} not found`);
 
    const assignments = await this.patientCaregiverRepo.find({
      where:     { caregiver_id: caregiverId },
      relations: ['patient'],
    });
 
    return {
      caregiver,
      patients: assignments.map(a => a.patient),
    };
  }

  async getCaregiverIdByPatient(patientId: number): Promise<number | null> {
  const assignment = await this.patientCaregiverRepo.findOne({
    where: { patient_id: patientId },
  });
  return assignment ? assignment.caregiver_id : null;
}

}
