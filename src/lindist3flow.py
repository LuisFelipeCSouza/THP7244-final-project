import numpy as np

class LinDist3FlowSolver:
    def __init__(self, nodes, lines, v_base_kv=4.16, s_base_mva=1.0):
        self.nodes = nodes
        self.lines = lines # Lista de dicionários: {'from', 'to', 'r_matrix', 'x_matrix'}
        self.n_nodes = len(nodes)
        self.node_map = {n: i for i, n in enumerate(nodes)}
        
        # Bases
        self.v_base = v_base_kv * 1000
        self.s_base = s_base_mva * 1e6
        self.z_base = (self.v_base**2) / self.s_base
        
        # Estrutura para facilitar varreduras (assumindo radial)
        self.children = {n: [] for n in nodes}
        self.parents = {n: None for n in nodes}
        self.line_params = {} # (u, v) -> (r_pu, x_pu)
        
        for line in lines:
            u, v = line['from'], line['to']
            self.children[u].append(v)
            self.parents[v] = u
            # Converter impedância para p.u.
            self.line_params[(u, v)] = (
                line['r_matrix'] / self.z_base,
                line['x_matrix'] / self.z_base
            )

        # Ordenar nós para varredura (BFS/Topological Sort)
        self.order_down = self._get_topological_order()
        self.order_up = self.order_down[::-1] # De baixo para cima (folhas -> raiz)

    def _get_topological_order(self):
        # Simples BFS para ordenar desde a raiz
        order = []
        queue = [self.nodes[0]] # Assumindo nó 0 como raiz
        while queue:
            u = queue.pop(0)
            order.append(u)
            for v in self.children[u]:
                queue.append(v)
        return order

    def _calc_M_matrices(self, r_pu, x_pu, gamma=None):
        """
        Calcula M^P e M^Q (Eqs 28-29 analysis.tex).
        Se gamma=None, assume aproximação nominal (120 graus).
        """
        mp = np.zeros((3, 3))
        mq = np.zeros((3, 3))
        sqrt3 = np.sqrt(3)

        # Se gamma não for fornecido, usa-se a simplificação do artigo (alpha = 1<120)
        # Onde a parte real/imag da rotação já está embutida nas eqs (28) e (29) hardcoded.
        # Eq 28 (M^P):
        # Diagonais
        for i in range(3):
            mp[i, i] = -2 * r_pu[i, i]
            mq[i, i] = -2 * x_pu[i, i]
            
        # Off-diagonals (seguindo explicitamente Eqs 28 e 29 do analysis.tex)
        # Nota: O artigo define índices a=1, b=2, c=3. Aqui 0,1,2.
        
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
        """
        Executa o cálculo de fluxo de potência.
        load_p_pu: Dicionário ou array (3, N) de cargas ativas
        """
        # Inicialização
        if v_root_pu is None:
            v_root_pu = np.ones(3) # [1.0, 1.0, 1.0] se nominal
            
        # Estruturas para armazenar estado
        # S_flow_in: Potência fluindo PARA o nó n vinda do pai
        S_flow = {n: np.zeros(3, dtype=complex) for n in self.nodes}
        Y_node = {n: np.zeros(3) for n in self.nodes} # |V|^2
        
        # 1. Backward Sweep (Cálculo de Fluxos de Potência)
        # Eq 27: S_j = s_j + sum(S_k)
        # Começa das folhas para a raiz
        for node in self.order_up:
            # Carga local (s_j)
            idx = self.node_map[node]
            s_load = load_p_pu[:, idx] + 1j * load_q_pu[:, idx]
            
            s_sum_children = np.zeros(3, dtype=complex)
            for child in self.children[node]:
                s_sum_children += S_flow[child]
            
            S_flow[node] = s_load + s_sum_children

        # 2. Forward Sweep (Cálculo de Tensões)
        # Eq 28: Y_k = Y_j + M^P * P_k + M^Q * Q_k
        # Atenção aos sinais: O artigo diz Y_j (pai) approx Y_k (filho) - M...
        # Logo: Y_k = Y_j + M^P * P_k + M^Q * Q_k
        # (Considerando que M tem diagonais negativas (-2r), isso resulta em queda de tensão correta)
        
        # Configurar raiz
        Y_node[self.nodes[0]] = v_root_pu ** 2
        
        for node in self.order_down:
            if node == self.nodes[0]: continue
            
            parent = self.parents[node]
            r, x = self.line_params[(parent, node)]
            
            # Calcular Matrizes M
            mp, mq = self._calc_M_matrices(r, x)
            
            # Fluxos entrando no nó atual (P_k, Q_k)
            pk = S_flow[node].real
            qk = S_flow[node].imag
            
            # Calcular Y do nó atual baseado no pai
            # Y_child = Y_parent + Mp*P + Mq*Q
            y_parent = Y_node[parent]
            y_child = y_parent + mp @ pk + mq @ qk
            
            Y_node[node] = y_child
            
        # Retorna magnitude de tensão (sqrt(Y)) em p.u.
        v_pu = np.zeros((3, self.n_nodes))
        for n, y in Y_node.items():
            # Proteção para valores negativos (muito raros em linearização mal condicionada)
            y_clamped = np.maximum(y, 0)
            v_pu[:, self.node_map[n]] = np.sqrt(y_clamped)
            
        return v_pu

# --- Exemplo de Execução ---
if __name__ == "__main__":
    # Configuração Simples (2 nós)
    nodes = [0, 1]
    
    # Impedância (Exemplo desequilibrado)
    r_mat = np.array([[0.3, 0.05, 0.05], [0.05, 0.3, 0.05], [0.05, 0.05, 0.3]])
    x_mat = np.array([[0.1, 0.02, 0.02], [0.02, 0.1, 0.02], [0.02, 0.02, 0.1]])
    
    lines = [{'from': 0, 'to': 1, 'r_matrix': r_mat, 'x_matrix': x_mat}]
    
    # Cargas (3 fases x 2 nós)
    p_load = np.array([[0, 0.1], [0, 0.05], [0, 0.08]]) # Carga no nó 1
    q_load = np.array([[0, 0.05], [0, 0.02], [0, 0.03]])
    
    solver = LinDist3FlowSolver(nodes, lines)
    v_result = solver.solve(p_load, q_load)
    
    print("Tensões no Nó 0 (Raiz):", v_result[:, 0])
    print("Tensões no Nó 1 (Carga):", v_result[:, 1])