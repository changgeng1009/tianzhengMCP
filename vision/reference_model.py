from __future__ import annotations

from vision.models import ReferenceModel
from vision.provider import ImageInput, VisionProvider


class ReferenceModelBuilder:
    """从参考图片构建 Reference Model。"""

    def __init__(self, provider: VisionProvider) -> None:
        self.provider = provider

    def build_from_image(self, image: ImageInput) -> ReferenceModel:
        payload = self.provider.analyze_image(image)
        return ReferenceModel.from_dict(payload)
