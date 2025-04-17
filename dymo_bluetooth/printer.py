# MIT License
# 
# Copyright (c) 2024 ysfchn / Yusuf Cihan
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from enum import Enum
from io import SEEK_END, BytesIO
from typing import Literal, Sequence, Tuple
import math

class DirectiveCommand(Enum):
    """
    Directives that accepted by the printer.
    """
    START = "s"
    MEDIA_TYPE = "M"
    PRINT_DENSITY = "C" # Unused
    PRINT_DATA = "D"
    FORM_FEED = "E"
    STATUS = "A"
    END = "Q"

    def to_bytes(self) -> bytes:
        # 27 = ASCII escape sequence
        return bytes((27, ord(self.value), ))


class Result(Enum):

    # Printing has been completed (supposedly). This may not always mean that a 
    # label has been printed out from the printer. See FAILED_NO_CASETTE status
    # below for details.
    SUCCESS = 0

    # PRINTING (or SUCCESS) is 1

    # Print failed due to some unknown reason.
    FAILED = 2

    # Printing has been completed but battery is low.
    SUCCESS_LOW_BATTERY = 3

    # Print failed due to being cancelled.
    FAILED_CANCEL = 4

    # FAILED (with a different status value) is 5

    # Print failed due to the low batteries.
    FAILED_LOW_BATTERY = 6 

    # Failed due to casette not inserted. On my tests, printer never sends this
    # status, instead it will spin its gear even casette is not inserted, and
    # will send a SUCCESS status instead, so there is no way to check if
    # casette is actually inserted.
    FAILED_NO_CASETTE = 7

    @classmethod
    def from_bytes(cls, data: Sequence[int]):
        if data[0] != 27:
            raise ValueError("Not a valid result value; 1st byte must be 0x1b (27)")
        if chr(data[1]) != "R":
            raise ValueError("Not a valid result value; 2nd byte must be 0x52 (82)")
        # There is a value 5, which also means printing has completed but has
        # a different status value, so we return FAILED since that's what it means.
        if data[2] == 5:
            return cls(Result.FAILED.value)
        # There is a value 1, which also means printing has completed but has
        # a different status value, so we return SUCCESS since that's what it means.
        if data[2] == 1:
            return cls(Result.SUCCESS.value)
        return cls(data[2])


class Canvas:
    """
    An implementation of 1-bit monochrome horizontal images, sequentially 
    ordered and stored in big-endian for each pixel.

    1 byte equals 8 bits, and each bit specifies if pixel should be filled
    (= 1) or not (= 0).
    """

    __slots__ = ("buffer", )

    # Each line takes 4 bytes, equals to 32 pixels (1 byte = 8 bits).
    BYTES_PER_LINE = 4

    # Maximum count of bytes that the image can extend into the fixed direction.
    MAX_LENGTH = 1024

    def __init__(self) -> None:
        self.buffer = BytesIO()

    def get_pixel(self, x: int, y: int) -> bool:
        """
        Gets the pixel in given coordinates. 
        Returns True if pixel is filled (= black), otherwise False.
        """
        self._raise_if_out_bounds(x, y)

        # Get the byte containing the pixel value of given coordinates.
        x_offset = x * Canvas.BYTES_PER_LINE
        y_offset = Canvas.BYTES_PER_LINE - 1 - math.floor(y / 8)
        self.buffer.seek(x_offset + y_offset)

        # Check if there is a bit value in given line.
        value = (self.buffer.read(1) or b"\x00")[0]
        is_black = bool(value & (1 << (7 - (y % 8))))
        return is_black

    def set_pixel(self, x: int, y: int, color: Literal[True, False, 0, 1]) -> None:
        """
        Sets a pixel to given coordinates.
        Setting color to True will paint a black color.
        """
        self._raise_if_out_bounds(x, y)

        # Get the byte containing the pixel value of given coordinates.
        x_offset = x * Canvas.BYTES_PER_LINE
        y_offset = Canvas.BYTES_PER_LINE - 1 - math.floor(y / 8)
        self.buffer.seek(x_offset + y_offset)

        # Get the one of four slices in line in the given coordinates. Add the bit in
        # given location if color is black, otherwise exclude the bit to make it white.
        curr = self.buffer.read(1)
        value = (curr or b"\x00")[0]
        if color:
            value = value | (1 << (7 - (y % 8)))
        else:
            value = value & ~(1 << (7 - (y % 8)))

        # Change the current byte with modified one, if not exists, append a new one.
        self.buffer.seek(0 if not curr else -1, 1)
        self.buffer.write(bytes([value]))

    def stretch(self, factor: int = 2) -> "Canvas":
        """
        Stretches image to the non-fixed direction in N times, and returns a new
        Canvas containing the stretched image. Factor 1 results in the same image.
        """
        if factor < 1:
            raise ValueError("Stretch factor must be at least 1!")
        canvas = Canvas()
        for x in range(self.width):
            for y in range(self.height):
                pixel = self.get_pixel(x, y)
                start_x = (x * factor)
                for i in range(factor):
                    canvas.set_pixel(start_x + i, y, pixel)
        return canvas

    def _get_byte_size(self):
        self.buffer.seek(0, SEEK_END)
        return self.buffer.tell()

    def _get_unfixed_pixels(self):
        return math.ceil(self._get_byte_size() / self.BYTES_PER_LINE)

    def _get_fixed_pixels(self):
        return self.BYTES_PER_LINE * 8

    def _raise_if_out_bounds(self, x: int, y: int):
        if (x < 0) or (y < 0):
            raise ValueError("Canvas positions can't be negative.")
        bits = Canvas.BYTES_PER_LINE * 8
        maxbits = Canvas.MAX_LENGTH * 8
        if y >= bits:
            raise ValueError(f"Canvas can't be or exceed {bits} pixels in height.")
        elif x >= maxbits:
            raise ValueError(f"Canvas can't be or exceed {maxbits} pixels in width.")

    @property
    def height(self) -> int:
        """
        Gets the height of the image.
        """
        return self._get_fixed_pixels()

    @property
    def width(self) -> int:
        """
        Gets the width of the image.
        """
        return self._get_unfixed_pixels()

    @property
    def size(self) -> Tuple[int, int]:
        """
        Gets the width and height of the image in tuple.
        """
        return (self.width, self.height, )

    def get_image(self) -> bytes:
        """
        Gets the created image with added blank padding.
        """
        self.buffer.seek(0)
        image = self.buffer.read()
        return image + (b"\x00" * (self.buffer.tell() % self.BYTES_PER_LINE))

    def empty(self):
        """
        Makes all pixels in the canvas in blank (= white). Canvas size won't be changed.
        """
        size = self._get_byte_size()
        self.buffer.seek(0)
        self.buffer.truncate(0)
        self.buffer.seek(size)
        self.buffer.write(b"\x00")

    def copy(self) -> "Canvas":
        """
        Creates a copy of this canvas.
        """
        canvas = Canvas()
        self.buffer.seek(0)
        canvas.buffer.write(self.buffer.read())
        return canvas

    def clear(self):
        """
        Clears the canvas. Canvas size will be changed to 0.
        """
        self.buffer.seek(0)
        self.buffer.truncate(0)

    def revert(self):
        """
        Returns a new Canvas with the image is flipped in color; all unfilled 
        pixels are filled, and all filled pixels are unfilled.
        """
        self.buffer.seek(0)
        copied = Canvas()
        copied.buffer.seek(0)
        while (byt := self.buffer.read(1)):
            copied.buffer.write(bytes([byt[0] ^ 0xFF]))
        return copied

    def fill(self, to_left: int, to_right: int) -> "Canvas":
        """
        Returns a new Canvas with blank (= white) spacing added to both sides.
        """
        canv = Canvas()
        canv.buffer.seek(0)
        canv.buffer.write(bytes(to_left * self.BYTES_PER_LINE))
        canv.buffer.write(self.get_image())
        canv.buffer.seek(0, SEEK_END)
        canv.buffer.write(bytes(to_right * self.BYTES_PER_LINE))
        return canv

    def pad(self, until: int) -> "Canvas":
        """
        Adds blank (= white) spacing to both sides of the image, until the image reaches 
        to the given width in pixels. Returns a new Canvas containing the modified image.
        If image is already longer than given width, returns the copy of the same image.
        """
        if self.width >= until:
            return self.copy()
        side = math.ceil((until - self.width) / 2)
        return self.fill(side, side)

    def text(self, in_quad: bool = True, blank_char: int = 0x20, frame: bool = True) -> str:
        """
        Converts the image to a string of unicode block symbols, so it can be printed
        out to the terminal. If `in_quad` is True, quarter block characters will be used,
        so the image will be 2 times smaller, making each 4 pixel to take up a single
        character. Empty pixels will be represented as `blank_char` (default is SPACE).
        """
        lines = []
        frame_length = 0
        if frame:
            frame_length = self.width if not in_quad else math.ceil(self.width / 2)
        if frame_length:
            lines.append(chr(0x250C) + (frame_length * chr(0x2500)) + chr(0x2510))
        if in_quad:
            for h in range(0, self.height, 2):
                line = ""
                for w in range(0, self.width, 2):
                    corners = \
                        self.get_pixel(w, h), \
                        self.get_pixel(w + 1, h), \
                        self.get_pixel(w, h + 1), \
                        self.get_pixel(w + 1, h + 1)
                    corners = sum([1 << x if corners[x] else 0 for x in range(4)])
                    line += chr(quartet_to_char(corners) or blank_char)
                if frame:
                    line = chr(0x2502) + line + chr(0x2502)
                lines.append(line)
        else:
            lines = []
            for h in range(0, self.height):
                line = ""
                for w in range(0, self.width):
                    line += chr(0x2588 if self.get_pixel(w, h) else blank_char)
                if frame:
                    line = chr(0x2502) + line + chr(0x2502)
                lines.append(line)
        if frame_length:
            lines.append(chr(0x2514) + (frame_length * chr(0x2500)) + chr(0x2518))
        return "\n".join(lines)

    def __len__(self):
        return self._get_byte_size()

    def __str__(self) -> str:
        return self.text(in_quad = True)

    def __eq__(self, value: object, /) -> bool:
        if not isinstance(value, Canvas):
            return False
        return value.get_image() == self.get_image()

    def __repr__(self) -> str:
        w, h = self.size
        return f"<{self.__class__.__name__} size={w}x{h} length={self.__len__()}>"


def quartet_to_char(char: int):
    """
    Gets a unicode block symbol code for a 4 bit value (0x0 to 0xF), each bit representing
    a corner of the 4 pixels, top left (1 << 0), top right (1 << 1), bottom left (1 << 2)
    and bottom right (1 << 3) respectively.
    """
    if (char > 0xF) or (char < 0x0):
        raise ValueError("Invalid character.")
    # https://en.wikipedia.org/wiki/Block_Elements
    data = {
        0x0: 0x0000, # Blank
        0x1: 0x2598, # 0001
        0x2: 0x259D, # 0010
        0x3: 0x2580, # 0011
        0x4: 0x2596, # 0100
        0x5: 0x258C, # 0101
        0x6: 0x259E, # 0110
        0x7: 0x259B, # 0111
        0x8: 0x2597, # 1000
        0x9: 0x259A, # 1001
        0xA: 0x2590, # 1010
        0xB: 0x259C, # 1011
        0xC: 0x2584, # 1100
        0xD: 0x2599, # 1101
        0xE: 0x259F, # 1110
        0xF: 0x2588, # 1111
    }
    return data[char]


class DirectiveBuilder:
    """
    Builds directives for the printer.
    """

    @staticmethod
    def start():
        # [154, 2, 0, 0] is the "job ID".
        # Without that, printer won't print anything but a small blank label.
        # This the only "job ID" that the printer uses in start directive, it is not
        # related with some sort of queue or anything else, just a constant value.
        return bytes([*DirectiveCommand.START.to_bytes(), 154, 2, 0, 0])

    @staticmethod
    def media_type(value: int):
        return bytes([*DirectiveCommand.MEDIA_TYPE.to_bytes(), value])

    @staticmethod
    def form_feed():
        return bytes(DirectiveCommand.FORM_FEED.to_bytes())
    
    @staticmethod
    def status():
        return bytes(DirectiveCommand.STATUS.to_bytes())
    
    @staticmethod
    def end():
        return bytes(DirectiveCommand.END.to_bytes())

    @staticmethod
    def print(
        data: Sequence[int],
        image_width: int,
        image_height: int,
        bits_per_pixel: int, 
        alignment: int
    ):
        size = \
            image_width.to_bytes(4, "little") + \
            image_height.to_bytes(4, "little")
        return bytes([
            *DirectiveCommand.PRINT_DATA.to_bytes(), 
            bits_per_pixel, 
            alignment, 
            *size,
            *data
        ])


def create_payload(data: Sequence[int], is_print: bool = False):
    """
    Creates a final payload to be sent to the printer from the input data.

    Each iteration of this generator will yield the bytes that needs to be sent over 
    the Bluetooth for each GATT write transaction.
    """
    # Longer inputs needs to be splitted.
    CHUNK_SIZE = 500
    # Magic value.
    MAGIC = [18, 52]
    # Length of the data in 4 bytes.
    length = len(data).to_bytes(4, "little")
    # byte[9] = [255, 240, 18, 52, ...LENGTH{4}, CHECKSUM]
    header = bytearray([
        255, # Preamble
        240, # Flags
        *MAGIC,
        *length
    ])
    # For checksum, we get the sum of all bytes, then get the first byte of the sum.
    checksum = sum(header) & 0xFF
    header.append(checksum)
    assert len(header) == 9, "Header must be 9 bytes"
    # Payloads other than writing doesn't require chunking, 
    # so the input data can be added as-is.
    if not is_print:
        header.extend(data)
        yield header
    # However, write payloads must be chunked properly.
    else:
        # First yield the header.
        yield header
        # Split chunk in each 500 bytes.
        for index, step in enumerate(range(0, len(data), CHUNK_SIZE)):
            current_chunk = bytearray()
            chunk = data[step: step + CHUNK_SIZE]
            # TODO: Not sure what is the purpose of the this, but the original
            # vendor app skips this index, so we do the same here.
            chunk_index = index + 1 if index >= 27 else index
            current_chunk.append(chunk_index)
            current_chunk.extend(chunk)
            # If this is the last chunk, append MAGIC to the end.
            if (step + CHUNK_SIZE) >= len(data):
                current_chunk.extend(MAGIC)
            yield current_chunk


def command_print(
    canvas: Canvas
):
    """
    Creates a print directive.
    """
    payload = bytearray()
    payload.extend(DirectiveBuilder.start())
    payload.extend(DirectiveBuilder.print(
        canvas.get_image(), 
        canvas.width,
        canvas.height, 
        bits_per_pixel = 1, 
        alignment = 2
    ))
    payload.extend(DirectiveBuilder.form_feed())
    payload.extend(DirectiveBuilder.status())
    payload.extend(DirectiveBuilder.end())
    return create_payload(payload, is_print = True)


def command_casette(
    media_type: int
):
    """
    Creates a casette directive.
    """
    payload = bytearray()
    payload.extend(DirectiveBuilder.start())
    payload.extend(DirectiveBuilder.media_type(media_type))
    payload.extend(DirectiveBuilder.end())
    return create_payload(payload)