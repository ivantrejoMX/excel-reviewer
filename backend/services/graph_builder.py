from __future__ import annotations
import sys
from collections import defaultdict

import networkx as nx
from openpyxl import Workbook

from backend.services.formula_tokenizer import extract_refs


def build_dependency_graph(wb: Workbook) -> nx.DiGraph:
    """
    Build a directed graph where an edge A→B means "cell A's formula references cell B".
    Node IDs are normalized as "SheetName!A1".
    """
    G = nx.DiGraph()
    for sheet in wb.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                val = cell.value
                if not isinstance(val, str) or not val.startswith("="):
                    continue
                cell_id = f"{sheet.title}!{cell.coordinate}"
                G.add_node(cell_id)
                for dep in extract_refs(sheet.title, val):
                    G.add_edge(cell_id, dep)
    return G


def _iterative_has_cycle(G: nx.DiGraph) -> bool:
    """DFS cycle check (iterative, avoids Python recursion limit)."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {}

    for start in G.nodes():
        if color.get(start, WHITE) != WHITE:
            continue
        stack = [(start, iter(G.successors(start)))]
        color[start] = GRAY
        while stack:
            node, children = stack[-1]
            try:
                child = next(children)
                c = color.get(child, WHITE)
                if c == GRAY:
                    return True
                if c == WHITE:
                    color[child] = GRAY
                    stack.append((child, iter(G.successors(child))))
            except StopIteration:
                color[node] = BLACK
                stack.pop()
    return False


def find_circular_references(G: nx.DiGraph) -> list[list[str]]:
    """Return all elementary cycles in the graph (each as a list of cell IDs)."""
    if not _iterative_has_cycle(G):
        return []
    return list(nx.simple_cycles(G))


def find_relay_chains(G: nx.DiGraph, passthroughs: set[str]) -> list[list[str]]:
    """
    Find chains of pure-passthrough cells: C→B→A where every hop is a passthrough.
    Returns chains of length >= 2 (at least one intermediate relay node).
    """
    chains: list[list[str]] = []
    visited_as_chain_member: set[str] = set()

    for node in passthroughs:
        if node in visited_as_chain_member:
            continue
        # Walk backwards (who depends on this node and is also a passthrough?)
        chain = [node]
        current = node
        while True:
            successors = list(G.successors(current))
            # A pure passthrough has exactly one reference
            if len(successors) != 1:
                break
            target = successors[0]
            if target not in passthroughs:
                chain.append(target)  # source (non-passthrough end)
                break
            chain.append(target)
            current = target

        if len(chain) >= 3:  # at least one relay hop
            chains.append(chain)
            visited_as_chain_member.update(chain)

    return chains
