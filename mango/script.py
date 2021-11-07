import re
from typing import Callable, Dict, List, Literal, NamedTuple, Set, Union


TokenType = Literal["str", "float", "ident", "punct"]

class Token(NamedTuple):
    line: int
    col: int
    type: TokenType
    text: str

class TokenList(NamedTuple):
    tokens: List[Token]

    def checkEOF(self):
        if not self.tokens:
            raise RuntimeError("Unexpected EOF")

    def peek(self, n: int = 0):
        return self.tokens[n]
    
    def isNext(self, type: TokenType, *texts: str, n: int = 0):
        if not self.hasNext(n):
            return False
        
        token = self.peek(n)
        return token.type == type and token.text in texts
    
    def accept(self, type: TokenType, *texts: str):
        if not self.isNext(type, *texts):
            raise RuntimeError(f"Unexpected token {repr(self.peek())}, expected {repr(texts)}")
    
        return self.pop()
    
    def pop(self):
        return self.tokens.pop(0)
    
    def hasNext(self, n: int = 0):
        return len(self.tokens) > n

def lexer(text: str) -> TokenList:
    current_ident = ""
    tokens: List[Token] = []
    line = 1
    col = 1

    def pushIdent():
        nonlocal current_ident
        if current_ident:
            if re.fullmatch(r"[0-9]+(\.[0-9]+)?(e[0-9]+)?", current_ident):
                tokens.append(Token(line, col-len(current_ident), "float", current_ident))
            
            else:
                tokens.append(Token(line, col-len(current_ident), "ident", current_ident))
            
            current_ident = ""
    
    def parseString(start, end):
        nonlocal line, col
        string = ""
        startcol = col
        char = chars.pop(0); col += 1
        while char != end:
            if char == "\n":
                line += 1
                col = 1
            
            string += char
            char = chars.pop(0); col += 1
        else:
            if char == "\n":
                line += 1
                col = 1
        
        tokens.append(Token(line, startcol, "str", string))

    chars = list(text)
    while chars:
        char = chars.pop(0); col += 1
        if char == "\n":
            pushIdent()
            line += 1
            col = 1
        
        elif char.isspace():
            pushIdent()
        
        elif char in "(){};,+-*/%=<>!:":
            pushIdent()
            op = char
            if chars:
                if char == "<" and chars[0] == "=":
                    op = "<="
                    chars.pop(0); col += 1
                
                elif char == ">" and chars[0] == "=":
                    op = ">="
                    chars.pop(0); col += 1
                
                elif char == "!" and chars[0] == "=":
                    op = "!="
                    chars.pop(0); col += 1
                
                elif char == "=" and chars[0] == "=":
                    op = "=="
                    chars.pop(0); col += 1

            tokens.append(Token(line, col, "punct", op))
        
        elif char == "`":
            pushIdent()
            parseString("`", "`")
        
        elif char == "'":
            pushIdent()
            parseString("'", "'")
        
        elif char == '"':
            pushIdent()
            parseString('"', '"')
        
        elif char == "|":
            pushIdent()
            parseString("|", "\n")
        
        else:
            current_ident += char
    
    pushIdent()
    return TokenList(tokens)

ExprValue = Union[float, str, List["ExprValue"], None]

BUILTINS: Dict[str, Callable] = {
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "<": lambda a, b: a < b,
    ">": lambda a, b: a > b,
    "<=": lambda a, b: a <= b,
    ">=": lambda a, b: a >= b,
    "+": lambda a, b: a + b,
    "-": lambda a, b: a - b,
    "*": lambda a, b: a * b,
    "/": lambda a, b: a / b,
    "%": lambda a, b: a % b,
    "print": lambda *a: print(*a),
    "replace": lambda a, b, s: s.replace(a, b),
    "sub": re.sub,
    "true": lambda: True,
    "false": lambda: False,
}

class Frame(NamedTuple):
    functions: Dict[str, Callable]

class Interpreter:
    frames: List[Frame] = [Frame(BUILTINS.copy())]

    def getFunctions(self):
        ans = {}
        for frame in self.frames:
            ans.update(frame.functions)
        
        return ans
    
    def pushFrame(self):
        self.frames.append(Frame({}))
    
    def popFrame(self):
        self.frames.pop()

class BlockTree(NamedTuple):
    exprs: List["ExprTree"]

    def eval(self, itpt: Interpreter) -> ExprValue:
        ans = []
        for expr in self.exprs:
            v = expr.eval(itpt)
            if v is not None:
                ans.append(v)
        
        return ans

class FunctionCallTree(NamedTuple):
    func: str
    args: List["ExprTree"]

    def eval(self, itpt: Interpreter) -> ExprValue:
        if len(self.args) == 3 and self.func == "if":
            cond = self.args[0].eval(itpt)
            if cond:
                return self.args[1].eval(itpt)
            
            else:
                return self.args[2].eval(itpt)
        
        elif len(self.args) == 3 and self.func == "for":
            varname = self.args[0].eval(itpt)
            items = self.args[1].eval(itpt)
            ans = []
            for item in list(items):
                itpt.pushFrame()
                itpt.frames[-1].functions[varname] = lambda: item
                v = self.args[2].eval(itpt)
                if v is not None:
                    ans.append(v)
                
                itpt.popFrame()
            
            return ans
        
        elif len(self.args) == 3 and self.func == "def":
            funcname = self.args[0].eval(itpt)
            params = self.args[1].eval(itpt)
            body = self.args[2]

            def execFunc(*args):
                itpt.pushFrame()
                for param, arg in zip(params, args):
                    itpt.frames[-1].functions[param] = lambda: arg
                
                v = body.eval(itpt)
                itpt.popFrame()
                return v
            
            itpt.frames[-1].functions[funcname] = execFunc
            return None

        functions = itpt.getFunctions()
        if self.func in functions:
            return functions[self.func](*[a.eval(itpt) for a in self.args])
        
        else:
            raise RuntimeError(f"Unknown function {self.func}")

class FloatTree(NamedTuple):
    value: float

    def eval(self, _itpt: Interpreter) -> ExprValue:
        return self.value

class StringTree(NamedTuple):
    value: str

    def eval(self, _itpt: Interpreter) -> ExprValue:
        return self.value

ExprTree = Union[FunctionCallTree, FloatTree, StringTree, BlockTree]

def parseBlock(tokens: TokenList) -> BlockTree:
    ans = BlockTree([])
    while tokens.hasNext() and not tokens.isNext("punct", "}"):
        ans.exprs.append(parseExpr(tokens))
    
    return ans

def parseExpr(tokens: TokenList) -> ExprTree:
    return parseOperatorExpr(tokens, OPERATORS)

OPERATORS = [
    {"==", "!=", "<", ">", "<=", ">="},
    {"+", "-"},
    {"*", "/", "%"},
]

def parseOperatorExpr(tokens: TokenList, operators: List[Set[str]]) -> ExprTree:
    if not operators:
        return parsePrimaryExpr(tokens)
    
    ans = parseOperatorExpr(tokens, operators[1:])
    while tokens.hasNext() and tokens.peek().type == "punct" and tokens.peek().text in operators[0]:
        op = tokens.pop().text
        ans = FunctionCallTree(op, [ans, parseOperatorExpr(tokens, operators[1:])])
    
    return ans

def parsePrimaryExpr(tokens: TokenList) -> ExprTree:
    tokens.checkEOF()

    if tokens.isNext("punct", "{"):
        tokens.pop()
        block = parseBlock(tokens)
        tokens.accept("punct", "}")
        return block
    
    elif tokens.peek().type == "float":
        return FloatTree(float(tokens.pop().text))
    
    elif tokens.peek().type == "str":
        return StringTree(tokens.pop().text)
    
    elif tokens.peek().type == "ident":
        func = tokens.pop().text
        args = []
        if tokens.isNext("punct", "("):
            tokens.pop()
            while not tokens.isNext("punct", ")"):
                args.append(parseExpr(tokens))
                if tokens.isNext("punct", ","):
                    tokens.pop()
            
            tokens.accept("punct", ")")
        
        elif tokens.isNext("punct", ":"):
            tokens.pop()
            args.append(parseExpr(tokens))
            while tokens.isNext("punct", ","):
                tokens.pop()
                args.append(parseExpr(tokens))
        
        return FunctionCallTree(func, args)
    
    else:
        raise RuntimeError(f"Unexpected token {repr(tokens.pop())}, expected expression")