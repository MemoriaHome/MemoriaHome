import { Test, TestingModule } from '@nestjs/testing';
import { CaregiverService } from './caregiver.service';

describe('CaregiverService', () => {
  let service: CaregiverService;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [CaregiverService],
    }).compile();

    service = module.get<CaregiverService>(CaregiverService);
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });
});
