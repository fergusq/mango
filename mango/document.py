import itertools
import json
import re
from typing import Callable, Dict, List, Literal, NamedTuple, Tuple, Union

from .params import Parameters
from .script import Interpreter, lexer, parseBlock


class Paragraph(NamedTuple):
    text: str
    type: Literal["title", "subtitle", "subsubtitle", "subsubsubtitle", "text"]
    no_page_break: bool

    @staticmethod
    def fromText(text, type="text", no_page_break=False):
        text = substituteCharacterEscapes(text)
        text = addBalance(text)
        return Paragraph(text=text.strip(), type=type, no_page_break=no_page_break)

class Table(NamedTuple):
    rows: List[List["DocumentObj"]]
    no_page_break: bool

class VSpace(NamedTuple):
    height: float
    no_page_break: bool

class HLine(NamedTuple):
    no_page_break: bool

class Subenvironment(NamedTuple):
    paragraphs: List["DocumentObj"]

class Eval(NamedTuple):
    func: Callable[[Parameters], None]

DocumentObj = Union[Paragraph, Table, VSpace, Subenvironment, Eval, HLine]
Chapter = List[DocumentObj]

def jsonToDocument(code: str) -> List[Chapter]:
    jdoc = json.loads(code)
    if not isinstance(jdoc, list):
        raise RuntimeError("The document must be a JSON list")
    
    elif jdoc and not isinstance(jdoc[0], list):
        jdoc = [jdoc]
    
    def jsonToDocumentObj(jpg):
        if not isinstance(jpg, dict):
            raise RuntimeError("Paragraphs must be JSON objects")

        pg_type = jpg.get("type", "text")
        if pg_type in {"title", "subtitle", "subsubtitle", "subsubsubtitle", "text"}:
            return Paragraph.fromText(text=jpg.get("text"), type=pg_type, no_page_break=not jpg.get("page_break", True))
        
        elif pg_type == "table":
            rows = []
            for jrow in jpg.get("rows"):
                cols = []
                for jcol in jrow:
                    cols.append(jsonToDocumentObj(jcol))
                
                rows.append(cols)
            
            return Table(rows=rows, no_page_break=not jpg.get("page_break", True))
        
        elif pg_type == "vspace":
            return VSpace(jpg.get("height", 0), no_page_break=not jpg.get("page_break", True))
        
        elif pg_type == "set":
            var = jpg["param"]
            val = jpg["value"]

            return Eval(lambda params: setattr(params, var, val))
        
        elif pg_type == "subenv":
            return Subenvironment([jsonToDocumentObj(pg) for pg in jpg["pgs"]])
        
        else:
            raise RuntimeError("Unknown document object type " + repr(pg_type))
    
    ans: List[Chapter] = []
    for jchapter in jdoc:
        chapter: Chapter = []
        for jpg in jchapter:
            chapter.append(jsonToDocumentObj(jpg))
        
        ans.append(chapter)
    
    return ans

def evalScript(code: str) -> List[Chapter]:
    chapters: List[Chapter] = []
    current_chapter_stack: List[List[DocumentObj]] = [[]]
    
    itpt = Interpreter()
    fs = itpt.frames[-1].functions

    def pgf(type):
        return lambda text, pb=True: current_chapter_stack[-1].append(Paragraph.fromText(text, type, not pb))

    fs["pg"] = pgf("text")
    fs["title"] = pgf("title")
    fs["subtitle"] = pgf("subtitle")
    fs["subsubtitle"] = pgf("subsubtitle")
    fs["subsubsubtitle"] = pgf("subsubsubtitle")
    fs["cpg"] = pgf("ctext")
    fs["ctitle"] = pgf("ctitle")
    fs["csubtitle"] = pgf("csubtitle")
    fs["csubsubtitle"] = pgf("csubsubtitle")
    fs["csubsubsubtitle"] = pgf("csubsubsubtitle")

    def newPage():
        if current_chapter_stack[-1]:
            chapters.append(current_chapter_stack[-1])
            current_chapter_stack[-1] = []
    
    fs["newpage"] = newPage

    def vspace(h, pb=True):
        current_chapter_stack[-1].append(VSpace(h, not pb))

    fs["vspace"] = vspace
    fs["hline"] = lambda pb=True: current_chapter_stack[-1].append(HLine(not pb))

    table_stack: List[List[List[DocumentObj]]] = []

    def tablestart():
        table_stack.append([])
        current_chapter_stack.append([])
    
    def tablestop(pb=True):
        row = current_chapter_stack.pop()
        table_stack[-1].append(row)
        rows = table_stack.pop()
        current_chapter_stack[-1].append(Table(rows, not pb))
    
    def nextrow():
        row = current_chapter_stack.pop()
        table_stack[-1].append(row)
        current_chapter_stack.append([])
    
    fs["tablestart"] = tablestart
    fs["tablestop"] = tablestop
    fs["nextrow"] = nextrow

    fs["row"] = lambda *cols: current_chapter_stack[-1].append(Table([[Paragraph.fromText(col, "text") for col in cols]], False))
    
    fs["set"] = lambda var, val: current_chapter_stack[-1].append(Eval(lambda params: setattr(params, var, val)))
    fs["addfont"] = lambda var, name: current_chapter_stack[-1].append(Eval(lambda params: params.addFont(var, name)))

    def envstart():
        current_chapter_stack.append([])
    
    def envstop():
        pgs = current_chapter_stack.pop()
        current_chapter_stack[-1].append(Subenvironment(pgs))
    
    fs["envstart"] = envstart
    fs["envstop"] = envstop

    def splitchars(string):
        string = " ".join(string)
        for open, close in MARKUP_CODES.keys():
            string = string.replace(" ".join(open), open)
            string = string.replace(" ".join(close), close)
        
        return string

    fs["splitchars"] = splitchars

    tokens = lexer(code)
    #print(tokens)
    tree = parseBlock(tokens)
    #print(tree)
    tree.eval(itpt)

    newPage()

    return chapters

def parseDocument(text: str) -> List[Chapter]:
    lines = text.split("\n")
    ans: List[List[str]] = []
    chapter = []
    for line in lines:
        if line.strip() == "\\newpage":
            if chapter:
                ans.append(chapter)
            
            chapter = []
        
        else:
            chapter.append(line)
    
    if chapter:
        ans.append(chapter)
    
    return [parseChapter(c) for c in ans]

def parseChapter(lines: List[str]) -> Chapter:
    pgs: List[DocumentObj] = []
    partial = ""
    npb = False
    quote = False
    def parseParagraph():
        nonlocal partial, npb
        partial = partial.strip()
        if partial.startswith("\\"):
            if " " in partial:
                command = partial[1:partial.index(" ")]
                partial = partial[len(command)+2:].strip()
            else:
                command = partial[1:]
                partial = ""
        
        else:
            command = None

        if command == "title":
            pgs.append(Paragraph.fromText(text=partial, type="title", no_page_break=npb))
            npb = True
        elif command == "subtitle":
            pgs.append(Paragraph.fromText(text=partial, type="subtitle", no_page_break=npb))
            npb = True
        elif command == "subsubtitle":
            pgs.append(Paragraph.fromText(text=partial, type="subsubtitle", no_page_break=npb))
            npb = True
        elif command == "subsubsubtitle":
            pgs.append(Paragraph.fromText(text=partial, type="subsubsubtitle", no_page_break=npb))
            npb = True
        elif command == "split_chars":
            partial = " ".join(list(partial))
            pgs.append(Paragraph.fromText(text=partial, type="text", no_page_break=npb))
        elif command:
            print(f"Tuntematon komento {command}!")
        elif partial:
            pgs.append(Paragraph.fromText(text=partial, type="text", no_page_break=npb))
            npb = False
        
        partial = ""
    
    def parseLine(line: str):
        nonlocal partial, npb
        if line == "":
            if partial.strip():
                parseParagraph()
        
        elif line == "\\nopagebreak":
            npb = True
        
        elif line == "\\quotestart":
            quote = True
        
        elif line == "\\quotestop":
            quote = False

        elif line.startswith("\\sets "):
            args = line[line.index(" "):].strip()
            if " " in args:
                var = args[:args.index(" ")]
                val = args[args.index(" "):].strip()
            
            else:
                var = args
                val = ""
            
            pgs.append(Eval(lambda params: setattr(params, var, val)))

        elif line.startswith("\\setf "):
            args = line[line.index(" "):].strip()
            if " " in args:
                var = args[:args.index(" ")]
                val = float(args[args.index(" "):].strip())
            
            else:
                var = args
                val = 0.0
            
            pgs.append(Eval(lambda params: setattr(params, var, val)))

        elif line.startswith("\\add_font "):
            args = line[line.index(" "):].strip()
            if " " in args:
                var = args[:args.index(" ")]
                val = args[args.index(" "):].strip()
            
            else:
                var = args
                val = "serif"
            
            pgs.append(Eval(lambda params: params.addFont(var, val)))
        
        elif "|" in line:
            parseParagraph()
            pgs.append(Table(rows=[[Paragraph.fromText(text=c) for c in line.split("|")]], no_page_break=npb))
        
        elif line == "\\tablestart":
            parseParagraph()
            rows = []
            line = lines.pop(0).strip()
            while lines and line != "\\tablestop":
                columns = [Paragraph.fromText(text=c) for c in line.split("|")]
                rows.append(columns)
                line = lines.pop(0).strip()
            
            pgs.append(Table(rows=rows, no_page_break=npb))
            npb = False
        
        elif line.startswith("\\vspace"):
            parseParagraph()
            if " " in line:
                height = float(line[line.index(" "):].strip())
            else:
                height = 0
            pgs.append(VSpace(height=height, no_page_break=npb))
            npb = False
        
        else:
            partial += " " + line

    while lines:
        line = lines.pop(0).strip()
        parseLine(line)
        
    parseParagraph()
    
    return pgs

def stripMarkup(text: str) -> str:
    return re.sub(r"[{}\[\]]", "", text)

MARKUP_CODES: Dict[Tuple[str, str], Tuple[str, str]] = {
    ("[", "]"): ("<i>", "</i>"),
    ("*{", "}*"): ("<b>", "</b>"),
    ("~{", "}~"): ("<s>", "</s>"),

    ("^{", "}^"): ("<sup>", "</sup>"),
    ("_{", "}_"): ("<sub>", "</sub>"),

    ("%{", "}%"): ("<span font_variant=\"smallcaps\" font_features=\"'c2sc' 1, 'smcp' 1\">", "</span>"),
    ("${", "}$"): ("<span color=\"grey\">", "</span>"),
}

MARKUP_CODE_DICT = {m: c for k, v in MARKUP_CODES.items() for m, c in zip(k, v)}
MARKUP_CODE_LIST = list(sorted(MARKUP_CODES, key=lambda t: -len(t[0])))

def fixMarkup(text: str) -> str:
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    for open, close in MARKUP_CODE_LIST:
        text = _balance(text, open, close)
    
    text = _substituteMarkup(text)
    return text

def _balance(text: str, open: str, close: str) -> str:
    i = 0
    d = 0
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue

        if text[i:].startswith(open):
            d += 1
            i += len(open)
        
        elif text[i:].startswith(close):
            d -= 1
            i += len(close)
        
        else:
            i += 1
    
    while d > 0:
        text += close
        d -= 1
    
    while d < 0:
        text = open + text
        d += 1
    
    while open+close in text:
        text = text.replace(open+close, "")
    
    return text

def _substituteMarkup(text: str) -> str:
    ans = ""
    i = 0
    while i < len(text):
        if text[i] == "\\":
            ans += text[i+1]

            i += 2
        
        for code in itertools.chain(*MARKUP_CODE_LIST):
            if text[i:].startswith(code):
                ans += MARKUP_CODE_DICT[code]
                i += len(code)
                break
        else:
            ans += text[i]
            i += 1
    
    return ans

def substituteCharacterEscapes(text: str) -> str:
    ans = ""
    i = 0
    while i < len(text):
        if text[i] == "\\":
            if text[i+1] == "n":
                ans += "\n"
                i += 2
                continue

            ans += text[i:i+2]
            i += 2
            continue
        
        ans += text[i]
        i += 1
    
    return ans

def addBalance(text: str) -> str:
    words = text.split(" ")
    new_words = []
    balance = ""
    for word in words:
        word = balance + word
        balance = getBalance(word)
        new_words.append(word)
    
    return " ".join(new_words)

def getBalance(text: str) -> str:
    ans = ""
    for open, close in MARKUP_CODE_LIST:
        ans += _getBalance(text, open, close)
    
    return ans

def _getBalance(text: str, open: str, close: str) -> str:
    i = 0
    d = 0
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue

        if text[i:].startswith(open):
            d += 1
            i += len(open)
        
        elif text[i:].startswith(close):
            d -= 1
            i += len(close)
        
        else:
            i += 1
    
    return d*open
