import numpy as np

class LinDist3FlowSolver:
    def __init__(self, nodes, lines, v_base_kv=4.16, s_base_mva=1.0):
        self.nodes = nodes
        self.lines = lines # Lista de dicionários
        self.n_nodes = len(nodes)
        self.node_map = {n: i for i, n in enumerate(nodes)}
        
        # Bases
        self.v_base = v_base_kv * 1000
        self.s_base = s_base_mva * 1e6
        self.z_base = (self.v_base**2) / self.s_base
        
        # Estrutura para facilitar varreduras
        self.children = {n: [] for n in nodes}
        self.parents = {n: None for n in nodes}
        self.line_params = {} 
        
        for line in lines:
            u, v = line['from'], line['to']
            # Se u ou v não estiverem no node_map, ignoramos a linha (proteção)
            if u not in self.node_map or v not in self.node_map:
                continue
                
            self.children[u].append(v)
            self.parents[v] = u
            
            # Impedância em p.u.
            self.line_params[(u, v)] = (
                line['r_matrix'] / self.z_base,
                line['x_matrix'] / self.z_base
            )

        # Ordenar nós para varredura (assumindo que nodes[0] é a raiz correta)
        self.order_down = self._get_topological_order()
        self.order_up = self.order_down[::-1] 

    def _get_topological_order(self):
        order = []
        queue = [self.nodes[0]] 
        visited = set([self.nodes[0]])
        
        while queue:
            u = queue.pop(0)
            order.append(u)
            for v in self.children[u]:
                if v not in visited:
                    visited.add(v)
                    queue.append(v)
        return order

    def _calc_M_matrices(self, r_pu, x_pu):
        mp = np.zeros((3, 3))
        mq = np.zeros((3, 3))
        sqrt3 = np.sqrt(3)

        # Diagonais
        for i in range(3):
            mp[i, i] = -2 * r_pu[i, i]
            mq[i, i] = -2 * x_pu[i, i]
            
        # Off-diagonals (LinDist3Flow analysis.tex Eq 28-29)
        # Row a (0)
        mp[0, 1] = r_pu[0, 1] - sqrt3 * x_pu[0, 1]
        mp[0, 2] = r_pu[0, 2] + sqrt3 * x_pu[0, 2]
        mq[0, 1] = x_pu[0, 1] + sqrt3 * r_pu[0, 1]
        mq[0, 2] = x_pu[0, 2] - sqrt3 * r_pu[0, 2]
        
        # Row b (1)
        mp[1, 0] = r_pu[1, 0] + sqrt3 * x_pu[1, 0]
        mp[1, 2] = r_pu[1, 2] - sqrt3 * x_pu[1, 2]
        mq[1, 0] = x_pu[1, 0] - sqrt3 * r_pu[1, 0]
        mq[1, 2] = x_pu[1, 2] + sqrt3 * r_pu[1, 2]
        
        # Row c (2)
        mp[2, 0] = r_pu[2, 0] - sqrt3 * x_pu[2, 0]
        mp[2, 1] = r_pu[2, 1] + sqrt3 * x_pu[2, 1]
        mq[2, 0] = x_pu[2, 0] + sqrt3 * r_pu[2, 0]
        mq[2, 1] = x_pu[2, 1] - sqrt3 * r_pu[2, 1]
        
        return mp, mq

    def solve(self, load_p_pu, load_q_pu, v_root_pu=None):
        if v_root_pu is None:
            v_root_pu = np.ones(3)
            
        S_flow = {n: np.zeros(3, dtype=complex) for n in self.nodes}
        Y_node = {n: np.zeros(3) for n in self.nodes}
        
        # 1. Backward Sweep (Soma de Potências)
        for node in self.order_up:
            idx = self.node_map[node]
            s_load = load_p_pu[:, idx] + 1j * load_q_pu[:, idx]
            
            s_sum_children = np.zeros(3, dtype=complex)
            for child in self.children[node]:
                s_sum_children += S_flow[child]
            
            S_flow[node] = s_load + s_sum_children

        # 2. Forward Sweep (Queda de Tensão)
        Y_node[self.nodes[0]] = v_root_pu ** 2
        
        for node in self.order_down:
            if node == self.nodes[0]: continue
            
            parent = self.parents[node]
            if not parent: continue
            
            r, x = self.line_params[(parent, node)]
            mp, mq = self._calc_M_matrices(r, x)
            
            pk = S_flow[node].real
            qk = S_flow[node].imag
            
            y_parent = Y_node[parent]
            y_child = y_parent + mp @ pk + mq @ qk
            
            Y_node[node] = y_child
            
        v_pu = np.zeros((3, self.n_nodes))
        for n, y in Y_node.items():
            y_clamped = np.maximum(y, 0)
            v_pu[:, self.node_map[n]] = np.sqrt(y_clamped)
            
        return v_pu