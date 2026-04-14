import { Module } from '@nestjs/common';
import { AppController } from './app.controller';
import { AppService } from './app.service';
import { AuthModule } from './auth/auth.module';
import { TypeOrmModule } from '@nestjs/typeorm';
import { CaregiverModule } from './caregiver/caregiver.module'
import { AdminModule } from './admin/admin.module';
import { SignalingModule } from './signaling/signaling.module';
import { MqttModule } from './mqtt/mqtt.module';

@Module({
  imports: [TypeOrmModule.forRoot({
      type: 'postgres',
      host: 'localhost',
      port: 5050,
      username: 'postgres',
      password: 'admin',
      database: 'postgres',
      autoLoadEntities: true,
      synchronize: false,
    }),
    CaregiverModule,
    AuthModule,
    AdminModule,
    SignalingModule,
    MqttModule,
  ],
  controllers: [AppController],
  providers: [AppService],
})
export class AppModule {}
