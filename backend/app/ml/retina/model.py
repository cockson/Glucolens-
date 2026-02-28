import torch
import torch.nn as nn
import torchvision.models as models

def build_retina_model(num_classes: int = 2):
    model = models.resnet18(weights=models.ResNet18_Weights.DEFAULT)
    in_features = model.fc.in_features
    model.fc = nn.Linear(in_features, num_classes)
    return model

class TemperatureScaler(nn.Module):
    """
    Post-hoc calibration: temperature scaling on logits.
    """
    def __init__(self):
        super().__init__()
        self.temperature = nn.Parameter(torch.ones(1) * 1.0)

    def forward(self, logits):
        t = torch.clamp(self.temperature, 0.05, 10.0)
        return logits / t