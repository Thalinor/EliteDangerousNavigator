# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Original procedural wireframe renderer for Docking Navigator.

RGBA coverage antialiasing and PNG encoding use only Python's standard library.
No sprites, screenshots, upstream visual assets, dithering or game telemetry.
Models are schematic references; camera angles are controlled by the user.
"""
import math
import struct
import zlib
from .core import carrier_boxes, starport_position, valid_pad


class Raster:
    def __init__(self, width, height):
        self.width, self.height = int(width), int(height)
        self.pixels = bytearray(self.width * self.height * 4)

    def plot(self, x, y, colour, coverage=1):
        x, y = int(x), int(y)
        if not (0 <= x < self.width and 0 <= y < self.height):
            return
        source = min(1, max(0, coverage)) * colour[3] / 255
        if source <= 0:
            return
        i = (y*self.width+x)*4
        old = self.pixels[i+3] / 255
        alpha = source + old*(1-source)
        for channel in range(3):
            self.pixels[i+channel] = round((colour[channel]*source + self.pixels[i+channel]*old*(1-source))/alpha)
        self.pixels[i+3] = round(alpha*255)

    def line(self, start, end, colour, width=1):
        """Xiaolin Wu coverage, with parallel strokes for thicker highlights."""
        x0, y0 = start; x1, y1 = end
        length = math.hypot(x1-x0, y1-y0)
        if length < .001:
            return
        count = max(1, math.ceil(width))
        for offset in range(count):
            distance = offset-(count-1)/2
            dx, dy = -(y1-y0)/length*distance, (x1-x0)/length*distance
            self._thin_line(x0+dx, y0+dy, x1+dx, y1+dy, colour)

    def _thin_line(self, x0, y0, x1, y1, colour):
        steep = abs(y1-y0) > abs(x1-x0)
        if steep:
            x0, y0, x1, y1 = y0, x0, y1, x1
        if x0 > x1:
            x0, y0, x1, y1 = x1, y1, x0, y0
        gradient = (y1-y0)/(x1-x0) if x1 != x0 else 0
        for x in range(math.floor(x0), math.ceil(x1)+1):
            y = y0 + gradient*(x-x0)
            base = math.floor(y)
            fraction = y-base
            extent = max(0, min(x+1, x1+.5)-max(x, x0-.5))
            for yy, amount in ((base, 1-fraction), (base+1, fraction)):
                self.plot(yy if steep else x, x if steep else yy, colour, amount*extent)

    def polygon(self, points, colour):
        # The transparent fill is restrained; outlines are antialiased separately.
        for y in range(max(0, math.ceil(min(p[1] for p in points))), min(self.height, math.ceil(max(p[1] for p in points)))):
            hits = []
            for a, b in zip(points, points[1:]+points[:1]):
                if min(a[1], b[1]) <= y+.5 < max(a[1], b[1]):
                    hits.append(a[0]+(y+.5-a[1])*(b[0]-a[0])/(b[1]-a[1]))
            hits.sort()
            for left, right in zip(hits[::2], hits[1::2]):
                for x in range(max(0, math.floor(left)), min(self.width, math.ceil(right))):
                    self.plot(x, y, colour, max(0, min(x+1, right)-max(x, left)))

    def png(self):
        def chunk(tag, data):
            return struct.pack('>I', len(data))+tag+data+struct.pack('>I', zlib.crc32(tag+data)&0xffffffff)
        rows = b''.join(b'\0'+self.pixels[y*self.width*4:(y+1)*self.width*4] for y in range(self.height))
        return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('>IIBBBBB', self.width, self.height, 8, 6, 0, 0, 0))
                +chunk(b'IDAT', zlib.compress(rows, 6))+chunk(b'IEND', b''))


class Scene:
    def __init__(self):
        self.lines = []
        self.faces = []
        self.has_slot = False
        self.has_pad = False

    def wire(self, points, colour='wire', closed=False, width=1):
        for a, b in zip(points, points[1:]+points[:1] if closed else points[1:]):
            self.lines.append((a, b, colour, width))

    def face(self, points, colour):
        self.faces.append((points, colour))
        self.wire(points, colour, True, 2)


def circle(z, radius=1, count=48, axis='z'):
    points = []
    for n in range(count):
        angle = n/count*math.tau
        x, y = radius*math.cos(angle), radius*math.sin(angle)
        points.append((x, y, z) if axis == 'z' else (x, z, y))
    return points


def _slot(scene, z=1.02, half=.38, reverse=False):
    slot = [(-half, -.095, z), (half, -.095, z), (half, .095, z), (-half, .095, z)]
    scene.face(slot, 'slot')
    scene.wire([(-half-.06, 0, z), (-half-.06, .15, z), (-half+.08, .15, z)], 'green' if reverse else 'red', width=2)
    scene.wire([(half+.06, 0, z), (half+.06, .15, z), (half-.08, .15, z)], 'red' if reverse else 'green', width=2)
    # This is an entrance marker attached to the model, never a ship bearing.
    scene.wire([(0, .58, z), (0, .22, z)], 'slot', width=2)
    scene.wire([(-.10, .32, z), (0, .22, z), (.10, .32, z)], 'slot', width=2)
    scene.has_slot = True


def exterior(station_type='Coriolis', reverse=False):
    scene = Scene()
    kind = str(station_type).casefold()
    if kind in {'orbis'}:
        for z, radius in ((-.6, 1.1), (-.38, 1.1), (-1.1, .28), (1.35, .28)):
            scene.wire(circle(z, radius), closed=True)
        for n in range(8):
            angle = n/8*math.tau
            x, y = math.cos(angle), math.sin(angle)
            scene.wire([(x*1.1, y*1.1, -.6), (x*1.1, y*1.1, -.38)])
            scene.wire([(x*.28, y*.28, -.38), (x*1.1, y*1.1, -.38)])
            scene.wire([(x*.28, y*.28, -1.1), (x*.28, y*.28, 1.35)], 'dim')
        _slot(scene, 1.38, .21, reverse)
    elif kind in {'ocellus', 'bernal'}:
        for z in (-.85, -.5, 0, .5, .85):
            scene.wire(circle(z, math.sqrt(1-z*z)), closed=True)
        for angle in range(0, 180, 30):
            a = math.radians(angle)
            scene.wire([(math.cos(t)*math.cos(a), math.cos(t)*math.sin(a), math.sin(t))
                        for t in [i/64*math.tau for i in range(64)]], closed=True)
        _slot(scene, reverse=reverse)
    else:
        # Original cuboctahedral schematic for Coriolis; other polygonal types
        # intentionally use this labelled generic reference, not false assets.
        vertices = sorted({(x, y, z) for x in (-1, 0, 1) for y in (-1, 0, 1)
                           for z in (-1, 0, 1) if x*x+y*y+z*z == 2})
        for i, a in enumerate(vertices):
            for b in vertices[i+1:]:
                if sum((u-v)**2 for u, v in zip(a, b)) == 2:
                    scene.wire([a, b])
        _slot(scene, reverse=reverse)
    return scene


def interior(pad, reverse=False):
    scene = Scene()
    for z in (-1.05, -.35, .35, 1.05):
        scene.wire(circle(z, count=12), 'dim', True)
    for n in range(12):
        angle = math.radians(15+n*30)
        x, y = math.cos(angle), math.sin(angle)
        scene.wire([(x, y, -1.05), (x, y, 1.05)])
    if valid_pad(pad, 'starport') is not None:
        _, _, sector, ring = starport_position(pad, reverse)
        angle = math.radians(-90-sector*30)
        z = (.72, 0, -.72)[ring]
        patch = [(math.cos(angle+d)*.98, math.sin(angle+d)*.98, zz)
                 for d, zz in ((-.13, z-.22), (.13, z-.22), (.13, z+.22), (-.13, z+.22))]
        scene.face(patch, 'pad')
        scene.has_pad = True
    _slot(scene, 1.10, reverse=reverse)
    return scene


def carrier(layout, pad=None, reverse=False):
    scene = Scene()
    half = 1.58 if layout == 'squadron' else .78
    top = [(-half, 0, -1.24), (half, 0, -1.24), (half, 0, 1.24), (-half, 0, 1.24)]
    bottom = [(x*.92, -.22, z*.96) for x, _, z in top]
    scene.wire(top, closed=True)
    scene.wire(bottom, 'dim', True)
    for a, b in zip(top, bottom):
        scene.wire([a, b], 'dim')
    for number, (x1, y1, x2, y2) in enumerate(carrier_boxes(layout, reverse), 1):
        patch = [(x1/32, .025, y1/32), (x2/32, .025, y1/32), (x2/32, .025, y2/32), (x1/32, .025, y2/32)]
        if number == pad:
            scene.face(patch, 'pad'); scene.has_pad = True
        else:
            scene.wire(patch, 'dim', True)
    return scene


def interior_flat(pad, reverse=False):
    """Depth tiers become explicit reference rings in 2D, not overlapping bays."""
    scene = Scene()
    radii = (.9, .68, .46)
    for radius in (1.03, *radii, .28):
        scene.wire(circle(0, radius, count=96), 'dim' if radius == 1.03 else 'wire', True)
    for sector in range(12):
        angle = math.radians(-75-sector*30)
        scene.wire([(math.cos(angle)*.28, math.sin(angle)*.28, 0),
                    (math.cos(angle)*1.03, math.sin(angle)*1.03, 0)], 'dim')
    if valid_pad(pad, 'starport') is not None:
        _, _, sector, ring = starport_position(pad, reverse)
        angle = math.radians(-90-sector*30)
        radius = radii[ring]
        scene.face([(math.cos(angle+d)*r, math.sin(angle+d)*r, 0)
                    for d, r in ((-.13, radius-.065), (.13, radius-.065),
                                 (.13, radius+.065), (-.13, radius+.065))], 'pad')
        scene.has_pad = True
    _slot(scene, .05, .20, reverse)
    return scene


def project(point, width, height, yaw=28, pitch=-18, perspective=True, zoom=1):
    x, y, z = point
    a, b = math.radians(yaw), math.radians(pitch)
    x, z = x*math.cos(a)+z*math.sin(a), -x*math.sin(a)+z*math.cos(a)
    y, z = y*math.cos(b)-z*math.sin(b), y*math.sin(b)+z*math.cos(b)
    distance = 5/(5-z) if perspective else 1
    scale = min(width, height)*.29*zoom
    return width/2+x*scale*distance, height/2-y*scale*distance, z


def render_scene(scene, width, height, yaw=28, pitch=-18, perspective=True, zoom=1, dark=True):
    raster = Raster(width, height)
    palette = {'wire': (101, 212, 232, 215) if dark else (20, 103, 124, 220),
               'dim': (101, 176, 197, 65) if dark else (45, 104, 123, 85),
               'slot': (255, 163, 48, 245), 'pad': (255, 151, 27, 245),
               'green': (40, 230, 139, 240), 'red': (244, 77, 100, 240)}
    def transform(p): return project(p, width, height, yaw, pitch, perspective, zoom)
    # Rear-to-front wire ordering gives a depth cue without opaque station faces.
    lines = sorted(scene.lines, key=lambda line: (transform(line[0])[2]+transform(line[1])[2])/2)
    for a, b, colour, weight in lines:
        p, q = transform(a), transform(b)
        rgba = palette[colour]
        if colour == 'wire':
            fade = max(.3, min(1, .65+(p[2]+q[2])/8))
            rgba = (*rgba[:3], round(rgba[3]*fade))
        raster.line(p[:2], q[:2], rgba, weight)
    for points, colour in scene.faces:
        projected = [transform(p)[:2] for p in points]
        rgba = palette[colour]
        raster.polygon(projected, (*rgba[:3], 78))
        for a, b in zip(projected, projected[1:]+projected[:1]):
            raster.line(a, b, rgba, 2)
    return raster
