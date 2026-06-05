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
    Wav2Vec2Processor,
    get_linear_schedule_with_warmup,
)

SAMPLE_RATE = 16000

LABEL_MAP = {
    'Prolongation':     0,
    'Block':            1,
    'SoundRep':         2,
    'WordRep':          3,
    'Interjection':     4,
    'NoStutteredWords': 5,
}

SKIP_IF_FLAGGED = {'Unsure', 'PoorAudio'}
IGNORE_COLS     = {'DifficultToUnderstand', 'NaturalPause', 'Music', 'NoSpeech'}
EPOCHS          = 3
BATCH_SIZE      = 16


class SEP28kDataset(Dataset):
    def __init__(self, csv_path, audio_dir, processor):
        self.df = pd.read_csv(csv_path)
        self.audio_dir = audio_dir
        self.processor = processor

        self.df['filename'] = self.df.apply(
            lambda r: f"{r['Show']}_{r['EpId']}_{r['ClipId']}.wav", axis=1
        )

        before = len(self.df)
        for flag in SKIP_IF_FLAGGED:
            if flag in self.df.columns:
                self.df = self.df[self.df[flag] != 1]
        print(f"Dropped {before - len(self.df)} clips flagged as Unsure/PoorAudio.")

        print("Checking which audio slices are available...")
        self.df = self.df[
            self.df['filename'].apply(
                lambda f: os.path.exists(os.path.join(audio_dir, f))
            )
        ].reset_index(drop=True)

        self._print_label_distribution()
        print(f"Dataset ready: {len(self.df)} clips.")

    def _print_label_distribution(self):
        print("\nLabel distribution:")
        for name in LABEL_MAP:
            if name in self.df.columns:
                count = int(self.df[name].sum())
                print(f"  {name:20s}: {count}")
        print()

    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx):
        row = self.df.iloc[idx]

        show = str(row['Show'])
        episode = str(row['EpId'])
        clip = str(row['ClipId'])

        nested_path = os.path.join(self.audio_dir, show, episode, f"{show}_{episode}_{clip}.wav")
        flat_path = os.path.join(self.audio_dir, row['filename'])
        audio_path = nested_path if os.path.exists(nested_path) else flat_path

        try:
            audio, _ = librosa.load(audio_path, sr=SAMPLE_RATE, mono=True)
        except Exception as e:
            print(f"WARNING: Could not load {audio_path}: {e} — using silence.")
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
            padding=True
        )

        label = 5
        for name, label_idx in LABEL_MAP.items():
            if name in row.index and row[name] == 1:
                label = label_idx
                break

        return {
            'input_values': inputs.input_values.squeeze(),
            'labels': torch.tensor(label, dtype=torch.long),
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
        num_labels=len(LABEL_MAP),
        ignore_mismatched_sizes=True,
        cache_dir='pretrained_models/wav2vec2'
    ).to(device)

    dataset = SEP28kDataset(
        'ml-stuttering-events-dataset/SEP-28k_labels.csv',
        'sep28k_audio',
        processor
    )

    if len(dataset) == 0:
        print("ERROR: No matching audio files found! Double-check your 'sep28k_audio' folder.")
        return

    dataloader = DataLoader(dataset, batch_size=BATCH_SIZE, shuffle=True, num_workers=2, pin_memory=True)

    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-5)
    criterion = torch.nn.CrossEntropyLoss()

    total_steps = len(dataloader) * EPOCHS
    warmup_steps = total_steps // 10
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=warmup_steps,
        num_training_steps=total_steps
    )

    model.train()
    print(f"Training started: {total_steps} total steps, {warmup_steps} warmup steps.\n")

    for epoch in range(EPOCHS):
        total_loss = 0
        correct = 0
        total = 0

        for batch in dataloader:
            optimizer.zero_grad()

            input_values = batch['input_values'].to(device)
            labels = batch['labels'].to(device)

            outputs = model(input_values=input_values)
            loss = criterion(outputs.logits, labels)

            loss.backward()
            optimizer.step()
            scheduler.step()

            total_loss += loss.item()
            preds = torch.argmax(outputs.logits, dim=1)
            correct += (preds == labels).sum().item()
            total += len(labels)

        acc = correct / total * 100
        current_lr = scheduler.get_last_lr()[0]
        print(f"Epoch {epoch+1}/{EPOCHS} — "
              f"Loss: {total_loss/len(dataloader):.4f} — "
              f"Acc: {acc:.1f}% — "
              f"LR: {current_lr:.2e}")

    os.makedirs('stutter_model/final', exist_ok=True)
    model.save_pretrained('stutter_model/final')
    processor.save_pretrained('stutter_model/final')
    print("\nModel saved to stutter_model/final")


if __name__ == '__main__':
    train()