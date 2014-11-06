"""
This module performs schematic drawing using circuitikz from a netlist.

>>> from lcapy import Schematic
>>> sch = Schematic()
>>> sch.add('P1 1 0.1; down')
>>> sch.add('R1 3 1; right')
>>> sch.add('L1 2 3; right')
>>> sch.add('C1 3 0; down')
>>> sch.add('P2 2 0.2; down')
>>> sch.add('W 0 0.1; right')
>>> sch.add('W 0.2 0.2; right')
>>> sch.draw()

Copyright 2014 Michael Hayes, UCECE
"""

from __future__ import print_function
import numpy as np
import re

__all__ = ('Schematic', )


# Mapping of component names to circuitikz names.   The keys define
# the allowable component names.
cpt_type_map = {'R' : 'R', 'C' : 'C', 'L' : 'L', 
                'Vac' : 'sV', 'Vdc' : 'V', 'Iac' : 'sI', 'Idc' : 'I', 
                'V' : 'V', 'I' : 'I', 'v' : 'V', 'i' : 'I',
                'TF' : 'transformer', 'P' : 'open', 'port' : 'open',
                'W' : 'short', 'wire' : 'short'}


# Regular expression alternate matches stop with first match so need
# to have longer names first.
cpt_types = cpt_type_map.keys()
cpt_types.sort(lambda x, y: cmp(len(y), len(x)))

cpt_type_pattern = re.compile(r'(%s)(\w)?' % '|'.join(cpt_types))


def longest_path(all_nodes, from_nodes):
    """all_nodes is an iterable for all the nodes in the graph, from_nodes
    is a directory indexed by node that stores a tuple of tuples.  The
    first tuple element is the parent node and the second element is
    the minimium size of the component connecting the nodes.
    """

    memo = {}

    def get_longest(to_node):

        if to_node in memo:
            return memo[to_node]

        best = 0
        for from_node, size in from_nodes[to_node]:
            best = max(best, get_longest(from_node) + size)

        memo[to_node] = best

        return best

    length, node = max([(get_longest(to_node), to_node) for to_node in all_nodes])
    return length, node, memo


class Node(object):

    def __init__(self, name):

        self.name = name
        self.pos = None
        self.port = False
        parts = name.split('_')
        self.rootname = parts[0]
        self.primary = len(parts) == 1
        self.list = []

    
    def append(self, elt):

        if elt.cpt_type in ('P', 'port', 'open'):
            self.port = True

        self.list.append(elt)


class NetElement(object):

    cpt_type_counter = 0

    def __init__(self, name, node1, node2, *args, **opts):

        match = cpt_type_pattern.match(name)

        if not match:
            raise ValueError('Unknown component %s' % name)

        cpt_type = match.groups()[0]
        id = match.groups()[1]

        if id is None:
            NetElement.cpt_type_counter += 1
            id = '#%d' % NetElement.cpt_type_counter
            name = cpt_type + id

        node1 = node1.replace('.', '_')
        node2 = node2.replace('.', '_')

        cpt_type_orig = cpt_type
        if args != ():
            if cpt_type == 'V' and args[0] == 'ac':
                cpt_type = 'Vac'
            elif cpt_type == 'V' and args[0] == 'dc':
                cpt_type = 'Vdc'
            elif cpt_type == 'I' and args[0] == 'ac':
                cpt_type = 'Iac'
            elif cpt_type == 'I' and args[0] == 'dc':
                cpt_type = 'Idc'

            if cpt_type in ('Vdc', 'Vac', 'Idc', 'Iac') and args[0] in ('ac', 'dc'):
                args = args[1:]


        symbol = None
        self.symbol = symbol

        autolabel = symbol
        if autolabel is None:
            autolabel = cpt_type_orig + '_{' + id + '}'

        if cpt_type in ('P', 'port', 'W', 'wire') or autolabel.find('#') != -1:
            autolabel = ''
        else:
            autolabel = '$' + autolabel + '$'

        if not opts.has_key('dir'):
            opts['dir'] = None
        if not opts.has_key('size'):
            opts['size'] = 1

        if opts['dir'] is None:
            opts['dir'] = 'down' if cpt_type in ('port', 'P') else 'right'

        self.name = name
        self.cpt_type = cpt_type
        self.autolabel = autolabel
        self.nodes = (node1, node2)
        self.opts = opts


    def __repr__(self):

        str = ', '.join(arg.__str__() for arg in [self.name] + list(self.nodes))
        return 'NetElement(%s)' % str


    def __str__(self):

        return ' '.join(['%s' % arg for arg in (self.name, ) + self.nodes])



class Schematic(object):

    def __init__(self, filename=None):

        self.elements = {}
        self.nodes = {}
        self.vnodes = {}
        self.scale = 2

        if filename is not None:
            self.netfile_add(filename)


    def __getitem__(self, name):
        """Return component by name"""

        return self.elements[name]


    def netfile_add(self, filename):    
        """Add the nets from file with specified filename"""

        file = open(filename, 'r')
        
        lines = file.readlines()

        for line in lines:
            # Skip comments
            if line[0] in ('#', '%'):
                continue
            self.add(line.strip())


    def netlist(self):
        """Return the current netlist"""

        return '\n'.join([elt.__str__() for elt in self.elements.values()])


    def _node_add(self, node, elt):

        if not self.nodes.has_key(node):
            self.nodes[node] = Node(node)
        self.nodes[node].append(elt)

        vnode = self.nodes[node].rootname
        if not self.vnodes.has_key(vnode):
            self.vnodes[vnode] = {}
        if not self.vnodes[vnode].has_key(node):
            self.vnodes[vnode][node] = elt


    def _elt_add(self, elt):

        if self.elements.has_key(elt.name):
            print('Overriding component %s' % elt.name)     
            # Need to search lists and update component.
           
        self.elements[elt.name] = elt

        for node in elt.nodes:
            self._node_add(node, elt)
        

    def _opts_parse(self, str):

        opts = {'dir' : None, 'size' : 1}

        for part in str.split(','):
            part = part.strip()

            if part in ('up', 'down', 'left', 'right'):
                opts['dir'] = part
                continue

            fields = part.split('=')
            key = fields[0].strip()
            arg = fields[1].strip() if len(fields) > 1 else ''
            opts[key] = arg

        return opts


    def add(self, line):
        """The general form is: 'Name Np Nm symbol'
        where Np is the positive nose and Nm is the negative node.

        A positive current is defined to flow from the positive node
        to the negative node.
        """

        fields = line.split(';')

        str = fields[1] if len(fields) > 1 else ''

        opts = self._opts_parse(str)

        parts = fields[0].split(' ')
        elt = NetElement(*parts, **opts)

        self._elt_add(elt)



    def _make_graphs(self, dirs):

        cnodes = {}
        cnode_map = {}
        cnode = 0

        # Use components in orthogonal directions as constraints.  The
        # nodes of orthogonal components get combined into a
        # collective node.
        for m, elt in enumerate(self.elements.values()):
            if elt.opts['dir'] in dirs:
                continue

            n1, n2 = elt.nodes

            if cnode_map.has_key(n1) and cnode_map.has_key(n2) and cnode_map[n1] != cnode_map[n2]:
                raise ValueError('Conflict for elt %s' % elt)
                    
            if not cnode_map.has_key(n1) and not cnode_map.has_key(n2):
                cnode += 1
                cnode_map[n1] = cnode
                cnode_map[n2] = cnode
                cnodes[cnode] = [n1, n2]
            elif not cnode_map.has_key(n1):
                node = cnode_map[n2]
                cnode_map[n1] = node
                cnodes[node].append(n1)
            else:
                node = cnode_map[n1]
                cnode_map[n2] = node
                cnodes[node].append(n2)


        # Augment the collective nodes with the other nodes used by
        # components in the desired directions.
        for m, elt in enumerate(self.elements.values()):
            if elt.opts['dir'] not in dirs:
                continue

            n1, n2 = elt.nodes

            if not cnode_map.has_key(n1):
                cnode += 1
                cnode_map[n1] = cnode
                cnodes[cnode] = [n1]
            if not cnode_map.has_key(n2):
                cnode += 1
                cnode_map[n2] = cnode
                cnodes[cnode] = [n2]


        # Now form forward and reverse directed graphs using components
        # in the desired directions.
        graph = {}
        rgraph = {}
        for m in range(cnode + 1):
            graph[m] = []
            rgraph[m] = []

        for m, elt in enumerate(self.elements.values()):
            if elt.opts['dir'] not in dirs:
                continue

            m1, m2 = cnode_map[elt.nodes[0]], cnode_map[elt.nodes[1]]

            size = float(elt.opts['size'])

            if elt.opts['dir'] == dirs[0]:
                graph[m1].append((m2, size))
                rgraph[m2].append((m1, size))
            elif elt.opts['dir'] == dirs[1]:
                graph[m2].append((m1, size))
                rgraph[m1].append((m2, size))

        # Chain all potential start nodes to node 0.
        orphans = []
        rorphans = []
        for m in range(1, cnode + 1):
            if graph[m] == []:
                orphans.append((m, 0))
            if rgraph[m] == []:
                rorphans.append((m, 0))
        graph[0] = rorphans
        rgraph[0] = orphans

        if False:
            print(graph)
            print(rgraph)
            print(cnodes)
            print(cnode_map)


        # Find longest path through the graphs.
        length, node, memo = longest_path(graph.keys(), graph)
        length, node, memor = longest_path(graph.keys(), rgraph)

        pos = {}
        posr = {}
        posa = {}
        for cnode in graph.keys():
            if cnode == 0:
                continue

            for node in cnodes[cnode]:
                pos[node] = length - memo[cnode]
                posr[node] = memor[cnode]
                posa[node] = 0.5 * (pos[node] + posr[node])
        
        if False:
            print(pos)
            print(posr)
        return posa


    def _positions_calculate(self):

        # The x and y positions of a component node are determined
        # independently.  The principle is that each component has a
        # minimum size (usually 1 but changeable with the size option)
        # but its wires can be stretched.

        # When solving the x position, first nodes that must be
        # vertically aligned (with the up or down option) are combined
        # into a set.  Then the left and right options are used to
        # form a graph.  This graph is traversed to find the longest
        # path and in the process each node gets assigned the longest
        # distance from the root of the graph.  To centre components,
        # a reverse graph is created and the distances are averaged.

        xpos = self._make_graphs(('right', 'left'))
        ypos = self._make_graphs(('up', 'down'))

        coords = {}
        for node in xpos.keys():
            coords[node] = (xpos[node] * self.scale, ypos[node] * self.scale)

        for m, elt in enumerate(self.elements.values()):

            n1, n2 = elt.nodes

            elt.pos1 = coords[n1]
            elt.pos2 = coords[n2]

        self.coords = coords


    def _make_wires1(self, vnode):

        num_wires = len(vnode) - 1
        if num_wires == 0:
            return []

        wires = []

        # TODO: remove overdrawn wires...
        for n in range(num_wires):
            n1 = vnode.keys()[n]
            n2 = vnode.keys()[n + 1]
            
            wires.append(NetElement('W_', n1, n2))

        return wires


    def _make_wires(self):
        """Create implict wires between common nodes."""

        wires = []

        vnode_dir = self.vnodes

        for m, vnode in enumerate(vnode_dir.values()):
            wires.extend(self._make_wires1(vnode))
            
        return wires


    def _node_str(self, n1, n2, draw_nodes=True):

        if self.nodes[n1].port:
            node_str = 'o'
        else:
            node_str = '*' if draw_nodes and n1.find('_') == - 1 else ''
            
        node_str += '-'

        if self.nodes[n2].port:
            node_str += 'o'
        else:
            node_str += '*' if draw_nodes and n2.find('_') == - 1 else ''

        if node_str == '-':
            node_str = ''
        
        return node_str


    def tikz_draw(self, draw_labels=True, draw_nodes=True, label_nodes=True,
                  filename=None, args=None):

        self._positions_calculate()

        if filename != None:
            outfile = open(filename, 'w')
        else:
            import sys
            outfile = sys.stdout

        # Preamble
        if args is None: args = ''
        print(r'\begin{tikzpicture}[%s]' % args, file=outfile)

        # Write coordinates
        for coord in self.coords.keys():
            print(r'    \coordinate (%s) at (%.1f, %.1f);' % (coord, self.coords[coord][0], self.coords[coord][1]), file=outfile)


        # Draw components
        for m, elt in enumerate(self.elements.values()):

            n1, n2 = elt.nodes

            cpt_type = cpt_type_map[elt.cpt_type]

            # circuittikz expects the positive node first, except for 
            # voltage and current sources!
            if elt.opts['dir'] == 'down' and cpt_type in ('V', 'Vdc', 'I', 'Idc'):
                n1, n2 = n2, n1
      
            # If have a left drawn cpt, then switch nodes so that
            # label defaults to top but then have to switch current
            # and voltage directions.
            if elt.opts['dir'] == 'left':
                n1, n2 = n2, n1
                if elt.opts.has_key('i'):
                    elt.opts['i<^'] = elt.opts.pop('i')
                if elt.opts.has_key('v'):
                    elt.opts['v_>'] = elt.opts.pop('v')

            # Current, voltage, label options.
            # It might be better to allow any options and prune out
            # dir and size.
            opts_str = ''
            for opt in ('i', 'i_', 'i^', 'i_>', 'i_<', 'i^>', 'i^<', 
                        'i>_', 'i<_', 'i>^', 'i<^', 
                        'v', 'v_', 'v^', 'v_>', 'v_<', 'v^>', 'v^<', 'l', 'l^', 'l_'):
                if elt.opts.has_key(opt):
                    opts_str += '%s=$%s$, ' % (opt, elt.opts[opt])

            node_str = self._node_str(n1, n2, draw_nodes)
               
            label_str =''
            if draw_labels and not ('l' in elt.opts.keys() or 'l_' in elt.opts.keys() or 'l^' in elt.opts.keys()):
                if cpt_type not in ('open', 'short'):
                    label_str = '=%s' % elt.autolabel

            print(r'    \draw (%s) to [%s%s, %s%s] (%s);' % (n1, cpt_type, label_str, opts_str, node_str, n2))

        wires = self._make_wires()

        # Draw wires
        for wire in wires:
            n1, n2 = wire.nodes

            node_str = self._node_str(n1, n2, draw_nodes)
            print(r'    \draw (%s) to [short, %s] (%s);' % (n1, node_str, n2))
    
        # Label primary nodes
        if label_nodes:
            for m, node in enumerate(self.nodes.values()):
                if not node.primary:
                    continue
                print(r'    \draw {[anchor=south east] (%s) node {%s}};' % (node.name, node.name))

        print(r'\end{tikzpicture}', file=outfile)


    def schemdraw_draw(self, draw_labels=True, draw_nodes=True, 
                       label_nodes=True, filename=None, args=None):

        from SchemDraw import Drawing
        import SchemDraw.elements as e

        cpt_type_map2 = {'R' : e.RES, 'C' : e.CAP, 'L' : e.INDUCTOR2, 
                         'Vac' : e.SOURCE_SIN, 'Vdc' : e.SOURCE_V,
                         'Iac' : e.SOURCE_SIN, 'Idc' : e.SOURCE_I, 
                         'V' : e.SOURCE_V, 'I' : e.SOURCE_I, 
                         'v' : e.SOURCE_V, 'i' : e.SOURCE_I,
                         'P' : e.GAP_LABEL, 'port' : e.GAP_LABEL,
                         'W' : e.LINE, 'wire' : e.LINE}        


        self._positions_calculate()

        # Preamble
        if args is None: args = ''
        
        drw = Drawing()

        # Draw components
        for m, elt in enumerate(self.elements.values()):

            cpt_type = cpt_type_map2[elt.cpt_type]

            if draw_labels:
                drw.add(cpt_type, xy=elt.pos1, to=elt.pos2, 
                        label=elt.autolabel)
            else:
                drw.add(cpt_type, xy=elt.pos1, to=elt.pos2)

        if draw_nodes:
            for m, node in enumerate(self.nodes.values()):
                label_str = node.name if draw_labels and node.primary else ''
                if node.port:
                    drw.add(e.DOT_OPEN, xy=self.coords[node.name],
                            label=label_str)
                elif node.primary:
                    drw.add(e.DOT, xy=self.coords[node.name], 
                            label=label_str)

        drw.draw()
        if filename is not None:
            drw.save(filename)


    def draw(self, draw_labels=True, draw_nodes=True, label_nodes=True,
             filename=None, args=None, scale=2, tex=False):

        self.scale = scale

        if tex or (filename is not None and filename.endswith('.tex')):
            self.tikz_draw(draw_labels=draw_labels, draw_nodes=draw_nodes,
                           label_nodes=label_nodes, filename=filename,
                           args=args)            
        else:
            self.schemdraw_draw(draw_labels=draw_labels, draw_nodes=draw_nodes, 
                                label_nodes=label_nodes, filename=filename)




def test():
    
    sch = Schematic()

    sch.add('P1 1 0.1')
    sch.add('R1 1 3; right')
    sch.add('L1 3 2; right')
    sch.add('C1 3 0; down')
    sch.add('P2 2 0.2')
    sch.add('W 0.1 0; right')
    sch.add('W 0 0.2; right')

    sch.draw()
    return sch