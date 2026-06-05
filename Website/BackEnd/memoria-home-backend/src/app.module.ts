import { Module } from '@nestjs/common';
import { AppController } from './app.controller';
import { AppService } from './app.service';
import { AuthModule } from './auth/auth.module';
import { TypeOrmModule } from '@nestjs/typeorm';
import { CaregiverModule } from './caregiver/caregiver.module'
import { AdminModule } from './admin/admin.module';
import { GatewayModule } from './signaling/signaling.module';
import { MqttModule } from './mqtt/mqtt.module';
import { AlertModule } from './alert/alert.module';

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
    GatewayModule,
    MqttModule,
    AlertModule,
  ],
  controllers: [AppController],
  providers: [AppService],
})
export class AppModule {}
