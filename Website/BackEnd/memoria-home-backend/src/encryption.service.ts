import { Injectable } from '@nestjs/common';
import * as CryptoJS from 'crypto-js';

@Injectable()
export class EncryptionService {
  private readonly secretKey = process.env.ENCRYPTION_KEY || 'memoria_encryption_key_2026';

  encrypt(text: string): string {
    if (!text) return text;
    return CryptoJS.AES.encrypt(text, this.secretKey).toString();
  }

  decrypt(cipherText: string): string {
    if (!cipherText) return cipherText;
    const bytes = CryptoJS.AES.decrypt(cipherText, this.secretKey);
    return bytes.toString(CryptoJS.enc.Utf8);
  }
}