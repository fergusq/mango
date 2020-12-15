import copy
import itertools
import re
from argparse import Namespace
from collections import defaultdict
from math import inf
from typing import Callable, List, Optional, Tuple

import cairocffi as cairo
import numpy as np
import pangocairocffi as pangocairo
import pangocffi as pango
from tqdm.cli import tqdm
from voikko import libvoikko

from .document import (Chapter, DocumentObj, Eval, Paragraph, Subenvironment,
                       Table, VSpace, fixMarkup, stripMarkup)
from .params import Parameters

try:
    voikko = libvoikko.Voikko("fi")
except:
    voikko = None

debug = False

def irange(a, b, s=1) -> range:
    return range(a, b+1 if s > 0 else b-1, s)

FixXY = Callable[[float, float], Tuple[float, float]]

class Line:
    outline: Optional[Tuple[int, str]]
    def __init__(self, width: float, height: float, no_page_break=False):
        self.height = height
        self.width = width
        self.indent = 0
        self.no_page_break = no_page_break
        self.outline = None
        self.is_content_line = False

    def draw(self, context: cairo.Context, x: float, y: float, fxy: FixXY):
        if debug:
            context.set_source_rgb(1 if self.no_page_break else 0, 0, 0)
            context.rectangle(*fxy(x-5, y), *fxy(2, 16))
            context.fill()
            context.set_source_rgb(0.5, 0.5, 0.5)
            context.rectangle(*fxy(self.indent+x, y), *fxy(self.width, self.height))
            context.stroke()

class ParagraphGap(Line):

    def draw(self, context: cairo.Context, x: float, y: float, fxy: FixXY):
        super().draw(context, x, y, fxy)
        if debug:
            context.set_source_rgb(1 if self.no_page_break else 0, 0, 0)
            context.rectangle(*fxy(x, y), *fxy(10, 10))
            context.fill()

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
    def __init__(self, surf: cairo.Surface, width: float, height: float, indent:float=0.0, no_page_break=False):
        self.surf = surf
        self.width = width
        self.height = height
        self.indent = indent
        self.no_page_break = no_page_break
        self.outline = None
        self.is_content_line = True
    
    def draw(self, context: cairo.Context, x: float, y: float, fxy: FixXY):
        super().draw(context, x, y, fxy)
        context.set_source_surface(self.surf, *fxy(x+self.indent, y))
        context.paint()
        self.surf.finish()

class ColumnLine(Line):
    def __init__(self, columns: List[Line], pg_gap: float, indent:float=0.0):
        self.columns = columns
        self.column_gap = pg_gap
        self.width = pg_gap * (len(columns) - 1) + sum(l.width for l in columns)
        self.height = max(l.height for l in columns)
        self.indent = indent
        self.no_page_break = any([l.no_page_break for l in columns])
        self.outline = None
        self.is_content_line = True
    
    def draw(self, context: cairo.Context, x: float, y: float, fxy: FixXY):
        super().draw(context, x, y, fxy)
        x += self.indent
        for column in self.columns:
            column.draw(context, x, y, fxy)
            x += column.width
            x += self.column_gap

TITLES = {
    "title": (0, 20, 26, "center"),
    "subtitle": (1, 15, 21, "justify"),
    "subsubtitle": (2, 13, 19, "justify"),
    "subsubsubtitle": (3, 12, 18, "justify"),
    "text": (-1, 10, 16, "justify"),
}

class draw:
    def __init__(self, args: Namespace, chapters: List[Chapter]):
        global debug
        debug = args.debug
        
        print("Alustetaan...")
        self.params = Parameters(args)
        self.param_stack = []

        self.page_direction = args.page_dir

        self.surf = cairo.PDFSurface(args.outfile, *self._fixXY(args.width, args.height))
        self.context = cairo.Context(self.surf)

        #font_options = cairo.FontOptions()
        #font_options.set_antialias(cairo.ANTIALIAS_NONE)
        #self.context.set_font_options(font_options)

        self.context.rectangle(0, 0, *self._fixXY(args.width, args.height))
        self.context.set_source_rgb(1, 1, 1)
        self.context.fill()

        self.context.set_source_rgb(0, 0, 0)
        
        self.page = 1
        self.last_title = defaultdict(lambda: 0)

        for i, chapter in enumerate(chapters):
            print(f"Piirretään kappale {i+1}...")
            self.drawChapter(chapter)

        self.surf.finish()
    
    def drawChapter(self, paragraphs: Chapter):
        print("Piirretään sanoja...")
        all_lines = self.paragraphsToLines(paragraphs)
        print(f"Piirretty {len(all_lines)} riviä!")

        print("Lasketaan sivunvaihdot...")
        bps = self.calculatePageBreaks(all_lines)
        print(f"Laskettu {len(bps)+1} sivua!")

        print("Piirretään sivuja...")
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
                        link = self.last_title[line.outline[0] - 1]
                        self.last_title[line.outline[0]] = self.surf.add_outline(link, line.outline[1], f"page={self.page} pos=[{self.params.margin} {y}]")

                    line.draw(self.context, self.params.margin, y, self._fixXY)
                    y += line.height
                
                y += pg_gap
            
            self.surf.show_page()
            self.page += 1
    
    def paragraphsToLines(self, paragraphs: List[DocumentObj]):
        all_lines: List[Line] = []
        for i, pg in enumerate(paragraphs):
            print(i+1, "/", len(paragraphs), end="\r")

            if isinstance(pg, Table):
                if all_lines and all_lines[-1].is_content_line:
                    all_lines.append(ParagraphGap(0, self.params.pg_gap, pg.no_page_break))
            
                with self._stackFrame():
                    self._getFont().set_size(pango.units_from_double(self.params.font_size))
                    indent = self.params.indent
                    self.params.resetLayout()
                    num_columns = max(len(row) for row in pg.rows)
                    max_line_width = self.params.line_width
                    self.params.line_width = (max_line_width - self.params.column_gap * (num_columns - 1)) / num_columns
                    rendered_rows: List[List[List[Line]]] = [[] for _ in range(len(pg.rows))]
                    for i in range(num_columns):
                        max_width = 0
                        for j in range(len(pg.rows)):
                            if i >= len(pg.rows[j]):
                                pg.rows[j].append(Paragraph.fromText(text=""))

                            rendered_rows[j].append(self.paragraphsToLines([pg.rows[j][i]]))
                            width = rendered_rows[j][i][0].width if rendered_rows[j][i] else 0
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
                            column_lines: List[Line] = [c[i] if i < len(c) else Line(c[0].width if c else 0, self.params.line_height) for c in rrow]
                            lines.append(ColumnLine(column_lines, self.params.column_gap, indent=indent))
                            lines[-1].no_page_break = pg.no_page_break
                
            elif isinstance(pg, Paragraph):
                if all_lines and all_lines[-1].is_content_line:
                    all_lines.append(ParagraphGap(0, self.params.pg_gap, pg.no_page_break))
            
                with self._stackFrame():
                    
                    if pg.type != "text":
                        level, self.params.font_size, self.params.line_height, self.params.text_align = TITLES[pg.type]
                    
                    else:
                        level = -1
                    
                    self._getFont().set_size(pango.units_from_double(self.params.font_size))

                    lines = self.textToLines(pg.text, hyphenate=level<0)
                    if lines:
                        lines[0].no_page_break = pg.no_page_break
                        if level >= 0:
                            lines[0].outline = (level, pg.text)
                        
                        if "title" in pg.type:
                            for line in lines[1:]:
                                line.no_page_break = True
            
            elif isinstance(pg, VSpace):
                lines = [Line(self.params.line_width, pg.height or self.params.line_height)]
                
            elif isinstance(pg, Eval):
                pg.func(self.params)
                lines = []
            
            elif isinstance(pg, Subenvironment):
                with self._stackFrame():
                    lines = self.paragraphsToLines(pg.paragraphs)
            
            else:
                print(f"Tuntematon kappaletyyppi {type(pg)}")
                lines = []
            
            all_lines += lines

        return all_lines

    def createLayout(self, text: str) -> pango.Layout:
        layout = pangocairo.create_layout(self.context)
        layout.set_font_description(self._getFont())
        layout.set_markup(fixMarkup(text))
        return layout
    
    def textToLines(self, text: str, **args) -> List[Line]:
        return list(itertools.chain(*[self.textWithoutNewlinesToLines(t, **args) for t in text.split("\n")]))
    
    def textWithoutNewlinesToLines(self, text: str, equal_widths=True, hyphenate=True) -> List[Line]:
        if text.strip() == "":
            return [Line(0, self.params.line_height)]

        ans = []
        layouts = [(word, self.createLayout(word)) for word in text.split(" ")]
        
        while layouts:
            surf = cairo.RecordingSurface(cairo.CONTENT_ALPHA, None)
            context = cairo.Context(surf)
            context.set_source_rgb(0, 0, 0)

            i = 0
            il = []
            wsum = 0
            for word, layout in layouts:
                _, _, w, h = getLayoutExtent(layout)
                w, h = self._fixXY(w, h)
                if wsum + len(il) * self.params.min_word_gap + w > self.params.line_width:
                    if hyphenate and voikko and "-" not in word:
                        syllables = re.split(r"-", voikko.hyphenate(word))
                        for j in range(len(syllables), 0, -1):
                            text = "".join(syllables[0:j])
                            if len(stripMarkup(text)) <= 1:
                                break

                            new_l = self.createLayout(text + "-")
                            _, _, new_w, new_h = getLayoutExtent(new_l)
                            new_w, new_h = self._fixXY(new_w, new_h)
                            if wsum + len(il) * self.params.min_word_gap + new_w <= self.params.line_width:
                                il.append(new_l)
                                wsum += new_w
                                layout.set_markup(fixMarkup("".join(syllables[j:])))
                                break

                    word_gap = (self.params.line_width - wsum) / (len(il) - 1) if len(il) > 1 else self.params.min_word_gap
                    break

                il.append(layout)
                wsum += w
                i += 1
            
            else:
                word_gap = self.params.min_word_gap
            
            if i == 0:
                _, _, w, h = getLayoutExtent(layouts[0][1])
                w, h = self._fixXY(w, h)
                il.append(layouts[0][1])
                wsum = w
                i += 1

            x = 0
            
            if self.params.text_align == "center":
                word_gap = self.params.min_word_gap
                x = (self.params.line_width - wsum - len(il) * self.params.min_word_gap) / 2

            width = -word_gap
            height = self.params.line_height
            for l in il:
                context.translate(*self._fixXY(x, 0))
                #pangocairo.update_context(context, l.get_context())
                pangocairo.show_layout(context, l)
                context.translate(*self._fixXY(-x, 0))
                _, _, w, h = getLayoutExtent(l)
                w, h = self._fixXY(w, h)
                x += word_gap + w
                width += word_gap + w
                if h > height:
                    height = h
            
            if self.params.text_align == "center":
                width = self.params.line_width

            del layouts[:i]

            if height != self.params.line_height:
                print(f"Liian pitkä rivi: {height} {repr(text)}")

            ans.append(TextLine(surf, width, height, indent=self.params.indent))
        
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
                
                if badness[i, j] < 0:
                    badness[i, j] = inf
                
                elif lines[i].no_page_break:
                    badness[i, j] += 1e50

                elif j == len(lines):
                    badness[i, j] = 0
        
        scores = np.full((len(lines)+1, len(lines)), inf)
        bps = {}
        j = len(lines)
        for n in tqdm(irange(0, len(lines) - 1)):
            for i in irange(len(lines) - 1, 0, -1):
                if n == 0:
                    scores[i, n] = inf
                    bps[(i, n)] = []
                
                else:
                    min_score = badness[i, j]
                    min_bps = []
                    for x in irange(i+1, j):
                        score = scores[x, n-1] + badness[i, x-1]
                        if score < min_score:
                            min_score = score
                            min_bps = [x] + bps[(x, n-1)]
                    
                    scores[i, n] = min_score
                    bps[(i, n)] = min_bps
        
        return bps[(0, len(lines) - 1)]
    
    def _getFont(self):
        return self.params.fonts[self.params.font]
    
    def _stackFrame(self):
        class C:
            def __enter__(_self, *args):
                self.param_stack.append(self.params)
                self.params = copy.copy(self.params)
            
            def __exit__(_self, *args):
                self.params = self.param_stack.pop()
        
        return C()
    
    def _fixXY(self, x: float, y: float) -> Tuple[float, float]:
        if self.page_direction in "^v":
            return x, y
        
        else:
            return y, x

def getLayoutExtent(layout: pango.Layout) -> Tuple[float, float, float, float]:
    e = layout.get_extents()
    return (
        pango.units_to_double(e[1].x),
        pango.units_to_double(e[1].y),
        pango.units_to_double(e[1].width),
        pango.units_to_double(e[1].height)
    )
