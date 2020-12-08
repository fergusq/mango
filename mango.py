import argparse
from os import sysconf

from mango.parser import parseDocument
from mango.render import draw

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("infile", nargs="?", default="-")
    parser.add_argument("outfile")
    parser.add_argument("--width", type=float, default=595.54)
    parser.add_argument("--height", type=float, default=842.19)
    parser.add_argument("--margin", type=float, default=50)
    parser.add_argument("--font", default="Sans")
    args = parser.parse_args()

    if args.infile == "-":
        text = sysconf.stdin.read()
    
    else:
        with open(args.infile, "r") as f:
            text = f.read()
    
    paragraphs = parseDocument(text)

    draw(args, paragraphs)

if __name__ == "__main__":
    main()