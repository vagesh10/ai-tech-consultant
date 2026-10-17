
import pytesseract
from PIL import Image, ImageDraw

pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

# Create a temporary test image containing readable text.
image = Image.new("RGB", (700, 160), "white")
draw = ImageDraw.Draw(image)
draw.text(
    (20, 40),
    "Payment Settings - Configure Gateway",
    fill="black",
)

text = pytesseract.image_to_string(image)

print("Extracted text:")
print(text.strip())

assert "Payment Settings" in text
print("OCR test passed!")
