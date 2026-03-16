import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';
import { ValidationPipe } from '@nestjs/common';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  app.enableCors(); //this is added to stop the browser from blocking communication between ports when testing 
  await app.listen(3000);
  app.useGlobalPipes(new ValidationPipe({ transform: true }));
}
bootstrap();
