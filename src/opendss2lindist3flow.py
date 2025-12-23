import py_dss_interface
import numpy as np
import json
import os
from pathlib import Path

class OpenDSS2LinDist3Flow:
    def __init__(self, dss_file_path):
        self.dss = py_dss_interface.DSS()
        self.dss_file = dss_file_path
        self.nodes = set()
        
    def run_dss(self):
        self.dss.text("Clear")
        # Correção: Aspas duplas para proteger caminhos com espaços ou parênteses
        self.dss.text(f'Compile "{self.dss_file}"')
        self.dss.text("CalcVoltageBases")
        self.dss.solution.solve()
        print(f"Circuito compilado: {self.dss.circuit.name}")

    def _parse_bus_phases(self, bus_str):
        parts = bus_str.split('.')
        bus_name = parts[0].lower()
        if len(parts) == 1:
            return bus_name, [0, 1, 2]
        else:
            phases = [int(p) - 1 for p in parts[1:]]
            return bus_name, phases

    def _matrix_to_3x3(self, matrix_array, phases, n_phases_line):
        mat_dss = np.array(matrix_array).reshape(n_phases_line, n_phases_line)
        mat_3x3 = np.zeros((3, 3))
        for i, ph_i in enumerate(phases):
            for j, ph_j in enumerate(phases):
                mat_3x3[ph_i, ph_j] = mat_dss[i, j]
        return mat_3x3

    def get_lines_data(self):
        lines_data = []
        n_lines = self.dss.lines.count
        self.dss.lines.first()
        
        for _ in range(n_lines):
            name = self.dss.lines.name
            bus1_str = self.dss.lines.bus1
            bus2_str = self.dss.lines.bus2
            
            u, phases_u = self._parse_bus_phases(bus1_str)
            v, phases_v = self._parse_bus_phases(bus2_str)
            
            self.nodes.add(u)
            self.nodes.add(v)
            
            length = self.dss.lines.length
            rmat_raw = self.dss.lines.rmatrix
            xmat_raw = self.dss.lines.xmatrix
            n_phases = self.dss.lines.phases
            
            r_3x3 = self._matrix_to_3x3(rmat_raw, phases_u, n_phases) * length
            x_3x3 = self._matrix_to_3x3(xmat_raw, phases_u, n_phases) * length
            
            lines_data.append({
                "name": name, "from": u, "to": v,
                "length": length,
                "r_matrix": r_3x3.tolist(),
                "x_matrix": x_3x3.tolist()
            })
            self.dss.lines.next()
        return lines_data

    def get_loads_data(self):
        loads_dict = {}
        n_loads = self.dss.loads.count
        self.dss.loads.first()
        
        for _ in range(n_loads):
            # Correção: Usar CktElement para pegar a barra
            bus_str = self.dss.cktelement.bus_names[0]
            bus_name, phases = self._parse_bus_phases(bus_str)
            
            if bus_name not in loads_dict:
                loads_dict[bus_name] = {'p': np.zeros(3), 'q': np.zeros(3)}
            
            kw = self.dss.loads.kw
            kvar = self.dss.loads.kvar
            n_phases_load = len(phases)
            
            p_per = kw / n_phases_load if n_phases_load > 0 else 0
            q_per = kvar / n_phases_load if n_phases_load > 0 else 0
            
            for ph in phases:
                if ph < 3:
                    loads_dict[bus_name]['p'][ph] += p_per
                    loads_dict[bus_name]['q'][ph] += q_per
            
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
        if not self.nodes:
            return {"s_base_mva": 1.0, "v_base_kv_ll": 4.16}

        self.dss.circuit.set_active_bus(list(self.nodes)[0])
        kv_base = self.dss.bus.kv_base
        if kv_base == 0: kv_base = 4.16 / 1.732
            
        return {
            "s_base_mva": 1.0,
            "v_base_kv_ll": kv_base * 1.732
        }

    def export_json(self, output_path):
        self.run_dss()
        print("Extraindo dados...")
        data = {
            "lines": self.get_lines_data(),
            "loads": self.get_loads_data(),
            "general": self.get_general_data(),
            "nodes": sorted(list(self.nodes))
        }
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=4)
        print(f"JSON salvo em: {output_path}")

if __name__ == "__main__":
    # Script para teste direto do conversor
    script_path = Path(__file__).resolve()
    project_root = script_path.parent.parent
    dss_file = project_root / "data" / "13Bus" / "IEEE13Nodeckt.dss"
    
    if dss_file.exists():
        converter = OpenDSS2LinDist3Flow(str(dss_file))
        converter.export_json("rede_eletrica.json")
    else:
        print(f"Arquivo DSS não encontrado: {dss_file}")