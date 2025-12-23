import json
import numpy as np
import os
from pathlib import Path
from lindist3flow import LinDist3FlowSolver
from opendss2lindist3flow import OpenDSS2LinDist3Flow

def main():
    # 1. Configuração de Caminhos
    # Garante funcionamento no terminal e (parcialmente) em notebooks
    current_dir = Path.cwd()
    
    # Lógica para encontrar a raiz do projeto procurando a pasta 'src' ou 'data'
    if (current_dir / "src").exists():
        project_root = current_dir
    elif (current_dir.parent / "src").exists():
        project_root = current_dir.parent
    else:
        # Tenta pegar pelo arquivo se não for notebook
        try:
            project_root = Path(__file__).resolve().parent.parent
        except NameError:
            print("AVISO: Rodando em ambiente interativo. Verifique se o caminho está correto.")
            project_root = current_dir

    dss_file_path = project_root / "data" / "13Bus" / "IEEE13Nodeckt.dss"
    json_output_path = project_root / "data" / "13Bus" / "IEEE13Nodeckt.json"

    # 2. Gerar JSON se não existir ou se quiser forçar atualização
    if not json_output_path.exists():
        print("Arquivo JSON não encontrado. Gerando a partir do OpenDSS...")
        if dss_file_path.exists():
            converter = OpenDSS2LinDist3Flow(str(dss_file_path))
            converter.export_json(str(json_output_path))
        else:
            raise FileNotFoundError(f"Arquivo DSS não encontrado em: {dss_file_path}")

    # 3. Carregar Dados
    with open(json_output_path, 'r') as f:
        data = json.load(f)

    # 4. Pré-processamento e Ordenação (CRÍTICO)
    nodes = data['nodes']
    
    # Identificar barra raiz (sourcebus) e mover para índice 0
    # No IEEE13 geralmente é 'sourcebus' ou 'rg60' dependendo da definição
    possible_roots = ['sourcebus', 'source', '650', 'rg60'] 
    root_found = False
    
    for r in possible_roots:
        if r in nodes:
            nodes.remove(r)
            nodes.insert(0, r)
            print(f"Barra de referência definida como: {r}")
            root_found = True
            break
            
    if not root_found:
        print(f"AVISO: Barra de referência não identificada automaticamente. O solver pode falhar. Nó 0 atual: {nodes[0]}")

    node_map = {n: i for i, n in enumerate(nodes)}
    n_nodes = len(nodes)

    # Converter Linhas
    lines_processed = []
    for line in data['lines']:
        line['r_matrix'] = np.array(line['r_matrix'])
        line['x_matrix'] = np.array(line['x_matrix'])
        lines_processed.append(line)

    # 5. Mapear Cargas
    load_p = np.zeros((3, n_nodes))
    load_q = np.zeros((3, n_nodes))
    s_base_mva = data['general']['s_base_mva']
    s_base_kw = s_base_mva * 1000

    print(f"Mapeando {len(data['loads'])} cargas...")
    for load in data['loads']:
        bus_name = load['bus']
        
        # Filtro de segurança: ignora cargas em barras que não estão nas linhas (ex: transformadores)
        if bus_name not in node_map:
            # Opcional: print(f"Ignorando carga na barra {bus_name}")
            continue
            
        idx = node_map[bus_name]
        load_p[:, idx] = np.array(load['p_load']) / s_base_kw
        load_q[:, idx] = np.array(load['q_load']) / s_base_kw

    # 6. Executar Solver
    solver = LinDist3FlowSolver(
        nodes, 
        lines_processed, 
        v_base_kv=data['general']['v_base_kv_ll'], 
        s_base_mva=s_base_mva
    )

    print("Resolvendo fluxo de potência...")
    v_result = solver.solve(load_p, load_q)

    # 7. Exibir Resultados
    print("\n--- Resultados (Tensões p.u.) ---")
    # Mostra as primeiras 5 barras para conferência
    for i in range(min(5, n_nodes)):
        node_name = nodes[i]
        v_a, v_b, v_c = v_result[:, i]
        print(f"Barra {node_name:<10}: A={v_a:.4f}  B={v_b:.4f}  C={v_c:.4f}")

if __name__ == "__main__":
    main()