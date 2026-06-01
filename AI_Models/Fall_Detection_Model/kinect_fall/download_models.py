import os
os.environ['REQUESTS_CA_BUNDLE']              = ''
os.environ['SSL_CERT_FILE']                   = ''
os.environ['CURL_CA_BUNDLE']                  = ''
os.environ['HF_HUB_DISABLE_SSL_VERIFICATION'] = '1'

import ssl
ssl._create_default_https_context = ssl._create_unverified_context

print("Downloading SpeechBrain emotion model...")
from speechbrain.inference.classifiers import EncoderClassifier

model = EncoderClassifier.from_hparams(
    source="speechbrain/emotion-recognition-wav2vec2-IEMOCAP",
    savedir="C:/kinect_fall/pretrained_models/emotion",  # ← absolute path
    run_opts={"device": "cpu"}
)
print("Emotion model downloaded successfully")

print("Downloading wav2vec2...")
from transformers import (
    Wav2Vec2ForSequenceClassification,
    Wav2Vec2Processor
)
processor = Wav2Vec2Processor.from_pretrained(
    "facebook/wav2vec2-base",
    cache_dir="C:/kinect_fall/pretrained_models/wav2vec2"
)
model2 = Wav2Vec2ForSequenceClassification.from_pretrained(
    "facebook/wav2vec2-base",
    num_labels=6,
    ignore_mismatched_sizes=True,
    cache_dir="C:/kinect_fall/pretrained_models/wav2vec2"
)
print("wav2vec2 downloaded successfully")
print("All models downloaded!")