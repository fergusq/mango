import argparse
import math
from os import sysconf

from mango.document import evalScript, jsonToDocument, parseDocument
from mango.render import draw

PAGESIZES = {
    "A0": (841, 1189),
    "A1": (594, 841),
    "A2": (420, 594),
    "A3": (297, 420),
    "A4": (210, 297),
    "A5": (148, 210),
    "A6": (105, 148),
    "A7": (74, 105),
    "A8": (52, 74),
    "A9": (37, 52),
    "A10": (26, 37),
    "B0": (1000, 1414),
    "B1": (707, 1000),
    "B2": (500, 707),
    "B3": (353, 500),
    "B4": (250, 353),
    "B5": (176, 250),
    "B6": (125, 176),
    "B7": (88, 125),
    "B8": (62, 88),
    "B9": (44, 62),
    "B10": (31, 44),
    "C0": (917, 1297),
    "C1": (648, 917),
    "C2": (458, 648),
    "C3": (324, 458),
    "C4": (229, 324),
    "C5": (162, 229),
    "C6": (114, 162),
    "C7": (81, 114),
    "C8": (57, 81),
    "C9": (40, 57),
    "C10": (28, 40),
}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("infile", nargs="?", default="-")
    parser.add_argument("outfile")
    parser.add_argument("--page_size", default="A4")
    parser.add_argument("--width", type=float, default=0)
    parser.add_argument("--height", type=float, default=0)
    parser.add_argument("--margin", type=float, default=50)
    parser.add_argument("--font", default="Sans")
    parser.add_argument("--page_dir", default="v")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    if args.page_size:
        if args.page_size in PAGESIZES:
            args.width = PAGESIZES[args.page_size][0]
            args.height = PAGESIZES[args.page_size][1]
    
    args.width = args.width * math.sqrt(2)**3
    args.height = args.height * math.sqrt(2)**3

    if args.infile == "-":
        text = sysconf.stdin.read()
    
    else:
        with open(args.infile, "r") as f:
            text = f.read()
    
    if args.infile.endswith(".json"):
        chapters = jsonToDocument(text)
    
    elif args.infile.endswith(".mng"):
        chapters = evalScript(text)
    
    else:
        chapters = parseDocument(text)

    draw(args, chapters)

if __name__ == "__main__":
    main()