from collections import defaultdict
import copy
import re
from argparse import Namespace
from math import inf
from typing import List, Optional, Tuple

import cairocffi as cairo
import numpy as np
import pangocairocffi as pangocairo
import pangocffi as pango
from voikko import libvoikko

from .parser import DocumentObj, Paragraph, Table, fixMarkup, getBalance

try:
    voikko = libvoikko.Voikko("fi")
except:
    voikko = None


def irange(a, b, s=1) -> range:
    return range(a, b+1 if s > 0 else b-1, s)

class Line:
    outline: Optional[Tuple[int, str]]
    def __init__(self, height: float, no_page_break=False):
        self.height = height
        self.width = 0
        self.no_page_break = no_page_break
        self.outline = None

    def draw(self, context: cairo.Context, x: float, y: float):
        pass

class ParagraphGap(Line):
    pass

def stripGaps(lines: List[Line]) -> List[Line]:
    i = 0
    while i < len(lines) and isinstance(lines[i], ParagraphGap):
        i += 1
    
    j = len(lines)
    while j > 0 and isinstance(lines[j - 1], ParagraphGap):
        j -= 1
    
    return lines[i:j]

def splitGaps(lines: List[Line]) -> List[List[Line]]:
    pgs = [[]]
    for line in lines:
        pgs[-1].append(line)
        if isinstance(line, ParagraphGap):
            pgs.append([])
    
    return pgs

class TextLine(Line):
    def __init__(self, surf: cairo.Surface, width: float, height: float, no_page_break=False):
        self.surf = surf
        self.width = width
        self.height = height
        self.no_page_break = no_page_break
        self.outline = None
    
    def draw(self, context: cairo.Context, x: float, y: float):
        context.set_source_surface(self.surf, x, y)
        context.paint()
        self.surf.finish()

class EmptyLine(Line):
    def __init__(self, width: float, height: float):
        self.width = width
        self.height = height
        self.no_page_break = False
        self.outline = None
    
    def draw(self, context: cairo.Context, x: float, y: float):
        pass

class ColumnLine(Line):
    def __init__(self, columns: List[Line], pg_gap: float):
        self.columns = columns
        self.column_gap = pg_gap
        self.width = pg_gap * (len(columns) - 1) + sum(l.width for l in columns)
        self.height = max(l.height for l in columns)
        self.no_page_break = any([l.no_page_break for l in columns])
        self.outline = None
    
    def draw(self, context: cairo.Context, x: float, y: float):
        for column in self.columns:
            column.draw(context, x, y)
            x += column.width
            x += self.column_gap

TITLES = {
    "title": (0, 20, 26, "center"),
    "subtitle": (1, 15, 21, "justify"),
    "subsubtitle": (2, 13, 19, "justify"),
    "text": (-1, 10, 16, "justify"),
}

class Parameters:
    def __init__(self, args: Namespace):
        self.width = float(args.width)
        self.height = float(args.height)
        self.margin = float(args.margin)
        self.line_width = float(self.width - 2 * self.margin)
        self.line_height = float(16)
        self.page_height = float(self.height - 2 * self.margin)
        self.pg_gap = float(16)
        self.column_gap = float(10)
        self.text_align = "justify"

        self.fontname = args.font
        self.fonts = {}
        self.fonts["rm"] = pango.FontDescription()
        self.fonts["rm"].set_family(self.fontname)
        self.fonts["rm"].set_size(pango.units_from_double(10))

        print(f"Paperin koko {self.width}x{self.height}")
        print(f"Piirtoalueen koko {self.line_width}x{self.page_height}")

class draw:
    def __init__(self, args: Namespace, paragraphs: List[DocumentObj]):
        print("Alustetaan...")
        self.params = Parameters(args)
        self.param_stack = []

        self.balance = ""

        self.surf = cairo.PDFSurface(args.outfile, args.width, args.height)
        self.context = cairo.Context(self.surf)

        self.context.rectangle(0,0,args.width,args.height)
        self.context.set_source_rgb(1, 1, 1)
        self.context.fill()
        self.font = self.params.fonts["rm"]

        self.context.set_source_rgb(0, 0, 0)

        print("Piirretään sanoja...")
        all_lines = []
        for i, pg in enumerate(paragraphs):
            if i != 0:
                all_lines.append(ParagraphGap(self.params.pg_gap, pg.no_page_break))
            
            if isinstance(pg, Table):
                level, font_size, self.line_height, self.params.text_align = TITLES["text"]
                self.font.set_size(pango.units_from_double(font_size))
                with self._stackFrame():
                    num_columns = max(len(row) for row in pg.rows)
                    max_line_width = self.params.line_width
                    self.params.line_width = (max_line_width - self.params.column_gap * (num_columns - 1)) / num_columns
                    rendered_rows: List[List[List[Line]]] = [[] for _ in range(len(pg.rows))]
                    for i in range(num_columns):
                        max_width = 0
                        for j in range(len(pg.rows)):
                            rendered_rows[j].append(self.textToLines(pg.rows[j][i]))
                            width = rendered_rows[j][i][0].width
                            if width > max_width:
                                max_width = width
                        
                        for rrow in rendered_rows:
                            for line in rrow[i]:
                                line.width = max_width
                        
                        if i != num_columns - 1:
                            self.params.line_width = (max_line_width - max_width - self.params.column_gap * (num_columns - i - 1)) / (num_columns - i - 1)
                    
                    lines = []
                    for rrow in rendered_rows:
                        for i in range(max(len(c) for c in rrow)):
                            column_lines: List[Line] = [c[i] if i < len(c) else EmptyLine(c[0].width, self.line_height) for c in rrow]
                            lines.append(ColumnLine(column_lines, self.params.column_gap))
            
            elif isinstance(pg, Paragraph):
                level, font_size, self.line_height, self.params.text_align = TITLES[pg.type]
                self.font.set_size(pango.units_from_double(font_size))

                if len(pg.columns) == 1:
                    lines = self.textToLines(pg.columns[0], hyphenate=level<0)
                    lines[0].no_page_break = pg.no_page_break
                    if level >= 0:
                        lines[0].outline = (level, pg.columns[0])
                
                else:
                    with self._stackFrame():
                        max_line_width = self.params.line_width
                        self.params.line_width = (max_line_width - self.params.column_gap * (len(pg.columns) - 1)) / len(pg.columns)
                        columns: List[List[Line]] = []
                        for i, column in enumerate(pg.columns):
                            columns.append(self.textToLines(column, hyphenate=level<0))
                            width = columns[-1][0].width
                            if i != len(pg.columns) - 1:
                                self.params.line_width = (max_line_width - width - self.params.column_gap * (len(pg.columns) - i - 1)) / (len(pg.columns) - i - 1)
                    
                        lines = []
                        for i in range(max(len(c) for c in columns)):
                            column_lines: List[Line] = [c[i] if i < len(c) else EmptyLine(c[0].width, self.line_height) for c in columns]
                            lines.append(ColumnLine(column_lines, self.params.column_gap))
            
            all_lines += lines

        print("Lasketaan sivunvaihdot...")
        bps = self.calculatePageBreaks(all_lines)

        print("Piirretään rivejä...")
        page = 1
        last_title = defaultdict(lambda: 0)
        for i, j in zip([0] + bps, bps + [len(all_lines)+1]):
            lines = stripGaps(all_lines[i:j])
            pgs = splitGaps(lines)
            if j == len(all_lines) + 1 or len(pgs) == 1:
                pg_gap = 0
            else:
                pg_gap = (self.params.page_height - sum(l.height for pg in pgs for l in pg)) / (len(pgs) - 1)

            y = self.params.margin
            for pg in pgs:
                for line in pg:
                    if line.outline:
                        link = last_title[line.outline[0] - 1]
                        last_title[line.outline[0]] = self.surf.add_outline(link, line.outline[1], f"page={page} pos=[{self.params.margin} {y}]")

                    line.draw(self.context, self.params.margin, y)
                    y += line.height
                
                y += pg_gap
            
            self.surf.show_page()
            page += 1

        self.surf.finish()

    def createLayout(self, text: str, balance=True) -> pango.Layout:
        if balance:
            text = self.balance + text
            self.balance = getBalance(text)

        layout = pangocairo.create_layout(self.context)
        layout.set_font_description(self.font)
        layout.set_markup(fixMarkup(text))
        return layout
    
    def textToLines(self, text: str, equal_widths=True, hyphenate=True) -> List[Line]:
        ans = []
        layouts = [(word, self.createLayout(word)) for word in text.split()]
        
        min_word_gap = 5
        while layouts:
            surf = cairo.RecordingSurface(cairo.CONTENT_ALPHA, None)
            context = cairo.Context(surf)
            context.set_source_rgb(0, 0, 0)

            i = 0
            il = []
            wsum = 0
            for word, layout in layouts:
                _, _, w, _ = getLayoutExtent(layout)
                if wsum + len(il) * min_word_gap + w > self.params.line_width:
                    if hyphenate and voikko and "-" not in word:
                        syllables = re.split(r"-", voikko.hyphenate(word))
                        for j in range(len(syllables), 0, -1):
                            text = "".join(syllables[0:j])
                            if len(text) == 1:
                                break

                            new_l = self.createLayout(text + "-", balance=False)
                            _, _, new_w, _ = getLayoutExtent(new_l)
                            if wsum + len(il) * min_word_gap + new_w <= self.params.line_width:
                                il.append(new_l)
                                wsum += new_w
                                layout.set_markup(fixMarkup("".join(syllables[j:])))
                                break

                    word_gap = (self.params.line_width - wsum) / (len(il) - 1) if len(il) > 1 else min_word_gap
                    break

                il.append(layout)
                wsum += w
                i += 1
            
            else:
                word_gap = min_word_gap

            x = 0
            
            if self.params.text_align == "center":
                word_gap = min_word_gap
                x = (self.params.line_width - wsum - len(il) * min_word_gap) / 2

            width = -word_gap
            for l in il:
                context.translate(x, 0)
                pangocairo.update_layout(context, l)
                pangocairo.show_layout(context, l)
                context.translate(-x, 0)
                _, _, w, _ = getLayoutExtent(l)
                x += word_gap + w
                width += word_gap + w

            del layouts[:i]

            ans.append(TextLine(surf, width, self.line_height))
        
        # Aseta rivien leveystiedot yhdenmukaiseksi sarakealgoritmia varten
        if equal_widths:
            width = max(line.width for line in ans)
            for line in ans:
                line.width = width
        
        return ans
    
    def calculatePageBreaks(self, lines: List[Line]):
        badness = np.full((len(lines)+1, len(lines)+1), inf)
        for i in irange(0, len(lines) - 1):
            for j in irange(i, len(lines)):
                badness[i, j] = (self.params.page_height - sum(l.height for l in stripGaps(lines[i:j+1]))) ** 3
                
                if badness[i, j] < 0 or lines[i].no_page_break:
                    badness[i, j] = inf

                elif j == len(lines):
                    badness[i, j] = 0
        
        scores = np.full((len(lines)+1, len(lines)), inf)
        bps = {}
        j = len(lines)
        for n in irange(0, len(lines) - 1):
            for i in irange(len(lines) - 1, 0, -1):
                if n == 0:
                    scores[i, n] = inf
                    bps[(i, n)] = []
                
                else:
                    min_score = badness[i, j]
                    min_bps = []
                    for x in irange(i+1, j):
                        score = scores[x, n-1]
                        score += badness[i, x-1]
                        if score < min_score:
                            min_score = score
                            min_bps = [x] + bps[(x, n-1)]
                    
                    scores[i, n] = min_score
                    bps[(i, n)] = min_bps
        
        return bps[(0, len(lines) - 1)]
    
    def _stackFrame(self):
        class C:
            def __enter__(_self, *args):
                self.param_stack.append(self.params)
                self.params = copy.copy(self.params)
            
            def __exit__(_self, *args):
                self.params = self.param_stack.pop()
        
        return C()

def getLayoutExtent(layout: pango.Layout) -> Tuple[float, float, float, float]:
    e = layout.get_extents()
    return (
        pango.units_to_double(e[1].x),
        pango.units_to_double(e[1].y),
        pango.units_to_double(e[1].width),
        pango.units_to_double(e[1].height)
    )