import pandas as pd
import numpy as np
import json
from lindist3flow import LinDist3FlowSolver

class SimulationEnviorment:
    def __init__(self, json_path, df_curves):
        """
        json_path: Caminho para o JSON gerado pelo OpenDSS2LinDist3FLow
        df_curves: DataFrame com curvas (Multiplicadores).
                   Colunas devem ser nomes de cargas (ex: "Load.671").
        """

        with open(json_path, 'r') as f:
            data = json.load(f)

        self.nodes = data['nodes']

        roots = ['sourcebus', 'rg60', '650', '632']
        for r in roots:
            if r in self.nodes:
                self.nodes.remove(r)
                self.nodes.insert(0, r)
                break
        
        self.nodes_map = {n: i for i , n in enumerate(self.nodes)}
        self.n_nodes = len(self.nodes)

        lines_proc = []
        for l in data['lines']:
            l['r_matrix'] = np.array(l['r_matrix'])
            l['x_matrix'] = np.array(l['x_matrix'])
            lines_proc.append(l)

        self.s_base_mva = data['general']['s_base_mva']
        self.v_base_kv = data['general']['v_base_kv_ll']
        self.solver = LinDist3FlowSolver(self.nodes,
                                         lines_proc,
                                         self.v_base_kv,
                                         self.s_base_mva)
        self.loads_map = data['loads_map']
        self.profiles = df_curves

        self.map_indices = []

        print("Mapeando perfis de carga...")

        for col_name in self.profiles.columns:

            dss_name = col_name

            found_meta = None
            for key, val in self.loads_map.items():
                if key.lower() == dss_name.lower().split('.')[1]:
                    found_meta = val
                    break

            if found_meta:
                bus = found_meta['bus']
                if bus not in self.nodes_map: continue

                node_idx = self.nodes_map[bus]
                phases = found_meta['phases']
                kw_nom = found_meta['kw']
                kvar_nom = found_meta['kvar']

                s_base_kw = self.s_base_mva * 1_000
                p_base_pu = kw_nom / s_base_kw
                q_base_pu = kvar_nom / s_base_kw

                n_ph = len(phases)
                if n_ph > 0:
                    p_base_pu /= n_ph
                    q_base_pu /= n_ph

                self.map_indices.append({
                    'col': col_name,
                    'node_idx': node_idx,
                    'phases': phases,
                    'p_base': p_base_pu,
                    'q_base': q_base_pu 
                })

            else:
                print(f"AVISO: Coluna '{col_name}' do CSV não corresponde a nenhuma carga no OpenDSS.")
            
        print(f"Mapeamento concluído. {len(self.map_indices)} colunas vinculadas.")

    def step(self, t_idx):
        """
        Executa um passo de simulação.
        t_idx: Índice da linha do DataFrame (tempo)
        """

        p_t = np.zeros((3, self.n_nodes))
        q_t = np.zeros((3, self.n_nodes))

        row = self.profiles.iloc[t_idx]

        for item in self.map_indices:
            mult = row[item['col']]

            p_val = item['p_base'] * mult
            q_val = item['q_base'] * mult

            p_t[item['phases'], item['node_idx']] += p_val
            q_t[item['phases'], item['node_idx']] += p_val

        return self.solver.solve(p_t, q_t)
    
if __name__ == "__main__":
    
    df_curves = pd.read_csv('./data/curves/13BUS_curve.csv', index_col='timestamp')

    env = SimulationEnviorment("./data/13Bus/IEEE13Nodeckt_simplified.json", df_curves)
    v_res = env.step(0)
    print(v_res[:, 0])
