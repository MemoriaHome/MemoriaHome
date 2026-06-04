import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Caregiver } from '../entities/caregiver.entity';
import { CreateCaregiverDto } from './dto/create-caregiver.dto';
import { UpdateCaregiverDto } from './dto/update-caregiver.dto';

@Injectable()
export class CaregiverService {

  constructor(
    @InjectRepository(Caregiver)
    private caregiverRepository: Repository<Caregiver>,
  ) {}

  async create(createCaregiverDto: CreateCaregiverDto) {
    const caregiver = this.caregiverRepository.create(createCaregiverDto);
    return await this.caregiverRepository.save(caregiver);
  }

  async findAll() {
    return await this.caregiverRepository.find();
  }

  async findOne(id: number) {
    const caregiver = await this.caregiverRepository.findOne({ where: { caregiver_id: id } });
    if (!caregiver) throw new NotFoundException(`Caregiver #${id} not found`);
    return caregiver;
  }

  async update(id: number, updateCaregiverDto: UpdateCaregiverDto) {
    const caregiver = await this.findOne(id);
    Object.assign(caregiver, updateCaregiverDto);
    return await this.caregiverRepository.save(caregiver);
  }

  async remove(id: number) {
    const caregiver = await this.findOne(id);
    return await this.caregiverRepository.remove(caregiver);
  }
}
