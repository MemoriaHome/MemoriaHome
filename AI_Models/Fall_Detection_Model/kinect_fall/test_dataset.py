from dataset import FallDataset

ds = FallDataset('./data', split='train')
img, label = ds[0]
print('Image shape:', img.shape)
print('Label:', label)