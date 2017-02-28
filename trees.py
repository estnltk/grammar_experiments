import itertools
from collections import defaultdict
from typing import Dict, List, Tuple

import networkx as nx
import numpy as np
import pandas as pd
import toolz


class Node:
    def __init__(self, span, name, weight = 1):
        self.span = span
        self.start = span[0]
        self.end = span[1]
        self.name = name

        self.weight = weight

    def __hash__(self):
        return hash((self.span, self.name))

    def __eq__(self, other):
        return self[0] == other[0] and self[1] == other[1]

    def __getitem__(self, item):
        return (self.span, self.name)[item]

    def __lt__(self, other):
        return self.span < other[0]

    def __gt__(self, other):
        return self.span > other[0]


    def __str__(self):
        return 'N({span}, {name}, {weight:.2f})'.format(span = self.span, name = self.name, weight=self.weight)

    def __len__(self):
        return 2

    def __repr__(self):
        return str(self)

START = Node((float('-inf'), float('-inf')), 'START')
END = Node((float('inf'), float('inf')), 'END')


class Grammar:
    def __init__(self, *, start_symbol, rules):
        self.rules = tuple(rules)
        self.start_symbol = start_symbol
        self.nonterminals = frozenset(i['lhs'] for i in rules)

        terminals = set()
        for i in (set(i.rhs) for i in self.rules):
             terminals.update(i)
        terminals -= self.nonterminals

        self.terminals = frozenset(terminals)
        self.nonterminal_dependency_order = tuple(self.get_rule_application_order())

    def get_rule_application_order(self) -> List[str]:
        rules_deps = dict(
            (j, set(itertools.chain(*i)) - self.terminals) for j, i in [(k, (i['rhs'] for i in v)) for k, v in
                                                                        toolz.groupby(lambda x: x['lhs'],
                                                                                      self).items()])
        order = []
        while len(order) != len(self.nonterminals):
            for k, v in rules_deps.items():
                if not v and k not in order:
                    order.append(k)
                    break
                else:
                    for _ in order:
                        rules_deps[k] -= set(order)
        return order


    def get_rule(self, lhs, rhs):
        for rule in self.rules:
            if rule.lhs == lhs.name and len(rhs)==len(rule.rhs) and [(a==b.name) for a,b in zip(rule.rhs, rhs)]:
                return rule
        return None

    def __getitem__(self, key):
        if key in self.nonterminals:
            return [i for i in self.rules if i.lhs == key]
        else:
            return self.rules[key]

    def __str__(self):
        rules = '\n\t'.join([str(i) for i in self.rules])
        return '''
Grammar:
\tstart symbol:{start},
\tterminals:{terminals}
\tnonterminals:{nonterminals}
Rules:
\t{rules}
'''.format(start=self.start_symbol, rules=rules, terminals=self.terminals, nonterminals=self.nonterminals)

    def __repr__(self):
        return str(self)


class Rule:
    def __init__(self, lhs, rhs, weight: int=None):
        self.lhs = lhs
        self.rhs = tuple(rhs)
        if weight is None:
            self.weight = len(rhs)
        else:
            self.weight = weight

    def __getitem__(self, key):
        if key == 'lhs':
            return self.lhs
        elif key == 'rhs':
            return self.rhs
        else:
            raise AssertionError

    def __str__(self):
        return '{lhs} -> {rhs}\t: {weight}'.format(lhs=self.lhs, rhs=' '.join(self.rhs), weight=self.weight)

    def __repr__(self):
        return str(self)





def graph_from_document(rows: Dict[str, List[Tuple[int, int]]]) -> nx.DiGraph:
    res = get_dense_matrix(rows)
    items = get_elementary_nodes(rows)
    df = matrix_to_dataframe(res, items)
    edges = edges_from_dataframe(df, items)
    graph = nx.DiGraph()
    graph.add_nodes_from(items)
    graph.add_edges_from(edges)

    create_entry_and_exit_nodes(graph, items)
    remove_shortcuts(graph)
    add_blanks(graph)
    remove_shortcuts(graph)
    return graph


def edges_from_dataframe(df, items):
    fixed = df.groupby('e1').apply(lambda x: x.groupby('n2').apply(lambda y: y[y.s2 <= y.e2.min()]))
    try:
        fixed['through_blank'] = fixed.s2 != fixed.e1
        edges = []
        for a, b, bl in zip(fixed.a.values, fixed.b.values, fixed.through_blank):
            edges.append((items[a], items[b]))
        return edges
    except AttributeError:
        raise  AssertionError('no items in df')

def create_entry_and_exit_nodes(graph: nx.DiGraph, items):
    graph.add_nodes_from([START, END])
    items = sorted(items)
    graph.add_edge(START, items[0])
    for node in (set(graph.nodes()) - {START}) - nx.descendants(graph, START):
        graph.add_edge(START, node)
    graph.add_edge(items[-1], END)
    for node in (set(graph.nodes()) - {END}) - nx.ancestors(graph, END):
        graph.add_edge(node, END)


def matrix_to_dataframe(res, items):
    vals = []
    for a, b in zip(*np.where(res)):
        (s1, e1), n1 = items[a]
        (s2, e2), n2 = items[b]
        vals.append((n1, s1, e1, n2, s2, e2, a, b))
    return pd.DataFrame.from_records(vals, columns='n1 s1 e1 n2 s2 e2 a b'.split())


def get_elementary_nodes(rows):
    items = []

    for row_name, indices in rows.items():
        for (a, b) in indices:
            items.append(Node((a, b), row_name))
    return items

def get_dense_matrix(rows):
    mapping, reverse_mapping = get_dense_mapping(rows)
    b_rows = []
    names = []
    for row_name, indices in rows.items():
        for (a, b) in indices:
            names.append(row_name)
            x = np.zeros(shape=len(reverse_mapping) - 1, dtype=np.bool)
            x[mapping[a]: mapping[b]] = 1
            b_rows.append(x)
    b_rows = np.array(b_rows)
    start_index = []
    end_index = []
    for row in b_rows:
        wh = np.where(row)[0]
        start_index.append(wh[0])
        end_index.append(wh[-1])
    start_index = np.array(start_index)
    res = np.zeros(shape=(len(start_index), len(start_index)), dtype=np.bool)
    for row, idx in zip(range(res.shape[0]), end_index):
        res[row] = start_index > idx
    return res


def get_dense_mapping(rows):
    by_start = defaultdict(list)
    by_end = defaultdict(list)
    for k, v in rows.items():
        for s, e in v:
            by_start[s].append(((s, e), k))
            by_end[e].append(((s, e), k))
    starts = set(by_start.keys())
    ends = set(by_end.keys())
    mapping = {}
    for idx, i in enumerate(sorted(starts | ends)):
        mapping[i] = idx
    reverse_mapping = [v for (v, _) in sorted(mapping.items())]
    return mapping, reverse_mapping


def add_blanks(graph: nx.DiGraph) -> None:
    for node in graph.nodes():
        if node[-1] != '_' and node != START:
            (s1, e1), name = node
            for succ in graph.successors(node):
                (s2, e2), _ = succ
                if s2 - e1 > 1 and succ != END:
                    nnode = Node((e1, s2), "_")
                    graph.add_node(nnode)
                    graph.add_edges_from([(node, nnode), (nnode, succ)])
                    graph.remove_edge(node, succ)


def remove_shortcuts(graph: nx.DiGraph) -> None:
    '''
    The aim is to remove edges from the graph without affecting the reachability matrix.
    Transitive reduction of a DAG
    '''


    nodelist = graph.nodes()
    adjacency_matrix = nx.to_numpy_matrix(graph, nodelist=nodelist) == 1
    reachability_matrix = nx.floyd_warshall_numpy(graph, nodelist=nodelist) == 1
    transitive_reduction = (adjacency_matrix & ~(adjacency_matrix @ reachability_matrix))

    to_remove = (adjacency_matrix ^ transitive_reduction)

    for a,b in zip(*np.where(to_remove)):
        graph.remove_edge(nodelist[a], nodelist[b])


# # see osa arvutas reeglitest kõik võimalikud teed
# rules2 = defaultdict(list)
# for k in rules:
#     rules2[k['lhs']].append(k['rhs'])
# stack = rules2[start][:]
# done = []
# while stack:
#     line = stack.pop()
#     new = []
#     for elem in line:
#         if elem in nonterminals:
#             new.append(rules2[elem])
#         elif elem in terminals:
#             new.append([[elem]])
#         else:
#             raise AssertionError('What kind of symbol is this?')
#     news = (
#         list(list(itertools.chain(*i)) for i in (itertools.product(*new)))
#     )
#     for i in news:
#         if set(i) & nonterminals == set():
#             done.append(i)
#         else:
#             stack.append(i)


# In[217]:

def get_valid_paths(graph: nx.DiGraph, rule:Rule):
    new_graph = graph.copy()

    new_graph.remove_nodes_from([START, END])
    new_graph.add_nodes_from([START, END])

    entries, exits = [], []

    for node in new_graph.nodes():
        if node[-1] == rule.rhs[0]:
            entries.append(node)
        if node[-1] == rule.rhs[-1]:
            exits.append(node)

    new_graph.add_edges_from([(START, i) for i in entries])
    new_graph.add_edges_from([(i, END) for i in exits])
    paths = [[START]]
    dones_paths = []
    etalon = rule.rhs[:]

    while paths:
        current_path = paths.pop(0)
        for succ in new_graph.successors(current_path[-1]):
            if len(current_path) <= len(etalon):
                if succ[-1] == etalon[len(current_path) - 1]:
                    paths.append(current_path + [succ])
            elif len(current_path) == len(etalon) + 1 and succ == END:
                dones_paths.append(current_path[1:])
    return dones_paths


def get_nonterminal_nodes(graph: nx.DiGraph, grammar: 'Grammar'):
    g2 = graph.copy()
    order = grammar.nonterminal_dependency_order

    nodes = defaultdict(list)
    for nonterminal in order:
        for rule in grammar[nonterminal]:
            paths = get_valid_paths(g2, rule)
            for path in paths:
                (s1, e1), n1 = path[0]
                (s2, e2), n2 = path[-1]
                node = Node((s1, e2), nonterminal)
                node.weight = rule.weight

                nodes[node].append((rule, path))
                g2.add_node(node)
                g2.add_edges_from(
                    [(i, node) for i in g2.predecessors(path[0])] +
                    [(node, i) for i in g2.successors(path[-1])])
    return nodes


def choose_parse_tree(nodes: Dict[Node, List[Tuple[Rule, Node]]], grammar:Grammar) -> nx.DiGraph:

    if not len([i for i in nodes.keys() if i.name == grammar.start_symbol])  >= 1:
        raise AssertionError('Parse failed, change grammar.')

    #we'll choose the starting symbol with the most cover
    #this is negotiable
    print([i for i in nodes.keys() if i.name == grammar.start_symbol])
    stack = [
        max((i for i in nodes.keys() if i.name == grammar.start_symbol), key=lambda x:x.weight)
             ]
    graph = nx.DiGraph()
    while stack:
        node = stack.pop(0)
        graph.add_node(node)
        if nodes[node]:
            _, children = max((rule.weight, children) for (rule, children) in nodes[node])
            graph.add_edges_from([(node, i) for i in children])
            stack.extend(children)
    return graph


def document_to_graph(document, grammar):
    graph = graph_from_document(document)
    nonterminal_nodes = get_nonterminal_nodes(graph, grammar)
    return  choose_parse_tree(nonterminal_nodes, grammar)


# gg = document_to_graph(document, grammar)
# for (s,e), name in gg.nodes():
#     print(s,e,name)
#
# nx.drawing.nx_pydot.write_dot(gg, 'hsptl2.dot')
