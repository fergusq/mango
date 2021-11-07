import yajwiz
import sys
import json
import argparse
import re


consonant = r"(ch|gh|ng|tlh|[bDHjlmnpqQrStvwy'])"
vowel = r"(a|e|I|o|u)"
syllable = rf"({consonant}+{vowel}+({consonant}+|w'|y'|rgh)?)"
word_pattern = re.compile(rf"({syllable})+")

def line2tlhng(line: str, mapping):
    tlhng = ""
    italic = False
    for token_type, word in yajwiz.tokenize(line):
        if token_type == "SPACE":
            continue
        
        elif token_type == "PUNCT":
            if word in ".!?":
                tlhng += ""

            elif word in ",;:…—-" or word == "...":
                tlhng += ""
            
            elif word in "«‹<":
                tlhng += ""
            
            elif word in "»›>":
                tlhng += ""
            
            elif word == "_":
                italic = not italic
                if italic:
                    tlhng += "${"
                else:
                    tlhng += "}$"
            
            else:
                print("Ignoring", repr(word), file=sys.stderr)

            continue

        if not word:
            continue
        
        if not word_pattern.fullmatch(word):
            print("Not Klingon:", repr(word), file=sys.stderr)
            tlhng += word
            continue

        syllables = yajwiz.split_to_syllables(word)
        
        word_tlhng = ""
        for syllable in syllables:
            syllable = syllable.replace("'", "z").replace("q", "k")
            if syllable not in mapping:
                print("Syllable not found in font: "+repr(syllable)+" (line: " + repr(line) + ")", file=sys.stderr)
                tlhng += word
                break

            word_tlhng += chr(mapping[syllable])
        
        else:
            tlhng += word_tlhng
    
    return tlhng

def main():
    parser = argparse.ArgumentParser(description="Convert Markdown to tlhIngngutlh Mango")
    parser.add_argument("-i", "--input", help="Input file", type=argparse.FileType("r"), default=sys.stdin)
    parser.add_argument("-o", "--output", help="Output file", type=argparse.FileType("w"), default=sys.stdout)
    parser.add_argument("-m", "--mapping", help="Mapping file", type=argparse.FileType("r"), default="mapping.json")
    args = parser.parse_args()

    with args.mapping as f:
        mapping = json.load(f)
    
    print(f"""
set("min_word_gap", 0)
addfont("tlhng", "tlhIngngutlh HanDI', monospace")
set("font", "tlhng")
set("smart_page_breaks", false)

vspace(130)
ctitle:splitchars:|{line2tlhng("lutmey ngaj", mapping)}
csubsubsubtitle:splitchars:|{line2tlhng("gherta' 'Iy'qa", mapping)}
newpage
""", file=args.output)

    chapters = []
    output = ""
    
    pg = ""
    for line in args.input:
        if line.strip() in ["***", ""] and pg.strip():
            output += "pg:splitchars:| " + pg + "\n"
            pg = ""
        
        if line.strip() == "***":
            output += "hline\n"
            continue
        
        if line.strip() == "":
            continue

        heading = 0
        while line.startswith("#"):
            line = line[1:]
            heading += 1
        
        t = line2tlhng(line, mapping)
        
        if heading == 0:
            pg += t
        
        elif heading == 1:
            chapters.append(t)
            output += "newpage\ntitle:splitchars:| " + t + "\n"
        
        elif heading == 2:
            output += "subtitle:splitchars:| " + t + "\n"
        
        elif heading == 3:
            output += "subsubtitle:splitchars:| " + t + "\n"
        
        elif heading == 4:
            output += "subsubsubtitle:splitchars:| " + t + "\n"
    
    if pg:
        output += "pg:splitchars:| " + pg + "\n"
        pg = ""
    
    print("title:splitchars:| " + line2tlhng("lutmey tetlh", mapping), file=args.output)
    
    for chapter in chapters:
        print(f"row(\"\", splitchars(\"{chapter}\"))", file=args.output)
    
    print(output, file=args.output)

if __name__ == "__main__":
    main()