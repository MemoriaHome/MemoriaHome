from transformers import (
    Wav2Vec2ForSequenceClassification,
    Wav2Vec2Processor,
    TrainingArguments,
    Trainer
)
import torch
from torch.utils.data import Dataset
import librosa
import pandas as pd
import numpy as np

class StutterDataset(Dataset):
    def __init__(self, csv_path, audio_dir, processor):
        self.data      = pd.read_csv(csv_path)
        self.audio_dir = audio_dir
        self.processor = processor

        # Map stutter types to integers
        self.label_map = {
            'Prolongation':     0,
            'Block':            1,
            'SoundRep':         2,
            'WordRep':          3,
            'Interjection':     4,
            'NoStutteredWords': 5,
        }

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        row       = self.data.iloc[idx]
        audio, _  = librosa.load(
            f"{self.audio_dir}/{row['Show']}/{row['EpId']}.wav",
            sr=16000, mono=True,
            offset=row['Start'] / 1000,
            duration=(row['Stop'] - row['Start']) / 1000
        )
        inputs = self.processor(
            audio,
            sampling_rate=16000,
            return_tensors="pt",
            padding=True
        )
        label = self.label_map.get(row['Dysfluency'], 5)
        return {
            'input_values': inputs.input_values.squeeze(),
            'labels':       torch.tensor(label)
        }

# Train
processor = Wav2Vec2Processor.from_pretrained("facebook/wav2vec2-base")
model     = Wav2Vec2ForSequenceClassification.from_pretrained(
    "facebook/wav2vec2-base", num_labels=6
)

dataset = StutterDataset(
    "ml-stuttering-events-dataset/SEP-28k_episodes.csv",
    "sep28k_audio/",
    processor
)

args = TrainingArguments(
    output_dir="stutter_model",
    num_train_epochs=10,
    per_device_train_batch_size=8,
    save_steps=500,
    logging_steps=100,
)

trainer = Trainer(
    model=model,
    args=args,
    train_dataset=dataset,
)
trainer.train()
model.save_pretrained("stutter_model/final")