import torch
import torch.nn.functional as F
import numpy as np
import cv2

class GradCAM:
    """
    Grad-CAM for CNN models. Works well with ResNet family.
    target_layer: usually model.layer4[-1]
    """
    def __init__(self, model, target_layer):
        self.model = model
        self.target_layer = target_layer
        self.gradients = None
        self.activations = None
        self._register_hooks()

    def _register_hooks(self):
        def forward_hook(_, __, output):
            self.activations = output.detach()

        def backward_hook(_, grad_in, grad_out):
            self.gradients = grad_out[0].detach()

        self.target_layer.register_forward_hook(forward_hook)
        self.target_layer.register_full_backward_hook(backward_hook)

    def generate(self, input_tensor, class_idx: int):
        self.model.zero_grad()
        logits = self.model(input_tensor)
        score = logits[:, class_idx].sum()
        score.backward(retain_graph=True)

        grads = self.gradients  # [B, C, H, W]
        acts = self.activations # [B, C, H, W]

        weights = grads.mean(dim=(2,3), keepdim=True)  # [B, C, 1, 1]
        cam = (weights * acts).sum(dim=1, keepdim=False)  # [B, H, W]
        cam = F.relu(cam)

        cam = cam[0].cpu().numpy()
        cam = (cam - cam.min()) / (cam.max() - cam.min() + 1e-8)
        return cam

def overlay_cam_on_image(rgb_img_uint8, cam, alpha=0.45):
    """
    rgb_img_uint8: HxWx3 uint8
    cam: HxW float 0..1
    returns overlay RGB uint8
    """
    h, w = rgb_img_uint8.shape[:2]
    cam_resized = cv2.resize(cam, (w, h))
    heatmap = cv2.applyColorMap(np.uint8(255 * cam_resized), cv2.COLORMAP_JET)
    heatmap = cv2.cvtColor(heatmap, cv2.COLOR_BGR2RGB)

    overlay = (alpha * heatmap + (1 - alpha) * rgb_img_uint8).clip(0,255).astype(np.uint8)
    return overlay