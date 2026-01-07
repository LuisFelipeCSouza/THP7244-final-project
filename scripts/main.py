import sys
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

# --- 1. CONFIGURAÇÃO DE AMBIENTE E IMPORTAÇÃO ---
# Identifica o diretório onde este script está (scripts/)
script_dir = Path(__file__).resolve().parent

# Identifica a raiz do projeto (um nível acima)
project_root = script_dir.parent

# Adiciona a pasta 'src' ao caminho do Python para permitir importação
sys.path.append(str(project_root / 'src'))

try:
    # Agora podemos importar a classe que está em src/simulation_env.py
    from simulation_env import SimulationEnviorment
except ImportError as e:
    print("ERRO CRÍTICO: Não foi possível importar 'src/simulation_env.py'.")
    print(f"Verifique se o caminho '{project_root / 'src'}' existe.")
    sys.exit(1)

# --- 2. CONFIGURAÇÃO DE ARQUIVOS DE DADOS ---
# Ajuste o nome do JSON conforme o último arquivo que você gerou (rede_eletrica.json ou IEEE13...json)
json_path = project_root / "data" / "13Bus" / "IEEE13Nodeckt_simplified.json" 
# Ou: json_path = project_root / "rede_eletrica.json"

csv_path = project_root / "data" / "curves" / "13BUS_curve.csv"

def main():
    print(f"--- INICIANDO AVALIAÇÃO DE SIMULAÇÃO ---")
    print(f"Raiz do Projeto: {project_root}")
    
    # Validação básica
    if not json_path.exists():
        print(f"ERRO: Arquivo JSON não encontrado em: {json_path}")
        return
    if not csv_path.exists():
        print(f"ERRO: Arquivo CSV não encontrado em: {csv_path}")
        return

    # --- 3. CARREGAMENTO E INICIALIZAÇÃO ---
    print("Carregando perfis de carga e topologia...")
    # parse_dates=True garante que o índice seja datetime
    df_curves = pd.read_csv(csv_path, index_col='timestamp', parse_dates=True)
    
    # Instancia o ambiente (Lógica refatorada)
    env = SimulationEnviorment(str(json_path), df_curves)
    
    # Define nós para monitoramento
    # Node 0 = Fonte (SourceBus/rg60)
    # Node -1 = Ponta do alimentador (Geralmente a barra mais distante na lista topológica)
    source_node = env.nodes[0]
    end_node = env.nodes[-1]
    
    print(f"\nConfiguração:")
    print(f" -> Passos de Tempo: {len(df_curves)}")
    print(f" -> Barra Fonte: {source_node}")
    print(f" -> Barra Ponta: {end_node}")

    # --- 4. LOOP DE SIMULAÇÃO ---
    results_source_v = []
    results_end_v = []
    
    print("\nExecutando fluxo de potência temporal...")
    for t in range(len(df_curves)):
        # Executa um passo da simulação
        v_res = env.step(t)
        
        # Extrai tensões da FASE A (índice 0)
        # O solver retorna matriz (3, N_nodes)
        v_src = v_res[0, 0]   # Fase A, Barra 0
        v_end = v_res[0, -1]  # Fase A, Última Barra
        
        results_source_v.append(v_src)
        results_end_v.append(v_end)
        
        # Feedback visual de progresso a cada 100 passos
        if t % 100 == 0:
            print(".", end="", flush=True)
            
    print("\nSimulação concluída!")

    # --- 5. VISUALIZAÇÃO DOS RESULTADOS ---
    # Cria uma curva média de carga para correlacionar visualmente (Eixo da direita)
    avg_load_profile = df_curves.mean(axis=1)

    fig, ax1 = plt.subplots(figsize=(12, 6))

    # Eixo Esquerdo: Tensões
    color_src = 'black'
    color_end = 'red'
    ax1.set_xlabel('Tempo')
    ax1.set_ylabel('Tensão (p.u.)')
    
    l1 = ax1.plot(df_curves.index, results_source_v, color=color_src, linestyle='--', label=f'Tensão Fonte ({source_node})')
    l2 = ax1.plot(df_curves.index, results_end_v, color=color_end, label=f'Tensão Ponta ({end_node})')
    
    # Limites normativos (PRODIST/IEEE)
    ax1.axhline(0.95, color='gray', linestyle=':', alpha=0.5)
    ax1.axhline(1.05, color='gray', linestyle=':', alpha=0.5)
    ax1.set_ylim(0.90, 1.05) # Ajuste conforme necessário para ver melhor a queda

    # Eixo Direito: Perfil de Carga (Para mostrar correlação)
    ax2 = ax1.twinx()
    color_load = 'blue'
    ax2.set_ylabel('Multiplicador de Carga (Média)', color=color_load)
    l3 = ax2.plot(df_curves.index, avg_load_profile, color=color_load, alpha=0.2, label='Perfil de Carga Médio')
    ax2.tick_params(axis='y', labelcolor=color_load)
    
    # Legenda Combinada
    lns = l1 + l2 + l3
    labs = [l.get_label() for l in lns]
    ax1.legend(lns, labs, loc='center right')

    plt.title(f"Simulação QSTS: Impacto da Carga na Tensão ({len(df_curves)} passos)")
    plt.grid(True, which='both', alpha=0.3)
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    main()