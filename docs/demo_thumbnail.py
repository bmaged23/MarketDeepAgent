"""Create a clickable README video preview from the real recording poster.

The SVG embeds the unmodified PNG and draws a play affordance inside its lower
left corner. GitHub README previews link to the hosted native video player.
"""
import base64
import struct
from pathlib import Path

ASSETS = Path(__file__).resolve().parent / 'assets'


def generate():
    poster = (ASSETS / 'storefront-poster.png').read_bytes()
    if poster[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('Demo poster must be a PNG')
    width, height = struct.unpack('>II', poster[16:24])
    image = base64.b64encode(poster).decode('ascii')
    bar = 64
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
<title id="title">Play the MarketDeepAgent customer demo</title>
<desc id="desc">Real storefront and AI assistant preview. Play button inside the bottom-left of the video. Click to open the hosted video player.</desc>
<image width="{width}" height="{height}" xlink:href="data:image/png;base64,{image}"/>
<rect y="{height-bar}" width="{width}" height="{bar}" fill="#091323" fill-opacity=".95"/>
<path d="M 28 {height-46} L 28 {height-18} L 52 {height-32} Z" fill="#6af5d3"/>
<text x="75" y="{height-26}" font-family="Arial,sans-serif" font-size="19" fill="#f0f6ff">Play demo</text>
<text x="208" y="{height-26}" font-family="Arial,sans-serif" font-size="16" fill="#b4c6dd">0:00 / 5:52</text>
<rect x="325" y="{height-34}" width="{width-470}" height="4" rx="2" fill="#52677d"/>
<text x="{width-110}" y="{height-26}" font-family="Arial,sans-serif" font-size="15" fill="#b4c6dd">Watch ↗</text>
</svg>'''
    (ASSETS / 'demo-preview.svg').write_text(svg)


if __name__ == '__main__':
    generate()
