import os
import csv
from pathlib import Path
from typing import Optional, Tuple, List

import numpy as np
from PIL import Image

import torch
from torch.utils.data import Dataset, DataLoader, WeightedRandomSampler
import torchvision.transforms as T
import torchvision.transforms.functional as TF

NUM_CLASSES = 5
CLASS_NAMES = ["Standing", "Sitting", "Lying", "Bending", "Crawling"]
IMG_H, IMG_W = 160, 120
CROP_H, CROP_W = 156, 108

# fallback for compute_dataset_stats (from imagenet)
MEAN = [0.485, 0.456, 0.406, 0.5]
STD = [0.229, 0.224, 0.225, 0.25]

# calculates the means and standard dev of the rgbd dataset for normalization
def compute_dataset_stats(root: str, split: str = "train", max_samples: int = 2000) -> Tuple[List[float], List[float]]:
    samples = _collect_samples(root, split)
    np.random.shuffle(samples)
    samples = samples[:max_samples]

    running_mean = np.zeros(4)
    running_sq = np.zeros(4)
    count = 0

    for rgb_path, depth_path, _ in samples:
        rgb = np.array(Image.open(rgb_path).convert("RGB"), dtype=np.float32) / 255.0
        depth = np.array(Image.open(depth_path).convert("L"), dtype=np.float32) / 255.0
        rgbd = np.concatenate([rgb, depth[..., None]], axis=-1)
        running_mean += rgbd.reshape(-1, 4).mean(axis=0)
        running_sq += (rgbd.reshape(-1, 4) ** 2).mean(axis=0)
        count += 1

    mean = running_mean / count
    std = np.sqrt(running_sq / count - mean ** 2)
    return mean.tolist(), std.tolist()

# scans the dir structure to pair rgb images, depth maps, and labels into a list
def _collect_samples(root: str, split: str) -> List[Tuple[str, str, int]]:
    split_dir = Path(root) / split
    samples: List[Tuple[str, str, int]] = []

    if not split_dir.exists():
        raise FileNotFoundError(
            f"Split directory not found: {split_dir}\n"
            f"Run download_data.py first."
        )

    for folder in sorted(split_dir.iterdir()):
        if not folder.is_dir():
            continue
        rgb_dir = folder / "rgb"
        depth_dir = folder / "depth"
        label_csv = folder / "labels.csv"

        if not (rgb_dir.exists() and depth_dir.exists() and label_csv.exists()):
            sub = folder / folder.name
            rgb_dir = sub / "rgb"
            depth_dir = sub / "depth"
            label_csv = sub / "labels.csv"
            if not (rgb_dir.exists() and depth_dir.exists() and label_csv.exists()):
                print(f"Skipping {folder}.")
                continue

        labels: dict[int, int] = {}
        with open(label_csv, newline="") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) < 2:
                    continue
                try:
                    serial = int(row[0])
                    cls = int(row[1])
                    labels[serial] = cls - 1
                except ValueError:
                    pass

        for rgb_path in sorted(rgb_dir.glob("rgb_*.png")):
            try:
                serial = int(rgb_path.stem.split("_")[1])
            except (IndexError, ValueError):
                continue
            depth_path = depth_dir / rgb_path.name.replace("rgb_", "depth_")
            if not depth_path.exists():
                continue
            label = labels.get(serial, -1)
            if label == -1: 
                continue
            if label == 7:
                label = 0
            samples.append((str(rgb_path), str(depth_path), label))

    return samples

def _build_transforms(split: str, mean: List[float] = MEAN, std:  List[float] = STD):
    normalize = T.Normalize(mean=mean, std=std)

    if split == "train":
        joint = _JointTransformTrain()
    else:
        joint = _JointTransformEval()

    return joint, normalize

# here, i used data augmentation to create fake variations of the data
# by randomly cropping or flipping the image, i'm forcing the model to learn that a person is
# still a person, even if they aren't perfectly centered
# i also applied the chnages to both the rgb and depth images the same exact way 
class _JointTransformTrain:
    def __call__(self, rgb: Image.Image, depth: Image.Image) -> Tuple[torch.Tensor, torch.Tensor]:
        rgb = TF.resize(rgb, [IMG_H, IMG_W])
        depth = TF.resize(depth, [IMG_H, IMG_W])

        i, j, h, w = T.RandomCrop.get_params(rgb, output_size=(CROP_H, CROP_W))
        rgb = TF.crop(rgb, i, j, h, w)
        depth = TF.crop(depth, i, j, h, w)

        if torch.rand(1) > 0.5:
            rgb = TF.hflip(rgb)
            depth = TF.hflip(depth)

        rgb = T.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.2)(rgb)

        rgb_t = TF.to_tensor(rgb)
        depth_t = TF.to_tensor(depth.convert("L"))
        return rgb_t, depth_t


class _JointTransformEval:
    def __call__(self, rgb: Image.Image, depth: Image.Image) -> Tuple[torch.Tensor, torch.Tensor]:
        rgb = TF.resize(rgb, [IMG_H, IMG_W])
        depth = TF.resize(depth, [IMG_H, IMG_W])

        rgb = TF.center_crop(rgb, [CROP_H, CROP_W])
        depth = TF.center_crop(depth, [CROP_H, CROP_W])

        rgb_t = TF.to_tensor(rgb)
        depth_t = TF.to_tensor(depth.convert("L"))
        return rgb_t, depth_t
    

class FallDataset(Dataset):
    def __init__(self, root:  str, split: str = "train", mean:  Optional[List[float]] = None, std:   Optional[List[float]] = None):
        self.split   = split
        self.samples = _collect_samples(root, split)
        if len(self.samples) == 0:
            raise RuntimeError(f"No samples found for split='{split}' under {root}")

        mean = mean or MEAN
        std = std  or STD
        self.joint_tf = _build_transforms(split, mean, std)[0]
        self.normalize = T.Normalize(mean=mean, std=std)

        print(f"[FallDataset] split={split:5s}  samples={len(self.samples):6d}")

    def class_weights(self) -> torch.Tensor:
        counts = torch.zeros(NUM_CLASSES)
        for _, _, lbl in self.samples:
            counts[lbl] += 1
        weights = 1.0 / counts.clamp(min=1)
        return weights / weights.sum()

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        rgb_path, depth_path, label = self.samples[idx]

        rgb = Image.open(rgb_path).convert("RGB")
        depth = Image.open(depth_path).convert("L")

        rgb_t, depth_t = self.joint_tf(rgb, depth)
        rgbd_t = torch.cat([rgb_t, depth_t], dim=0)
        rgbd_t = self.normalize(rgbd_t)

        return rgbd_t, torch.tensor(label, dtype=torch.long)


def build_dataloaders(root: str, batch_size: int = 32, num_workers: int = 4, mean: Optional[List[float]] = None, std: Optional[List[float]] = None, oversample_train: bool = True) -> dict[str, DataLoader]:
    loaders = {}

    for split in ("train", "val", "test"):
        ds = FallDataset(root, split=split, mean=mean, std=std)

        if split == "train" and oversample_train:
            weights_per_class  = ds.class_weights()
            sample_weights = torch.tensor(
                [weights_per_class[lbl] for _, _, lbl in ds.samples]
            )
            sampler = WeightedRandomSampler(
                sample_weights, num_samples=len(ds), replacement=True
            )
            loaders[split] = DataLoader(
                ds, batch_size=batch_size, sampler=sampler,
                num_workers=num_workers, pin_memory=True
            )
        else:
            loaders[split] = DataLoader(
                ds, batch_size=batch_size, shuffle=False,
                num_workers=num_workers, pin_memory=True
            )

    return loaders