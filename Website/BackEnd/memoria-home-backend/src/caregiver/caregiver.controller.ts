import { Controller, Get, Post, Body, Patch, Param, Delete } from '@nestjs/common';
import { CaregiverService } from './caregiver.service';
import { CreateCaregiverDto } from './dto/create-caregiver.dto';
import { UpdateCaregiverDto } from './dto/update-caregiver.dto';

@Controller('caregiver')
export class CaregiverController {

  constructor(
    private readonly caregiverService: CaregiverService,
  ) {}

  @Post()
  create(@Body() createCaregiverDto: CreateCaregiverDto) {
    return this.caregiverService.create(createCaregiverDto);
  }

  @Get()
  findAll() {
    return this.caregiverService.findAll();
  }

  @Get(':id')
  findOne(@Param('id') id: string) {
    return this.caregiverService.findOne(+id);
  }

  // Returns the caregiver's profile + all their assigned patients
  @Get(':id/patients')
  getMyPatients(@Param('id') id: string) {
    return this.caregiverService.getMyPatients(+id);
  }

  @Patch(':id')
  update(@Param('id') id: string, @Body() updateCaregiverDto: UpdateCaregiverDto) {
    return this.caregiverService.update(+id, updateCaregiverDto);
  }

  @Delete(':id')
  remove(@Param('id') id: string) {
    return this.caregiverService.remove(+id);
  }
}