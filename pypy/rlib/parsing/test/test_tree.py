import py

from pypy.rlib.parsing.tree import Nonterminal, Symbol
from pypy.rlib.parsing.lexer import Token, SourcePos

class TestTreeAppLevel(object):

    def test_nonterminal_simple(self):
        pos = SourcePos(1,2,3)
        tree = Nonterminal(symbol="a", 
            children=[
                Symbol(symbol="b", 
                    additional_info="b", 
                    token=Token(name="B",
                        source="b",
                        source_pos=pos))])
        assert tree.getsourcepos() == pos
        
    def test_nonterminal_nested(self):
        pos = SourcePos(1,2,3)
        tree = Nonterminal(symbol="a", 
            children=[
                Nonterminal(symbol="c",
                    children=[
                       Symbol(symbol="b", 
                            additional_info="b", 
                            token=Token(name="B",
                                source="b",
                                source_pos=pos))])])
        assert tree.getsourcepos() == pos
    
    def test_nonterminal_simple_empty(self):
        tree = Nonterminal(symbol="a", 
            children=[])
        assert len(tree.children) == 0 # trivial
        py.test.raises(IndexError, tree.getsourcepos)

    def test_nonterminal_nested_empty(self):
        tree = Nonterminal(symbol="a", 
            children=[Nonterminal(symbol="c",
            children=[Nonterminal(symbol="c",
            children=[Nonterminal(symbol="c",
            children=[Nonterminal(symbol="c",
            children=[Nonterminal(symbol="c",
            children=[Nonterminal(symbol="c",
            children=[])])])])])])])
        assert len(tree.children) != 0 # the not-so-trivial part.
        py.test.raises(IndexError, tree.getsourcepos)

class BaseTestTreeTranslated(object):
    
    def compile(self, f):
        raise NotImplementedError
    
    def test_nonterminal_simple_empty(self):
        def foo():
            tree = Nonterminal(symbol="a", 
                children=[])
            try:
                return tree.getsourcepos()
            except IndexError:
                return -42
        f = self.compile(foo)
        assert f() == -42

    def test_nonterminal_nested_empty(self):
        def foo():
            tree = Nonterminal(symbol="a", 
                children=[Nonterminal(symbol="c",
                children=[Nonterminal(symbol="c",
                children=[Nonterminal(symbol="c",
                children=[Nonterminal(symbol="c",
                children=[Nonterminal(symbol="c",
                children=[Nonterminal(symbol="c",
                children=[])])])])])])])
            try:
                return tree.getsourcepos()
            except IndexError:
                return -42
        f = self.compile(foo)
        assert f() == -42


class TestTreeTranslatedLLType(BaseTestTreeTranslated):

    def compile(self, f):
        from pypy.translator.c.test.test_genc import compile
        return compile(f, [])

class TestTreeTranslatedOOType(BaseTestTreeTranslated):
    
    def compile(self, f):
        py.test.skip("XXX fix me maybe")
        from pypy.translator.cli.test.runtest import compile_function
        return compile_function(f, [], auto_raise_exc=True, exctrans=True)


