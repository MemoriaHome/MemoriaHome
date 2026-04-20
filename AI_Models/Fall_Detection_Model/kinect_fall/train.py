import argparse
import os
import time
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import torch
import torch.nn as nn
from torch.optim import AdamW
from torch.optim.lr_scheduler import OneCycleLR
from arch import arch_model

from dataset import build_dataloaders, NUM_CLASSES, CLASS_NAMES
from model import FallDetectorCNN


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train fall detection CNN")
    p.add_argument("--data_root", default="./data")
    p.add_argument("--epochs", type=int,   default=30)
    p.add_argument("--batch_size", type=int,   default=32)
    p.add_argument("--lr", type=float, default=1e-4)
    p.add_argument("--dropout", type=float, default=0.5)
    p.add_argument("--num_workers", type=int,   default=4)
    p.add_argument("--save_dir", default="./checkpoints")
    p.add_argument("--patience", type=int,   default=7)
    p.add_argument("--no_oversample", action="store_true")
    p.add_argument("--device", default="")
    return p.parse_args()


def accuracy(preds: torch.Tensor, labels: torch.Tensor) -> float:
    return (preds.argmax(1) == labels).float().mean().item()


def per_class_sensitivity(preds: torch.Tensor, labels: torch.Tensor) -> Dict[int, float]:
    sens = {}
    for c in range(NUM_CLASSES):
        mask = labels == c
        if mask.sum() == 0:
            sens[c] = float("nan")
        else:
            sens[c] = (preds.argmax(1)[mask] == c).float().mean().item()
    return sens


def confusion_matrix(preds: torch.Tensor, labels: torch.Tensor) -> np.ndarray:
    cm = np.zeros((NUM_CLASSES, NUM_CLASSES), dtype=np.int64)
    p  = preds.argmax(1).cpu().numpy()
    l  = labels.cpu().numpy()
    for pi, li in zip(p, l):
        cm[li, pi] += 1
    return cm


def print_confusion_matrix(cm: np.ndarray) -> None:
    header = f"{'':12s}" + "".join(f"{n:>10s}" for n in CLASS_NAMES)
    print(header)
    for i, row in enumerate(cm):
        row_str = f"{CLASS_NAMES[i]:12s}" + "".join(f"{v:10d}" for v in row)
        total = row.sum()
        sens  = cm[i, i] / total if total > 0 else 0.0
        row_str += f"  sens={sens:.1%}"
        print(row_str)


def run_epoch(model, loader, criterion, optimizer, scheduler, device, train):
    model.train(train)
    total_loss, all_preds, all_labels = 0.0, [], []

    with torch.set_grad_enabled(train):
        for images, labels in loader:
            images = images.to(device, non_blocking=True)
            labels = labels.to(device, non_blocking=True)

            logits = model(images)
            loss = criterion(logits, labels)

            if train:
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
                optimizer.step()
                if scheduler is not None:
                    scheduler.step()

            total_loss += loss.item() * len(labels)
            all_preds.append(logits.detach().cpu())
            all_labels.append(labels.detach().cpu())

    all_preds = torch.cat(all_preds)
    all_labels = torch.cat(all_labels)
    avg_loss = total_loss / len(all_labels)
    acc = accuracy(all_preds, all_labels)
    sens = per_class_sensitivity(all_preds, all_labels)
    return avg_loss, acc, sens


def main() -> None:
    args = parse_args()

    if args.device:
        device = torch.device(args.device)
    elif torch.cuda.is_available():
        device = torch.device("cuda")
    elif torch.backends.mps.is_available():
        device = torch.device("mps")
    else:
        device = torch.device("cpu")
    print(f"Device: {device}")

    loaders = build_dataloaders(
        root=args.data_root,
        batch_size=args.batch_size,
        num_workers=args.num_workers,
        oversample_train=not args.no_oversample,
    )

    for split in ["train", "val", "test"]:
        dataset_samples = loaders[split].dataset.samples
        if len(dataset_samples) > 0:
            all_labels = [lbl for _, _, lbl in dataset_samples]
            low, high = min(all_labels), max(all_labels)
            print(f"[{split.upper()}] Label range: {low} to {high}")
            if high >= NUM_CLASSES or low < 0:
                print(f"error: {split} split has labels out of 0-{NUM_CLASSES-1} range")

    model = FallDetectorCNN(dropout_rate=args.dropout).to(device)
    n_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"FallDetectorCNN: trainable params: {n_params:,}")

    # weighted loss for classs imbalance
    class_weights = loaders["train"].dataset.class_weights().to(device)
    loss_weights = (1.0 / class_weights.clamp(min=1e-6))
    loss_weights = loss_weights / loss_weights.sum() * NUM_CLASSES
    criterion = nn.CrossEntropyLoss(weight=loss_weights)

    # optimizer and scheduler
    optimizer = AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    scheduler = OneCycleLR(
        optimizer,
        max_lr=args.lr,
        steps_per_epoch=len(loaders["train"]),
        epochs=args.epochs,
        pct_start=0.3,
    )

    save_dir = Path(args.save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    best_ckpt = save_dir / "best.pth"

    best_val_acc = 0.0
    patience_count = 0

    print(f"\n{'Epoch':>6} {'Train Loss':>12} {'Train Acc':>10} "
          f"{'Val Loss':>10} {'Val Acc':>10}  Lying-Sens")

    for epoch in range(1, args.epochs + 1):
        t0 = time.time()

        tr_loss, tr_acc, _ = run_epoch(model, loaders["train"], criterion, optimizer, scheduler, device, train=True)
        va_loss, va_acc, sens = run_epoch(model, loaders["val"], criterion, None, None, device, train=False)

        lying_sens = sens.get(3, float("nan"))
        elapsed = time.time() - t0

        print(f"{epoch:6d} {tr_loss:12.4f} {tr_acc:10.4f}  "
              f"{va_loss:10.4f} {va_acc:10.4f}  "
              f"{lying_sens:.2%} ({elapsed:.0f}s)")

        sens_str = "  ".join(
            f"{CLASS_NAMES[c][:4]}={sens[c]:.0%}" for c in range(NUM_CLASSES)
        )
        print(f"sens: {sens_str}")

        if va_acc > best_val_acc:
            best_val_acc = va_acc
            patience_count = 0
            torch.save({"epoch": epoch, "model_state": model.state_dict(), "val_acc": va_acc}, best_ckpt)
            print(f"Saved best model  (val_acc={va_acc:.4f})")
        else:
            patience_count += 1
            if patience_count >= args.patience:
                print(f"\nEarly stopping after {epoch} epochs.")
                break

    # test eval
    print("Loading best checkpoint for test evaluation")
    ckpt = torch.load(best_ckpt, map_location=device)
    model.load_state_dict(ckpt["model_state"])
    print(f"Best epoch: {ckpt['epoch']}  \nval_acc: {ckpt['val_acc']:.4f}")

    te_loss, te_acc, te_sens = run_epoch(model, loaders["test"], criterion, None,  None, device, train=False)

    print(f"\nTest Loss: {te_loss:.4f}  |  Test Accuracy: {te_acc:.4f} ({te_acc*100:.1f}%)")
    print(f"Lying sensitivity: {te_sens[3]:.2%}")

    all_preds, all_labels = [], []
    model.eval()
    with torch.no_grad():
        for images, labels in loaders["test"]:
            logits = model(images.to(device))
            all_preds.append(logits.cpu())
            all_labels.append(labels.cpu())

    cm = confusion_matrix(torch.cat(all_preds), torch.cat(all_labels))
    print(f"\nConfusion matrix (rows=true, cols=predicted):")
    print_confusion_matrix(cm)


if __name__ == "__main__":
    main()