 import { Controller, Get, Patch, Param, Delete, Body } from '@nestjs/common';
import { CaregiverService } from './caregiver.service';
import { UpdateCaregiverDto } from './dto/update-caregiver.dto';

@Controller('caregiver')
export class CaregiverController {
  constructor(private readonly caregiverService: CaregiverService) {}

  @Get()
  findAll() {
    return this.caregiverService.findAll();
  }

  @Get(':id')
  findOne(@Param('id') id: string) {
    return this.caregiverService.findOne(+id);
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

