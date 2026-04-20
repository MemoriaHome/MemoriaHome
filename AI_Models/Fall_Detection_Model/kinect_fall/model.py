import torch
import torch.nn as nn

NUM_CLASSES = 6

# groups 3 standard ops into one reusable unit
class ConvBnRelu(nn.Sequential):
    def __init__(self, in_ch: int, out_ch: int, kernel: int = 3, stride: int = 1, padding: int = 1):
        super().__init__(
            nn.Conv2d(in_ch, out_ch, kernel, stride=stride, padding=padding, bias=False), # filters to find patterns
            nn.BatchNorm2d(out_ch), 
            nn.ReLU(inplace=True), # turns all neg numbers to zero for non-linearity, helps model understand complex shapes like the human body
        )

# stacks building blocks (above class) to create the model
class FallDetectorCNN(nn.Module):
    def __init__(self, in_channels:  int = 4, num_classes:  int = NUM_CLASSES, dropout_rate: float = 0.5):
        super().__init__()

        # these layers look at the image and extracts info
        # nn.MaxPool2d halves the h and w of the image (reduces resolution but increases depth)
        # for ex: layer 1 might see a finger and layer 2 might see the whole hand
        self.c1 = nn.Sequential(ConvBnRelu(in_channels, 16, kernel=3, padding=1), nn.MaxPool2d(2, 2),)
        self.c2 = nn.Sequential(ConvBnRelu(16, 32, kernel=3, padding=1), nn.MaxPool2d(2, 2),)

        flat = 32 * 39 * 27

        self.classifier = nn.Sequential(
            nn.Flatten(), # turns 2d grid of features into long list of num
            nn.Linear(flat, 4096), # takes all features found by cnn and votes for which class it belongds to
            nn.ReLU(inplace=True),
            nn.Dropout(dropout_rate), # randomly turns off neurons during training to prevent overfitting, so that the model doesnt rely on one specifc trick to identify a fall
            nn.Linear(4096, num_classes),
        )

        self._init_weights()

    # the model's weight at the start is just random num 
    # if the nums are all the same the model learns nothing
    # if they are too big the model will crash
    def _init_weights(self) -> None:
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, mode="fan_out", nonlinearity="relu")
            elif isinstance(m, nn.BatchNorm2d):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias,   0)
            elif isinstance(m, nn.Linear):
                nn.init.xavier_normal_(m.weight)
                nn.init.constant_(m.bias, 0)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.c1(x) # input
        x = self.c2(x) # result
        return self.classifier(x) # final features flattened and classified (scores for each class)


if __name__ == "__main__":
    m = FallDetectorCNN()
    x = torch.randn(2, 4, 156, 108)
    y = m(x)
    n_params = sum(p.numel() for p in m.parameters() if p.requires_grad)
    print(f"output={tuple(y.shape)}  params={n_params:,}")