import { Controller, Get, Post, Body, Patch, Param, Delete, UseGuards } from '@nestjs/common';
import { CaregiverService } from './caregiver.service';
import { CreateCaregiverDto } from './dto/create-caregiver.dto';
import { UpdateCaregiverDto } from './dto/update-caregiver.dto';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';
import { RolesGuard } from '../auth/roles.guard';
import { Roles } from '../auth/roles.decorator';

@Controller('caregiver')
@UseGuards(JwtAuthGuard, RolesGuard)
export class CaregiverController {
  constructor(private readonly caregiverService: CaregiverService) {}

  @Post()
  @Roles('admin')
  create(@Body() createCaregiverDto: CreateCaregiverDto) {
    return this.caregiverService.create(createCaregiverDto);
  }

  @Get()
  @Roles('admin', 'caregiver', 'family')
  findAll() {
    return this.caregiverService.findAll();
  }

  @Get(':id')
  @Roles('admin', 'caregiver', 'family')
  findOne(@Param('id') id: string) {
    return this.caregiverService.findOne(+id);
  }

  @Patch(':id')
  @Roles('admin', 'caregiver')
  update(@Param('id') id: string, @Body() updateCaregiverDto: UpdateCaregiverDto) {
    return this.caregiverService.update(+id, updateCaregiverDto);
  }

  @Delete(':id')
  @Roles('admin')
  remove(@Param('id') id: string) {
    return this.caregiverService.remove(+id);
  }
}