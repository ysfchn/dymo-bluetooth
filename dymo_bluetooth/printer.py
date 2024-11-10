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
from typing import Union
import math

BytesLike = Union[bytes, bytearray]


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
    def from_bytes(cls, data : BytesLike):
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
    An implementation of 1-bit monochrome little-endian encoded 32 pixel height 
    images for printing them to the label.

    1 byte equals 8 bits, and each bit specifies if pixel should be black (= 1) 
    or white (= 0). The generated image will contain a multiple of 4 bytes, equaling 
    the label height in pixels (4 * 8 = 32 pixels).
    """

    __slots__ = ("buffer", )

    HEIGHT = 32
    MAX_WIDTH = 8186

    def __init__(self) -> None:
        self.buffer = BytesIO()

    def get_pixel(self, x : int, y : int):
        """
        Gets the pixel in given coordinates. 
        Returns True if pixel is black, otherwise False.
        """
        if y >= Canvas.HEIGHT:
            raise ValueError(f"Canvas can't exceed {Canvas.HEIGHT} pixels in height.")
        if x >= Canvas.MAX_WIDTH:
            raise ValueError(f"Canvas can't exceed {Canvas.MAX_WIDTH} pixels in width.")

        # Get the byte containing the pixel value of given coordinates.
        x_offset = math.ceil((x * Canvas.HEIGHT) / 8)
        y_offset = 3 - math.floor(y / 8)
        self.buffer.seek(x_offset + y_offset)

        # Check if there is a bit value in given line.
        read = self.buffer.read(1)
        value = int.from_bytes(read or b"\x00", "little")
        is_black = bool(value & (1 << (7 - (y % 8))))
        return is_black

    def set_pixel(self, x : int, y : int, color : bool):
        """
        Sets a pixel to given coordinates.
        Setting color to True will paint a black color.
        """
        if y >= Canvas.HEIGHT:
            raise ValueError(f"Canvas can't exceed {Canvas.HEIGHT} pixels in height.")
        if x >= Canvas.MAX_WIDTH:
            raise ValueError(f"Canvas can't exceed {Canvas.MAX_WIDTH} pixels in width.")

        # Get the byte containing the pixel value of given coordinates.
        x_offset = math.ceil((x * Canvas.HEIGHT) / 8)
        y_offset = 3 - math.floor(y / 8)
        self.buffer.seek(x_offset + y_offset)

        # Get the one of four slices in line in the given coordinates. Add the bit in
        # given location if color is black, otherwise exclude the bit to make it white.
        read = self.buffer.read(1)
        value = int.from_bytes(read or b"\x00", "little")
        if color:
            value = value | (1 << (7 - (y % 8)))
        else:
            value = value & ~(1 << (7 - (y % 8)))

        # Change the current part of the line with modified one.
        self.buffer.seek(x_offset + y_offset)
        self.buffer.write(bytes([value]))

    def stretch_image(self, factor : int = 2):
        """
        Stretches image to the right in N times, and returns a new Canvas
        containing the stretched image. Factor 1 results in the same image.
        """
        if factor < 1:
            raise ValueError("Stretch factor must be at least 1!")
        canvas = Canvas()
        for x in range(self.get_width()):
            for y in range(Canvas.HEIGHT):
                pixel = self.get_pixel(x, y)
                start_x = (x * factor)
                for i in range(factor):
                    canvas.set_pixel(start_x + i, y, pixel)
        return canvas

    def pad_image(self, width : int):
        """
        Adds blank spacing to both sides of the image, until the image
        reaches to the given width. Returns a new Canvas containing the
        modified image. If image is already longer than given width, it
        will return the current Canvas.
        """
        current_width = self.get_width()
        if current_width >= width:
            return self
        canvas = Canvas()
        left_padding = math.ceil(width / 2)
        for x in range(current_width):
            for y in range(Canvas.HEIGHT):
                canvas.set_pixel(left_padding + x, y, self.get_pixel(x, y))
        for i in range(Canvas.HEIGHT):
            canvas.set_pixel(current_width + left_padding, i, False)
        return canvas

    def print(self):
        """
        Prints the image to the console.
        """
        for y in range(Canvas.HEIGHT):
            for x in range(self.get_width()):
                print("█" if self.get_pixel(x, y) else "░", end = "")
            print()

    def get_width(self):
        """
        Gets the painted width of the image.
        """
        self.buffer.seek(0, SEEK_END)
        cur = self.buffer.tell()
        return math.ceil(cur / 4)

    def get_size(self):
        """
        Gets the width and height of the image in tuple.
        """
        return (self.get_width(), Canvas.HEIGHT, )

    def get_image(self):
        """
        Gets the created image with added blank padding.
        """
        self.buffer.seek(0)
        image = self.buffer.read()
        return image + (b"\x00" * (self.buffer.tell() % 4))

    def empty(self):
        """
        Makes all pixels in the canvas in white. Canvas size won't be changed.
        """
        self.buffer.seek(0, SEEK_END)
        byte_count = self.buffer.tell()
        self.buffer.seek(0)
        self.buffer.truncate(0)
        self.buffer.seek(byte_count)
        self.buffer.write(b"\x00")

    def copy(self):
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

    def __eq__(self, value: object, /) -> bool:
        if not isinstance(value, Canvas):
            return False
        return value.get_image() == self.get_image()

    def __repr__(self) -> str:
        self.buffer.seek(0, SEEK_END)
        byte_size = self.buffer.tell()
        image_size = "x".join(map(str, self.get_size()))
        return f"<{self.__class__.__name__} image={image_size} bytes={byte_size}>"


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
    def media_type(value : int):
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
        data : BytesLike,
        image_width : int,
        bits_per_pixel : int, 
        alignment : int
    ):
        size = \
            image_width.to_bytes(4, "little") + \
            Canvas.HEIGHT.to_bytes(4, "little")
        return bytes([
            *DirectiveCommand.PRINT_DATA.to_bytes(), 
            bits_per_pixel, 
            alignment, 
            *size,
            *data
        ])


def create_payload(data : BytesLike, is_print : bool = False):
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
            chunk = data[step : step + CHUNK_SIZE]
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
    canvas : Canvas
):
    """
    Creates a print directive.
    """
    payload = bytearray()
    payload.extend(DirectiveBuilder.start())
    payload.extend(DirectiveBuilder.print(
        canvas.get_image(), 
        canvas.get_width(), 
        bits_per_pixel = 1, 
        alignment = 2
    ))
    payload.extend(DirectiveBuilder.form_feed())
    payload.extend(DirectiveBuilder.status())
    payload.extend(DirectiveBuilder.end())
    return create_payload(payload, is_print = True)


def command_casette(
    media_type : int
):
    """
    Creates a casette directive.
    """
    payload = bytearray()
    payload.extend(DirectiveBuilder.start())
    payload.extend(DirectiveBuilder.media_type(media_type))
    payload.extend(DirectiveBuilder.end())
    return create_payload(payload)