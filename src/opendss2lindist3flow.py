from pathlib import Path
import py_dss_interface
import numpy as np
import json
import os
import re

class OpenDSS2LinDist3Flow:
    def __init__(self, dss_file_path):
        self.dss = py_dss_interface.DSS()
        self.dss_file = dss_file_path
        self.nodes = set()
        
    def run_dss(self):
        """Inicializa e compila o OpenDSS."""
        # Limpa memória
        self.dss.text("Clear")
        
        # CORREÇÃO AQUI:
        # Usamos aspas simples ' fora e aspas duplas " dentro para proteger o caminho
        # O comando final enviado ao OpenDSS será: Compile "C:\Caminho Com Espaço\Arquivo.dss"
        self.dss.text(f'Compile "{self.dss_file}"')
        
        # Resolve um snapshot inicial para garantir que o circuito esteja montado
        self.dss.text("CalcVoltageBases")
        self.dss.solution.solve()
        print(f"Circuito compilado: {self.dss.circuit.name}")

    def _parse_bus_phases(self, bus_str):
        """
        Analisa a string da barra (ex: 'bus1.1.2') e retorna o nome da barra
        e os índices das fases (0, 1, 2).
        Se não houver sufixo (ex: 'bus1'), assume trifásico (0, 1, 2).
        """
        parts = bus_str.split('.')
        bus_name = parts[0].lower() # OpenDSS é case insensitive
        
        if len(parts) == 1:
            # Assume trifásico se não especificado
            return bus_name, [0, 1, 2]
        else:
            # OpenDSS usa fases 1,2,3 -> converter para índices 0,1,2
            phases = [int(p) - 1 for p in parts[1:]]
            return bus_name, phases

    def _matrix_to_3x3(self, matrix_array, phases, n_phases_line):
        """
        Mapeia a matriz linear do OpenDSS (ex: lista de 1, 4 ou 9 elementos)
        para uma matriz 3x3 completa, preenchendo com zeros as fases inexistentes.
        """
        # A matriz vem do OpenDSS como uma lista flat.
        # Ex: bifásico (2 fases) tem 4 elementos (2x2).
        mat_dss = np.array(matrix_array).reshape(n_phases_line, n_phases_line)
        
        mat_3x3 = np.zeros((3, 3))
        
        # Mapeia os elementos da matriz reduzida para a 3x3 nas posições corretas
        for i, ph_i in enumerate(phases):
            for j, ph_j in enumerate(phases):
                mat_3x3[ph_i, ph_j] = mat_dss[i, j]
                
        return mat_3x3

    def get_lines_data(self):
        """Extrai dados de linhas e converte impedâncias para Ohms totais 3x3."""
        lines_data = []
        
        # Iterar sobre todas as linhas
        n_lines = self.dss.lines.count
        self.dss.lines.first()
        
        for _ in range(n_lines):
            name = self.dss.lines.name
            
            # Topologia
            bus1_str = self.dss.lines.bus1
            bus2_str = self.dss.lines.bus2
            
            u, phases_u = self._parse_bus_phases(bus1_str)
            v, phases_v = self._parse_bus_phases(bus2_str)
            
            self.nodes.add(u)
            self.nodes.add(v)
            
            # Propriedades Físicas
            length = self.dss.lines.length
            # Nota: rmatrix e xmatrix no OpenDSS geralmente são por unidade de comprimento
            # dependendo de como foi definido. Assumindo definição padrão (ohms/unidade).
            # Se Units for 'none', o valor já é total, mas em circuitos geográficos é /km ou /kft.
            # Aqui multiplicamos pelo length para garantir Ohms Totais.
            
            rmat_raw = self.dss.lines.rmatrix
            xmat_raw = self.dss.lines.xmatrix
            n_phases = self.dss.lines.phases
            
            # Converter para 3x3
            # Usa as fases de u (source) como referência para a matriz
            r_3x3 = self._matrix_to_3x3(rmat_raw, phases_u, n_phases) * length
            x_3x3 = self._matrix_to_3x3(xmat_raw, phases_u, n_phases) * length
            
            lines_data.append({
                "name": name,
                "from": u,
                "to": v,
                "length": length,
                "r_matrix": r_3x3.tolist(), # Convertendo para lista para JSON
                "x_matrix": x_3x3.tolist()
            })
            
            self.dss.lines.next()
            
        return lines_data

    def get_loads_data(self):
        """Extrai cargas ativas e reativas (kW, kvar) organizadas por nó (3x1 array)."""
        loads_dict = {} 
        
        n_loads = self.dss.loads.count
        self.dss.loads.first()
        
        for _ in range(n_loads):
            # --- CORREÇÃO AQUI ---
            # A interface .loads não tem .bus1. 
            # Usamos .cktelement.bus_names para pegar a conectividade do elemento ativo.
            # Retorna uma lista ['bus_name.1.2'], pegamos o primeiro item.
            bus_str = self.dss.cktelement.bus_names[0]
            
            bus_name, phases = self._parse_bus_phases(bus_str)
            
            if bus_name not in loads_dict:
                loads_dict[bus_name] = {
                    'p': np.zeros(3), 
                    'q': np.zeros(3)
                }
            
            kw = self.dss.loads.kw
            kvar = self.dss.loads.kvar
            
            # Nota: .is_delta existe na interface Loads, então ok manter.
            is_delta = self.dss.loads.is_delta
            
            n_phases_load = len(phases)
            # Evitar divisão por zero se algo estiver errado nas fases
            if n_phases_load > 0:
                p_per_phase = kw / n_phases_load
                q_per_phase = kvar / n_phases_load
            else:
                p_per_phase = 0
                q_per_phase = 0
            
            for ph in phases:
                # Proteção: phases vem do OpenDSS como 0,1,2, mas verifique se não excede índice 2
                if ph < 3: 
                    loads_dict[bus_name]['p'][ph] += p_per_phase
                    loads_dict[bus_name]['q'][ph] += q_per_phase
                
            self.dss.loads.next()
            
        final_loads = []
        for bus, data in loads_dict.items():
            final_loads.append({
                "bus": bus,
                "p_load": data['p'].tolist(),
                "q_load": data['q'].tolist()
            })
            
        return final_loads

    def get_general_data(self):
        """Retorna dados gerais como tensão base."""
        # --- CORREÇÃO DO ERRO DE ACCESS VIOLATION ---
        # Se self.nodes estiver vazio (circuito não compilou ou não tem linhas),
        # não tente definir a barra ativa.
        if not self.nodes:
            print("AVISO: Nenhum nó encontrado. Usando valores padrão para V_base.")
            return {
                "s_base_mva": 1.0,
                "v_base_kv_ll": 4.16 
            }

        # Pega a primeira barra encontrada para referência
        first_node = list(self.nodes)[0]
        self.dss.circuit.set_active_bus(first_node)
        
        kv_base = self.dss.bus.kv_base # kV LN
        
        if kv_base == 0:
            kv_base = 4.16 / 1.732 
            
        return {
            "s_base_mva": 1.0,
            "v_base_kv_ll": kv_base * 1.732 
        }

    def export_json(self, output_path):
        self.run_dss()
        
        print("Extraindo Linhas...")
        lines = self.get_lines_data()
        
        print("Extraindo Cargas...")
        loads = self.get_loads_data()
        
        print("Extraindo Dados Gerais...")
        general = self.get_general_data()
        
        # Ordenar nós para consistência
        sorted_nodes = sorted(list(self.nodes))
        
        data = {
            "nodes": sorted_nodes,
            "general": general,
            "lines": lines,
            "loads": loads
        }
        
        # Salva em JSON
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=4)
        
        print(f"Arquivo gerado com sucesso: {output_path}")
        return data

if __name__ == "__main__":
    # 1. Identifica onde este script (main.py ou lindist3flow.py) está
    script_path = Path(__file__).resolve()
    
    # 2. Identifica a raiz do projeto
    # Se o script está em 'src/', o .parent é 'src' e o .parent.parent é a raiz do projeto
    project_root = script_path.parent.parent
    
    # 3. Constrói o caminho para o arquivo DSS
    # O operador '/' no pathlib une os caminhos de forma segura para Windows/Linux
    dss_file_path = project_root / "data" / "13Bus" / "IEEE13Nodeckt.dss"
    
    # Converte para string para passar para o OpenDSS
    dss_file_str = str(dss_file_path)

    print(f"Tentando abrir: {dss_file_str}")
    
    if not dss_file_path.exists():
        print(f"ERRO: Arquivo não encontrado no caminho: {dss_file_str}")
    else:
        # Passa o caminho absoluto para a classe
        converter = OpenDSS2LinDist3Flow(dss_file_str)
        converter.export_json("rede_eletrica.json")