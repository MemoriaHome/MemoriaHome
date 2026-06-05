import os
import certifi
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
os.environ['SSL_CERT_FILE'] = certifi.where()
import numpy as np
import torch
import librosa
import pandas as pd
from torch.utils.data import Dataset, DataLoader
from transformers import (
    Wav2Vec2ForSequenceClassification,
    Wav2Vec2Processor
)

SAMPLE_RATE  = 16000
LABEL_MAP    = {
    'Prolongation': 0,
    'Block':         1,
    'SoundRep':      2,
    'WordRep':       3,
    'Interjection': 4,
    'NoStutteredWords': 5,
}

class SEP28kDataset(Dataset):
    def __init__(self, csv_path, audio_dir, processor):
        self.df        = pd.read_csv(csv_path)
        self.audio_dir = audio_dir
        self.processor = processor

        self.df['filename'] = self.df.apply(
            lambda r: f"{r['Show']}_{r['EpId']}_{r['ClipId']}.wav", axis=1
        )

        print("Checking which Kaggle audio slices are available...")
        self.df = self.df[
            self.df['filename'].apply(
                lambda f: os.path.exists(os.path.join(audio_dir, f))
            )
        ].reset_index(drop=True)

        print(f"Dataset initialized successfully with: {len(self.df)} clips.")

    def __len__(self):
        return len(self.df)

    # Priority-ordered dysfluency columns as they appear in SEP-28k
    DYSFLUENCY_COLS = ['Prolongation', 'Block', 'SoundRep', 'WordRep', 'Interjection', 'NoStutteredWords']

    def __getitem__(self, idx):
        # Priority-ordered dysfluency columns as they appear in SEP-28k
        DYSFLUENCY_COLS = ['Prolongation', 'Block', 'SoundRep', 'WordRep', 'Interjection', 'NoStutteredWords']
        row  = self.df.iloc[idx]
        path = os.path.join(self.audio_dir, row['filename'])

        try:
            audio, _ = librosa.load(path, sr=SAMPLE_RATE, mono=True)
        except Exception as e:
            print(f"[WARN] Failed to load {path}: {e}")
            audio = np.zeros(SAMPLE_RATE * 3, dtype=np.float32)

        target = SAMPLE_RATE * 3
        if len(audio) < target:
            audio = np.pad(audio, (0, target - len(audio)))
        else:
            audio = audio[:target]

        inputs = self.processor(
            audio,
            sampling_rate=SAMPLE_RATE,
            return_tensors='pt',
        )

        # SEP-28k: each column holds an annotator vote count; pick the highest-voted label
        label = 5  # default: NoStutteredWords
        best  = 0
        for col in DYSFLUENCY_COLS:
            if col in row.index:
                count = int(row[col])
                if count > best:
                    best  = count
                label = LABEL_MAP[col]

        return {
        'input_values': inputs.input_values.squeeze(),
        'label':        torch.tensor(label, dtype=torch.long)
    }

def train():
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Using device: {device}")

    processor = Wav2Vec2Processor.from_pretrained(
        'facebook/wav2vec2-base',
        cache_dir='pretrained_models/wav2vec2'
    )
    model = Wav2Vec2ForSequenceClassification.from_pretrained(
        'facebook/wav2vec2-base',
        num_labels=6,
        ignore_mismatched_sizes=True,
        cache_dir='pretrained_models/wav2vec2'
    ).to(device)

    dataset    = SEP28kDataset(
        'ml-stuttering-events-dataset/SEP-28k_labels.csv',
        'sep28k_audio',
        processor
    )
    
    if len(dataset) == 0:
        print("ERROR: No matching audio files found! Double-check your 'sep28k_audio' folder contents.")
        return

    dataloader = DataLoader(dataset, batch_size=4, shuffle=True)

    optimizer  = torch.optim.AdamW(model.parameters(), lr=1e-5)
    criterion  = torch.nn.CrossEntropyLoss()

    model.train()
    print("Training started...")

    for epoch in range(5):
        total_loss = 0
        correct    = 0
        total      = 0

        for batch in dataloader:
            optimizer.zero_grad()

            input_values = batch['input_values'].to(device)
            labels = batch['label'].to(device)

            outputs = model(input_values=input_values)
            loss = criterion(outputs.logits, labels)
            
            loss.backward()
            optimizer.step()

            total_loss += loss.item()
            preds       = torch.argmax(outputs.logits, dim=1)
            correct    += (preds == labels).sum().item()
            total      += len(labels)

        acc = correct / total * 100
        print(f"Epoch {epoch+1}/5 — "
              f"Loss: {total_loss/len(dataloader):.4f} — "
              f"Acc: {acc:.1f}%")

    os.makedirs('stutter_model/final', exist_ok=True)
    model.save_pretrained('stutter_model/final')
    processor.save_pretrained('stutter_model/final')
    print("Model saved safely to stutter_model/final")


if __name__ == '__main__':
    train()