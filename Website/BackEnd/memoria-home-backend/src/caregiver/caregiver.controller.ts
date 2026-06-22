import {
  Body,
  Controller,
  Delete,
  ForbiddenException,
  Get,
  Param,
  ParseIntPipe,
  Patch,
  Post,
  Req,
  UseGuards,
} from '@nestjs/common';
import { CaregiverService } from './caregiver.service';
import { CreateCaregiverDto } from './dto/create-caregiver.dto';
import { UpdateCaregiverDto } from './dto/update-caregiver.dto';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';
import type { AuthenticatedRequest } from '../auth/jwt-auth.guard';

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
  @UseGuards(JwtAuthGuard)
  getMyPatients(
    @Param('id', ParseIntPipe) id: number,
    @Req() req: AuthenticatedRequest,
  ) {
    if (
      req.user.role !== 'caregiver' ||
      !req.user.caregiver_id ||
      req.user.caregiver_id !== id
    ) {
      throw new ForbiddenException(
        'Caregivers can only access their own assigned patients',
      );
    }

    return this.caregiverService.getMyPatients(req.user.caregiver_id);
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
