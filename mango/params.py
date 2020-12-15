from argparse import Namespace
from typing import Dict, Literal

import pangocffi as pango


class Parameters:
    width: float
    height: float
    margin: float
    line_width: float
    line_height: float
    page_height: float
    pg_gap: float
    column_gap: float
    min_word_gap: float
    indent: float
    text_align: Literal["justify", "center"]

    font: str
    fonts: Dict[str, pango.FontDescription]

    def __init__(self, args: Namespace):
        self.width = float(args.width)
        self.height = float(args.height)
        self.margin = float(args.margin)
        self.line_width = float(self.width - 2 * self.margin)
        self.line_height = float(16)
        self.page_height = float(self.height - 2 * self.margin)
        self.pg_gap = float(16)
        self.column_gap = float(10)
        self.min_word_gap = float(5)
        self.indent = float(0)
        self.quote_indent = float(50)
        self.text_align = "justify"
        self.font_size = float(10)

        self.font = "rm"
        self.fonts = {}
        self.fonts["rm"] = pango.FontDescription()
        self.fonts["rm"].set_family(args.font)
        self.fonts["rm"].set_size(pango.units_from_double(10))

        print(f"Paperin koko {self.width}x{self.height}")
        print(f"Piirtoalueen koko {self.line_width}x{self.page_height}")
    
    def resetLayout(self):
        self.indent = 0
    
    def addFont(self, varname, fontname):
        print(f"Lisätään fontti {varname} = {repr(fontname)}")
        self.fonts[varname] = pango.FontDescription()
        self.fonts[varname].set_family(fontname)
        self.fonts[varname].set_size(pango.units_from_double(10))