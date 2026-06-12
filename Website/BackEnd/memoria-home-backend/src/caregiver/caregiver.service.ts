import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Caregiver } from '../entities/caregiver.entity';
import { UpdateCaregiverDto } from './dto/update-caregiver.dto';
import { EncryptionService } from '../encryption.service';

@Injectable()
export class CaregiverService {

  constructor(
    @InjectRepository(Caregiver)
    private caregiverRepository: Repository<Caregiver>,
    private encryptionService: EncryptionService,
  ) {}

  async findAll() {
    const caregivers = await this.caregiverRepository.find();
    return caregivers.map(c => this.decrypt(c));
  }

  async findOne(id: number) {
    const caregiver = await this.caregiverRepository.findOne({ where: { caregiver_id: id } });
    if (!caregiver) throw new NotFoundException('Caregiver not found');
    return this.decrypt(caregiver);
  }

  async update(id: number, updateCaregiverDto: UpdateCaregiverDto) {
    const caregiver = await this.caregiverRepository.findOne({ where: { caregiver_id: id } });
    if (!caregiver) throw new NotFoundException('Caregiver not found');

    if (updateCaregiverDto.first_name)
      caregiver.first_name = this.encryptionService.encrypt(updateCaregiverDto.first_name);
    if (updateCaregiverDto.last_name)
      caregiver.last_name = this.encryptionService.encrypt(updateCaregiverDto.last_name);
    if (updateCaregiverDto.phone)
      caregiver.phone = this.encryptionService.encrypt(updateCaregiverDto.phone);
    if (updateCaregiverDto.specialization)
      caregiver.specialization = this.encryptionService.encrypt(updateCaregiverDto.specialization);
    if (updateCaregiverDto.license_number)
      caregiver.license_number = this.encryptionService.encrypt(updateCaregiverDto.license_number);
    if (updateCaregiverDto.years_experience)
      caregiver.years_experience = updateCaregiverDto.years_experience;

    const saved = await this.caregiverRepository.save(caregiver);
    return this.decrypt(saved);
  }

  async remove(id: number) {
    const caregiver = await this.caregiverRepository.findOne({ where: { caregiver_id: id } });
    if (!caregiver) throw new NotFoundException('Caregiver not found');
    await this.caregiverRepository.remove(caregiver);
    return { message: 'Caregiver deleted successfully' };
  }

  private decrypt(caregiver: Caregiver) {
    return {
      ...caregiver,
      first_name: this.encryptionService.decrypt(caregiver.first_name),
      last_name: this.encryptionService.decrypt(caregiver.last_name),
      phone: this.encryptionService.decrypt(caregiver.phone),
      specialization: this.encryptionService.decrypt(caregiver.specialization),
      license_number: this.encryptionService.decrypt(caregiver.license_number),
    };
  }
}