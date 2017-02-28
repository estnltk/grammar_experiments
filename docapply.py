from itertools import chain

import estnltk
import networkx as nx

from trees import Rule, Grammar, document_to_graph, graph_from_document, get_nonterminal_nodes, choose_parse_tree

import random

INF = 10


class Expr:
    def __init__(self, nodes, frm=1, to=1):
        self.nodes = nodes
        self.frm = frm
        self.to = to

    def __repr__(self):
        return '!{self.nodes}'.format(self=self)


class Or:
    def __init__(self, left, right):
        self.left = left
        self.right = right

    @property
    def nodes(self):
        return self.left, self.right

    def __repr__(self):
        return 'OR({self.left}, {self.right})'.format(self=self)


import regex as re


class Token:
    def __init__(self, typ, value):
        self.typ = typ
        self.value = value

    def __repr__(self):
        return '{value}'.format(typ=self.typ, value=self.value)


def tokenize(s):
    token_specification = [
        ('token', r'(?P<token>[[:alpha:]_][[:alpha:][:digit:]_]*)'),
        ('meta', r'[?*+|]'),
        ('startbr', r'\('),
        ('endbr', r'\)'),
        ('arrow', r'->'),
        ('brackets', r'{(?P<from>[0-9]+), *(?P<to>[0-9]+)}'),
        ('weight', r':[0-9]+'),
        ('SKIP', r'[ \n\t]+'),

    ]
    tok_regex = '|'.join('(?P<%s>%s)' % pair for pair in token_specification)
    get_token = re.compile(tok_regex).match
    pos = 0
    mo = get_token(s)
    while mo is not None:
        typ = mo.lastgroup
        if typ != 'SKIP':
            val = mo.group(typ)
            yield Token(typ, val)
        pos = mo.end()
        mo = get_token(s, pos)
    if pos != len(s):
        raise RuntimeError('Unexpected character %r' % (s[pos]))


def parse(lst, frm=0, nst=0):
    res = []

    to = None
    idx = -1
    for idx, i in enumerate(lst):
        if to is not None:
            if to > idx:
                continue
            else:
                to = None

        if i.value == '(':
            to, new = parse(lst[idx + 1:], idx + frm, nst + 1)
            res.append(Expr(new))
        elif i.value == ')':
            if nst != 0:
                return idx + frm + 1, res
            else:
                res[-1] = Expr([res[-1]])
        else:
            if i.typ == 'token':
                res.append(Expr([i]))
            elif i.value == '|':
                res.append(i)
            elif i.value == '+':
                res[-1].frm = 1
                res[-1].to = INF
            elif i.value == '*':
                res[-1].frm = 0
                res[-1].to = INF
            elif i.value == '?':
                res[-1].frm = 0
                res[-1].to = 1
            elif i.typ == 'brackets':
                res[-1].frm, res[-1].to = [int(j.strip()) for j in i.value[1:-1].split(',')]
    return idx, Expr(res)


def to_tree(statements):
    #     statements = '''a ->B | (C | D E F G)*'''
    c = 100

    for token in tokenize(statements):
        c -= 1
        if c < 0:
            break

    start, arrow, *rest, weight = [token for token in tokenize(statements)]
    if weight.typ != 'weight':
        rest.append(weight)

    assert start.typ == 'token'
    assert arrow.typ == 'arrow'

    p = parse(rest)[1]

    return p


def shunt(tree):
    stack = tree.nodes[:]
    if (type(tree.nodes[0]) == Token):
        return tree

    news = []
    while stack:
        i = stack.pop(0)
        if isinstance(i, Token) and i.value == '|':
            news.append(Or(news.pop(-1), shunt(stack.pop(0))))
        else:
            news.append(shunt(i))
    tree.nodes = news

    return tree


class ORR:
    def __init__(self, *nodes):
        self.nodes = nodes

    def __repr__(self):
        return 'OR({nodes})'.format(nodes=' '.join(str(i) for i in self.nodes))


def unwrap(t):
    results = []
    if isinstance(t, Token):
        return t

    for i in t.nodes:
        if isinstance(i, Or):
            results.append(
                ORR(*[unwrap(Expr([i.left])), unwrap(Expr([i.right]))])
            )



        elif isinstance(i, Expr) and i.to != 1:
            tmp = []
            for j in range(i.frm, i.to + 1):
                if len(i.nodes) == 1 and isinstance(i.nodes[0], Token):
                    tmp.append(([i.nodes[0]] * j))
                else:

                    tmp.append(
                        list(chain(*[unwrap(Expr(nodes=[k], frm=i.frm, to=i.to)) for k in i.nodes] * j))
                    )
            results.append(ORR(*tmp))


        elif isinstance(i, Expr) and i.to == 1:

            if i.frm == 1:
                results.extend(
                    unwrap(i)
                )
            elif i.frm == 0:
                results.append(
                    ORR([], unwrap(i))
                )

        elif isinstance(i, Token):
            results.append(i)

    return results


def fixup(g, x, lvl=0):
    if x == []:
        ff = ('epsilon', lvl, random.random())
        return ff, ff

    fst = None
    prev = None
    for idx, i in enumerate(x):
        if isinstance(i, Token):
            new = (i, lvl, idx, random.random())
            if not fst:
                fst = new
            g.add_node(new)
            if prev:
                g.add_edge(prev, new)
            prev = new
        else:
            # must be ORR
            new = ('OR', idx, lvl, random.random())
            if not fst:
                fst = new

            if prev:
                g.add_edge(prev, new)
            g.add_node(new)
            prev = (('ENDOR', idx, lvl, random.random()))
            g.add_node(prev)

            for j in i.nodes:
                r = fixup(g, j, lvl + 1)
                enter, exit = r
                g.add_edge(exit, prev)
                g.add_edge(new, enter)

    return fst, prev


def get_rhs_set(line):
    t = shunt(to_tree(line))

    x = unwrap(t)
    g = nx.DiGraph()

    fst, last = fixup(g, x)
    START,  END = ('start', 0), ('end', 0)
    g.add_edge(
    START, fst
    )
    g.add_edge(
    last, END
    )

    res = set()
    for i in nx.all_simple_paths(g, START, END):
        res.add(' '.join([j[0].value for j in i if isinstance(j[0], Token)]))
    return res



def layers_to_document(text, layers):
    document = {}

    for layer in layers:
        document[layer] = [(i['start'], i['end']) for i in text[layer]]

    return document
