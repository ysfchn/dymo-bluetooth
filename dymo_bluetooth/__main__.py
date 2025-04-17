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

from argparse import ArgumentParser, BooleanOptionalAction
from pathlib import Path
from typing import Literal, Union, cast
from dymo_bluetooth.bluetooth import discover_printers, create_image
import sys
import asyncio
import os

async def print_image(
    input_file: Path, 
    max_timeout: int, 
    stretch_factor: int, 
    use_dither: bool,
    ensure_mac: bool,
    padding: int,
    reverse: bool,
    is_preview: Union[None, Literal["large", "small"]]
):
    canvas = create_image(input_file, dither = use_dither)
    if stretch_factor != 1:
        canvas = canvas.stretch(factor = stretch_factor)
    if padding != 0:
        canvas = canvas.fill(padding, padding)
    if reverse:
        canvas = canvas.revert()

    if is_preview:
        print(canvas.text(False if is_preview == "large" else True))
        exit(0)

    print(f"Image size: {canvas.size}", file = sys.stderr)
    print(f"Searching for nearby printers to print (timeout: {max_timeout})...", file = sys.stderr)
    printers = await discover_printers(max_timeout, ensure_mac)
    if not printers:
        print("Couldn't find any printers, is the printer online?", file = sys.stderr)
        exit(1)
    printer = printers[0]
    print(f"Found: {printer._impl.address}", file = sys.stderr)
    await printer.connect()
    print("Printing...", file = sys.stderr)
    result = await printer.print(canvas)
    print(f"Result: {result.name} ({result.value})", file = sys.stderr)


def main():
    module_name = cast(str, sys.modules[__name__].__file__).split(os.sep)[-2]
    args = ArgumentParser(
        prog = f"python -m {module_name}",
        description = (
            "Print monochrome labels with DYMO LetraTag LT-200B label printer over Bluetooth. "
            "If executed without --preview, it will search for a printer nearby and automatically "
            "start printing the image."
        )
    )
    args.add_argument(
        "image", 
        help = (
            "Image file to print. Can be any type of image that is supported by Pillow. "
            "Must be 32 pixels in height, otherwise it will be cropped out."
        ), 
        type = Path, 
        metavar = "IMAGE"
    )
    args.add_argument(
        "--ensure-mac", 
        default = False, 
        action = "store_true",
        help = (
            "Also ensures the MAC address does match with the pre-defined MAC prefixes when "
            "searching for a printer. Otherwise it will only search for printers by "
            "looking for service UUID and its Bluetooth name."
        )
    )
    args.add_argument(
        "--timeout", 
        default = 5, 
        type = int, 
        help = "Maximum timeout in seconds to search for printers."
    )
    args.add_argument(
        "--dither", 
        default = True, 
        action = BooleanOptionalAction,
        help = (
            "Use or don't use Floyd-Steinberg dithering provided by Pillow when converting "
            "the image to a monochrome image."
        )
    )
    args.add_argument(
        "--stretch", 
        default = 2, 
        type = int,
        help = (
            "Stretch the image N times. Default is 2 (as-is in the mobile app), otherwise "
            "the printed label will become too thin to actually read."
        )
    )
    args.add_argument(
        "--padding", 
        default = 0, 
        type = int,
        help = (
            "Adds N blank width in both sides of the image, leaving the content in the center. "
            "So the output width will be ((N * 2) + image width)."
        )
    )
    args.add_argument(
        "--reverse",
        action = "store_true",
        help = (
            "Flip the image in color (black becomes white, white becomes black)."
        )
    )
    args.add_argument(
        "--preview",
        const = "small",
        nargs = "?",
        choices = ("large", "small"),
        help = (
            "Don't actually print anything, just print the image in the console with all settings "
            "applied to it. The default is 'small', which is the recommended option."
        )
    )
    parsed = args.parse_args()
    input_file = cast(Path, parsed.image).absolute()
    max_timeout = cast(int, parsed.timeout)
    stretch_factor = cast(int, parsed.stretch)
    use_dither = cast(bool, parsed.dither)
    ensure_mac = cast(bool, parsed.ensure_mac)
    padding = cast(int, parsed.padding)
    reverse = cast(bool, parsed.reverse)
    is_preview = cast(Union[None, Literal["large", "small"]], parsed.preview)

    if not input_file.exists():
        print(f"Input file doesn't exists: {input_file.as_posix()}", file = sys.stderr)
        exit(1)
    if input_file.is_dir():
        print(f"Input file can't be a directory: {input_file.as_posix()}", file = sys.stderr)
        exit(1)

    asyncio.run(print_image(
        input_file, 
        max_timeout, 
        stretch_factor, 
        use_dither,
        ensure_mac,
        padding,
        reverse,
        is_preview
    ))


if __name__ == "__main__":
    main()
