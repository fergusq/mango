from typing import List, Literal, NamedTuple, Union

class Paragraph(NamedTuple):
    columns: List[str]
    type: Literal["title", "subtitle", "subsubtitle", "text"]
    no_page_break: bool

class Table(NamedTuple):
    rows: List[List[str]]
    no_page_break: bool

DocumentObj = Union[Paragraph, Table]

def parseDocument(text: str) -> List[DocumentObj]:
    lines = text.split("\n")
    pgs = []
    partial = ""
    npb = False
    def parseParagraph():
        if partial.strip().startswith("\\title"):
            pgs.append(Paragraph(columns=[partial.strip()[len("\\title"):].strip()], type="title", no_page_break=npb))
        elif partial.strip().startswith("\\subtitle"):
            pgs.append(Paragraph(columns=[partial.strip()[len("\\subtitle"):].strip()], type="subtitle", no_page_break=npb))
        elif partial.strip().startswith("\\subsubtitle"):
            pgs.append(Paragraph(columns=[partial.strip()[len("\\subsubtitle"):].strip()], type="subsubtitle", no_page_break=npb))
        elif partial.strip():
            pgs.append(Paragraph(columns=[partial.strip()], type="text", no_page_break=npb))

    while lines:
        line = lines.pop(0)
        if line.strip() == "":
            parseParagraph()
            partial = ""
            npb = False
        
        elif line.strip() == "\\nopagebreak":
            npb = True
        
        elif "|" in line:
            parseParagraph()
            partial = ""
            pgs.append(Paragraph(columns=line.strip().split("|"), type="text", no_page_break=npb))
        
        elif line.strip() == "\\tablestart":
            parseParagraph()
            partial = ""
            rows = []
            line = lines.pop(0)
            while lines and line.strip() != "\\tablestop":
                columns = line.strip().split("|")
                rows.append(columns)
                line = lines.pop(0)
            
            pgs.append(Table(rows=rows, no_page_break=npb))
        
        else:
            partial += " " + line.strip()
        
    parseParagraph()
    
    return pgs

def fixMarkup(text: str) -> str:
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = _balance(text, "{", "}")
    text = text.replace("{", "<b>").replace("}", "</b>")
    text = _balance(text, "[", "]")
    text = text.replace("[", "<i>").replace("]", "</i>")
    return text

def _balance(text: str, open: str, close: str) -> str:
    i = 0
    d = 0
    while i < len(text):
        if text[i] == open:
            d += 1
        
        elif text[i] == close:
            d -= 1
        
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

def getBalance(text: str) -> str:
    return _getBalance(text, "{", "}") + _getBalance(text, "[", "]")

def _getBalance(text: str, open: str, close: str) -> str:
    i = 0
    d = 0
    while i < len(text):
        if text[i] == open:
            d += 1
        
        elif text[i] == close:
            d -= 1
        
        i += 1
    
    return d*open