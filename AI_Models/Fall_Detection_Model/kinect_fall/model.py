import torch
import torch.nn as nn

NUM_CLASSES = 5

# reusable building block that chains 3 operations togetehr
# 1. extracts features
# 2. batch normalization
# 3. relu
class ConvBnRelu(nn.Sequential):
    def __init__(self, in_ch: int, out_ch: int, kernel: int = 3, stride: int = 1, padding: int = 1):
        super().__init__(
            nn.Conv2d(in_ch, out_ch, kernel, stride=stride, padding=padding, bias=False),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
        )

# processes the input through two convolutions then adds og input back
class ResBlock(nn.Module):
    def __init__(self, channels: int, dropout_rate: float = 0.1):
        super().__init__()
        self.block = nn.Sequential(
            ConvBnRelu(channels, channels),
            nn.Dropout2d(dropout_rate), # prevents overfitting
            nn.Conv2d(channels, channels, 3, padding=1, bias=False),
            nn.BatchNorm2d(channels),
        )
        self.relu = nn.ReLU(inplace=True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.relu(x + self.block(x))

# learns depth specific features (body shape and distance from camera) through two conv layers before fusing with rgb
class DepthBranch(nn.Module):
    def __init__(self, out_ch: int = 16):
        super().__init__()
        self.stem = nn.Sequential(
            ConvBnRelu(1, 8, kernel=3, padding=1),
            ConvBnRelu(8, out_ch, kernel=3, padding=1),
        )

    def forward(self, depth: torch.Tensor) -> torch.Tensor:
        return self.stem(depth)

# main model
class FallDetectorCNN(nn.Module):
    def __init__(self, in_channels: int = 4, num_classes: int = NUM_CLASSES, dropout_rate: float = 0.5):
        super().__init__()

        self.depth_branch = DepthBranch(out_ch=16)

        self.rgb_stem = nn.Sequential(
            ConvBnRelu(3, 16, kernel=3, padding=1),
            ConvBnRelu(16, 32, kernel=3, padding=1),
        )

        fused_ch = 48

        # input is 156x108 (crop size from paper), each stage halves both numbers

        # learns low level features (edges and silhouettes)
        self.stage1 = nn.Sequential(
            ConvBnRelu(fused_ch, 64, kernel=3, padding=1),
            ResBlock(64, dropout_rate=0.1),
            nn.MaxPool2d(2, 2), # 156x108 / 2 = 78x54
        )

        # learns mid level features (limb shapes and body parts)
        self.stage2 = nn.Sequential(
            ConvBnRelu(64, 128, kernel=3, padding=1),
            ResBlock(128, dropout_rate=0.1),
            ResBlock(128, dropout_rate=0.1),
            nn.MaxPool2d(2, 2), # 78x54 / 2 = 39x27
        )

        # learns high level features (overall body pose and orientation)
        self.stage3 = nn.Sequential(
            ConvBnRelu(128, 256, kernel=3, padding=1),
            ResBlock(256, dropout_rate=0.15),
            nn.MaxPool2d(2, 2), # 39x27 / 2 = 20x14
        )

        # collapses 20x14 down to a single value per channel to give it a 256 element vector
        # better than flattening it bc it forces each of the 256 channels to represent meaningful features
        # instead of just memorizing where in the image a pose tends to appear
        self.gap = nn.AdaptiveAvgPool2d(1)

        # maps to 5 class scores
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(256, 256),
            nn.ReLU(inplace=True),
            nn.Dropout(dropout_rate),
            nn.Linear(256, 128),
            nn.ReLU(inplace=True),
            nn.Dropout(dropout_rate * 0.6),  # randomly disables neurons during training to prevent overfitting
            nn.Linear(128, num_classes),
        )

        self._init_weights()

    def _init_weights(self) -> None:
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, mode="fan_out", nonlinearity="relu")
            elif isinstance(m, nn.BatchNorm2d):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)
            elif isinstance(m, nn.Linear):
                nn.init.xavier_normal_(m.weight)
                nn.init.constant_(m.bias, 0)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        rgb = x[:, :3, :, :]   # first 3 channels
        depth = x[:, 3:, :, :] # last channel

        rgb_feat = self.rgb_stem(rgb)
        depth_feat = self.depth_branch(depth)

        # fuse by concatenation along channel dim
        fused = torch.cat([rgb_feat, depth_feat], dim=1) 

        out = self.stage1(fused)
        out = self.stage2(out)
        out = self.stage3(out)
        out = self.gap(out)

        return self.classifier(out)


if __name__ == "__main__":
    m = FallDetectorCNN()
    x = torch.randn(2, 4, 156, 108)
    y = m(x)
    n_params = sum(p.numel() for p in m.parameters() if p.requires_grad)
    print(f"output={tuple(y.shape)}  params={n_params:,}")