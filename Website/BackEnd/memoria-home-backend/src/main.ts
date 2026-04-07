import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';
import { ValidationPipe } from '@nestjs/common';
import * as fs from 'fs';

async function bootstrap() {

  const httpsOptions = {
  key: fs.readFileSync('./SSL/key.pem'),
  cert: fs.readFileSync('./SSL/cert.pem'),
};

  const app = await NestFactory.create(AppModule, { httpsOptions });
  app.enableCors(); //this is added to stop the browser from blocking communication between ports when testing 
  app.useGlobalPipes(new ValidationPipe({ transform: true }));
  await app.listen(3000);
}
bootstrap();
