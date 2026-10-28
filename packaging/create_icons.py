"""Generate matching Windows and macOS app icons."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

root = Path(__file__).resolve().parent
size = 1024
image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((28, 28, 996, 996), radius=158, fill='#315f9a')
fonts = [
    Path('C:/Windows/Fonts/msyhbd.ttc'),
    Path('/System/Library/Fonts/PingFang.ttc'),
    Path('/System/Library/Fonts/Supplemental/Arial Unicode.ttf'),
]
font_path = next((path for path in fonts if path.is_file()), None)
if font_path is None:
    raise SystemExit('A CJK font is required to generate the app icon.')
font = ImageFont.truetype(str(font_path), 630)
draw.text((size / 2, size / 2 - 20), '文', fill='white', font=font, anchor='mm')
image.save(root / 'Wenshu.ico', sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
image.save(root / 'Wenshu.icns', format='ICNS')
