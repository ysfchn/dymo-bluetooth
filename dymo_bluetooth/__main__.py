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
from typing import cast
from dymo_bluetooth.bluetooth import discover_printers, create_image
import sys
import asyncio

async def print_image(
    input_file : Path, 
    max_timeout : int, 
    stretch_factor : int, 
    use_dither : bool
):
    canvas = create_image(input_file, dither = use_dither)
    canvas = canvas.stretch_image(factor = stretch_factor)
    printers = await discover_printers(max_timeout)
    if not printers:
        print("Couldn't find any printers in given timeout!")
        exit(1)
    printer = printers[0]
    print(f"Starting to print on {printer._impl.address}...")
    await printer.connect()
    await printer.print(canvas)


def main():
    module_name = cast(str, sys.modules[__name__].__file__).split("/")[-2]
    args = ArgumentParser(
        prog = f"python -m {module_name}",
        description = (
            "Print monochrome labels with DYMO LetraTag LT-200B label printer over "
            "Bluetooth."
        )
    )
    args.add_argument("image", help = "Image file to print. Must be 32 pixels in height.", type = Path, metavar = "IMAGE") # noqa: E501
    args.add_argument("--timeout", default = 5, type = int, help = "Maximum timeout to search for printers.") # noqa: E501
    args.add_argument("--dither", default = True, action = BooleanOptionalAction,
        help = "Use or don't use dithering when converting it to monochrome image."
    )
    args.add_argument("--factor", default = 2, type = int,
        help = "Stretch the image N times. Default is 2, otherwise printer" + \
        "will print images too thin."
    )
    parsed = args.parse_args()
    input_file = cast(Path, parsed.image).absolute()
    max_timeout = cast(int, parsed.timeout)
    stretch_factor = cast(int, parsed.factor)
    use_dither = cast(bool, parsed.dither)
    if not input_file.exists():
        print(f"Given image file doesn't exists: {input_file.as_posix()}")
        exit(1)
    asyncio.run(print_image(input_file, max_timeout, stretch_factor, use_dither))


if __name__ == "__main__":
    main()