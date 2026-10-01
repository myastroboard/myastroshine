"""CPU compatibility smoke test, run inside the image by scripts/check_cpu_compat.sh.

Imports the app (which pulls in every dependency it uses) and drives the hot
paths of the compiled libraries: the enhancement pipeline (NumPy, OpenCV, the
starlet transforms), FITS and 16-bit decoding, linear ingest, the stacking star
detection, Pillow. On a CPU missing an instruction a wheel was built for, the
process dies with SIGILL - there is nothing to assert here beyond reaching the end.
"""

import io
import os
import sys

sys.path.insert(0, "/app")
os.environ.setdefault("APP_ENV", "test")  # no log file, no background services

import app.main  # noqa: F401 - the import chain uvicorn runs
import cv2
import numpy as np
import rawpy  # noqa: F401 - LibRaw's native module loads on import
from app.models import ProcessingParameters
from app.services.image_processing import ImageProcessingService
from app.services.star_detection import StarDetectionService
from app.utils.image_utils import decode_image
from app.utils.linear_ingest import ingest_frame
from astropy.io import fits
from PIL import Image

rng = np.random.default_rng(0)
image = (rng.random((256, 384, 3)) * 255).astype(np.uint8)
for _ in range(60):
    y, x = int(rng.integers(8, 248)), int(rng.integers(8, 376))
    cv2.circle(image, (x, y), int(rng.integers(1, 4)), (250, 250, 250), -1)
image = cv2.GaussianBlur(image, (3, 3), 0)

params = ProcessingParameters(
    contrast=1.4,
    saturation=1.2,
    denoise=40,
    chroma_denoise=30,
    sharpness=1.6,
    clarity=0.4,
    dehaze=20,
    star_reduction=30,
)
ImageProcessingService().apply_parameters(image, params)

StarDetectionService().detect(image, sensitivity=50, max_size=10)

warp = cv2.getRotationMatrix2D((192, 128), 3.0, 1.0)
cv2.warpAffine(image, warp, (384, 256))
cv2.resize(image, (128, 96), interpolation=cv2.INTER_AREA)
ok, png16 = cv2.imencode(".png", (image.astype(np.uint16) * 257))
if not ok:
    raise SystemExit("cv2.imencode failed")
decode_image(png16.tobytes(), "frame.png")

buffer = io.BytesIO()
fits.PrimaryHDU((rng.random((64, 96)) * 60000).astype(np.uint16)).writeto(buffer)
ingest_frame(buffer.getvalue(), "light.fits")

Image.fromarray(image).resize((64, 64)).save(io.BytesIO(), format="JPEG")

print("cpu-compat smoke test: OK")
