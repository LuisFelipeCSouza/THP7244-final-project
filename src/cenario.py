import py_dss_interface
import numpy as np
import random
import os
import matplotlib.pyplot as plt
# CÓDIGO QUE IMPLEMENTA 'CO-SIMULAÇÃO' ENTRE OPENDSS E ALGORITMO DE OTIMIZAÇÃO DA BATERIA
# ==============================================================================
#   1. ÁREA DE CONFIGURAÇÃO GERAL
#   Centraliza os parâmetros que você altera com frequência para testes.
# ==============================================================================
CONFIG = {
    # Caminho absoluto para o arquivo mestre do circuito OpenDSS !!!! CONFIGURAR DE ACORDO COM SEU PC !!!!
    "DSS_FILE": r"C:\Users\Caio\Desktop\codigos\mestrado\trabfinalredes\Nova\13Bus-Modificado_Ok\IEEE13Nodeckt.dss",
    
    # Barra onde será focado o monitoramento de tensão no gráfico final (PODE ESCOLHER QUALQUER BARRA DO SISTEMA)
    "BUS_ALVO": "675", 
    
    # Fase para monitoramento (1=Fase A, 2=Fase B, 3=Fase C)
    "FASE_ALVO": 3, 
    
    # Semente para geração de números aleatórios (garante repetibilidade do sorteio das baterias)
    "SEED": 42
}

# ==============================================================================
#   2. CLASSE DO SISTEMA DE ARMAZENAMENTO (Lógica de Controle)
# ==============================================================================
class EnergyStorageSystem:
    """
    Representa o BESS (Battery Energy Storage System) e seu Inversor Inteligente.
    Esta classe atua como o 'cérebro' local da bateria.
    """
    def __init__(self, name, bus_full_name, kv, kw_rated, kwh_rated):
        self.name = name
        self.bus_full_name = bus_full_name 
        self.kv = kv
        self.kw_rated = kw_rated   # Potência Ativa Nominal (kW) do Inversor
        self.kwh_rated = kwh_rated # Capacidade de Energia (kWh) da Bateria
        self.soc = 50.0            # Estado de Carga Inicial (%)
        
        # Parâmetros da Curva Volt-Var (Baseado na IEEE 1547, mas modificado)
        self.v_min_q = 0.92  # Tensão < 0.92 pu -> Injeta máximo reativo (Capacitivo)
        self.v_max_q = 1.08  # Tensão > 1.08 pu -> Absorve máximo reativo (Indutivo)

    def update_soc(self, power_kw, step_hours):
        """
        Simula a física da bateria: Atualiza o nível de carga (SOC).
        power_kw > 0: Descarregando (Sai energia da bateria) -> SOC diminui
        power_kw < 0: Carregando (Entra energia na bateria)  -> SOC aumenta
        """
        energy_change_kwh = power_kw * step_hours
        self.soc -= (energy_change_kwh / self.kwh_rated) * 100
        
        # Trava física: O SOC não pode ser menor que 0% nem maior que 100%
        self.soc = max(0.0, min(100.0, self.soc))
        return self.soc

    def get_volt_var_q(self, v_pu):
        """
        Lógica de Controle REATIVO (Volt-Var) SEM BANDA MORTA.
        Objetivo: Suporte de tensão imediato.
        
        Diferente do padrão que tem uma zona morta (ex: 0.98 a 1.02 onde Q=0),
        esta lógica reage a qualquer desvio de 1.0 pu.
        """
        # Define a capacidade de reativo (50% da potência ativa nominal)
        q_limit = self.kw_rated * 0.5 
        
        # 1. Região de Saturação Inferior (Tensão crítica baixa)
        if v_pu <= self.v_min_q:
            return q_limit  # Injeta Máximo
            
        # 2. Região de Saturação Superior (Tensão crítica alta)
        elif v_pu >= self.v_max_q:
            return -q_limit # Absorve Máximo
            
        # 3. Região Linear de Injeção (V < 1.0)
        elif v_pu < 1.0:
            # Calcula a reta entre (V_min, Q_max) e (1.0, 0)
            slope = q_limit / (1.0 - self.v_min_q)
            return slope * (1.0 - v_pu)
            
        # 4. Região Linear de Absorção (V >= 1.0)
        else: 
            # Calcula a reta entre (1.0, 0) e (V_max, -Q_max)
            slope = -q_limit / (self.v_max_q - 1.0)
            return slope * (v_pu - 1.0)

    def get_self_consumption_p(self, p_pv_now, p_load_now):
        """
        Lógica de Controle ATIVO (Autoconsumo / Self-Consumption).
        Objetivo: Minimizar a troca de energia com a rede na barra local.
        """
        # Saldo energético local: Geração - Carga
        net_power = p_pv_now - p_load_now 
        
        p_cmd = 0.0
        state = "IDLING"

        if net_power > 0: 
            # SOBRA DE SOL (Geração > Carga) -> Bateria deve CARREGAR
            p_cmd = min(net_power, self.kw_rated) # Carrega a sobra, limitado ao inversor
            
            # Verificação de SOC Cheio
            if self.soc >= 99.0: 
                p_cmd, state = 0.0, "IDLING"
            else: 
                p_cmd, state = -p_cmd, "CHARGING" # Sinal negativo interno indica carga

        elif net_power < 0: 
            # FALTA DE SOL (Carga > Geração) -> Bateria deve DESCARREGAR
            p_cmd = min(abs(net_power), self.kw_rated) # Suprir a falta, limitado ao inversor
            
            # Verificação de SOC Vazio
            if self.soc <= 1.0: 
                p_cmd, state = 0.0, "IDLING"
            else: 
                p_cmd, state = p_cmd, "DISCHARGING" # Sinal positivo indica descarga
                
        return abs(p_cmd), state

# ==============================================================================
#   3. FUNÇÃO DE SETUP DO CIRCUITO
#   Prepara o OpenDSS, mapeia elementos e aloca as baterias.
# ==============================================================================
def setup_circuit(dss_file_path):
    random.seed(CONFIG["SEED"]) 
    
    # Inicializa a interface COM do OpenDSS
    dss = py_dss_interface.DSS()
    dss.text("Clear")
    dss.text(f'Compile "{dss_file_path}"')
    
    # Configurações de simulação temporal
    dss.text("Set Mode=Daily")
    dss.text("Set StepSize=15m") 
    dss.text("Set Number=1")  # Vamos resolver 1 passo por vez manualmente

    # --- A. Mapeamento dos PVs ---
    pv_names = dss.pvsystems.names
    if not pv_names: return dss, [], {}

    pv_data_list = []
    for pv_name in pv_names:
        dss.circuit.set_active_element(f"PVSystem.{pv_name}")
        bus = dss.cktelement.bus_names[0]
        phases = dss.cktelement.num_phases
        
        # Tenta ler a potência nominal (Pmpp) para dimensionar a bateria
        try:
            pmpp = float(dss.text(f"? PVSystem.{pv_name}.Pmpp"))
            if pmpp == 0: pmpp = float(dss.text(f"? PVSystem.{pv_name}.kVA"))
            kv = float(dss.text(f"? PVSystem.{pv_name}.kV"))
        except: pmpp, kv = 0.0, 0.0
        pv_data_list.append({'name': pv_name, 'bus': bus, 'phases': phases, 'pmpp': pmpp, 'kv': kv})

    # --- B. Mapeamento das Cargas ---
    # Cria um mapa { 'Barra': ['Load1', 'Load2'] } para associar carga local à bateria
    loads_by_bus = {}
    for ld in dss.loads.names:
        dss.circuit.set_active_element(f"Load.{ld}")
        bus_raw = dss.cktelement.bus_names[0]
        if bus_raw not in loads_by_bus: loads_by_bus[bus_raw] = []
        loads_by_bus[bus_raw].append(ld)

    # --- C. Instalação das Baterias ---
    # Seleciona aleatoriamente 30% dos PVs para receberem bateria
    n_bat = max(1, int(len(pv_data_list) * 0.30))
    selected_pvs = random.sample(pv_data_list, n_bat)
    
    batteries = []
    bat_associations = {}
    
    # Dicionário para estatísticas do Log
    allocation_count = {}
    
    print(f"Instalando {n_bat} baterias no circuito...")

    for data in selected_pvs:
        bat_name = f"Bat_{data['name']}"
        bus_loc = data['bus']
        
        # Dimensionamento: 1.5x PV (Potência) e 4h (Energia)
        kw_rate = data['pmpp'] * 1.5
        kva_rate = kw_rate
        kwh_rate = kw_rate * 4 
        kv_bat = data['kv'] if data['kv'] > 0 else (2.4 if data['phases']==1 else 4.16)

        # Procura uma carga local para associar (para o controle de autoconsumo)
        target_load_name = None
        if bus_loc in loads_by_bus and loads_by_bus[bus_loc]:
            target_load_name = loads_by_bus[bus_loc].pop(0) 
        else:
            # Se não achar na fase exata, procura no nó geral (ex: 671)
            bus_node = bus_loc.split('.')[0]
            for key in loads_by_bus:
                if key.startswith(bus_node) and loads_by_bus[key]:
                     target_load_name = loads_by_bus[key].pop(0)
                     break
        
        # Cria o objeto Storage no OpenDSS
        # state=IDLING: Começa parada
        # kw=0: Sem injeção ativa inicial
        cmd = (f"New Storage.{bat_name} phases={data['phases']} bus1={bus_loc} "
               f"kV={kv_bat} kVA={kva_rate} kWrated={kw_rate} kWhrated={kwh_rate} "
               f"%stored=50 state=IDLING kw=0")
        dss.text(cmd)
        
        batteries.append(EnergyStorageSystem(bat_name, bus_loc, kv_bat, kw_rate, kwh_rate))
        bat_associations[bat_name] = {'pv_name': data['name'], 'load_name': target_load_name}

        # Contagem para o Log
        parts = bus_loc.split('.')
        bus_root = parts[0]
        nodes_suffix = "." + ".".join(parts[1:]) if len(parts) > 1 else "(3-Fas)"
        key = (bus_root, nodes_suffix)
        if key not in allocation_count: allocation_count[key] = 0
        allocation_count[key] += 1

    dss.text("CalcVoltageBases")
    
    # --- LOGS DE SAÍDA ---
    print("\n" + "="*70)
    print(f"RELATÓRIO DE INSTALAÇÃO (Total: {len(batteries)})")
    print(f"{'NOME DA BATERIA':<30} | {'LOCAL':<12} | {'POTÊNCIA':<15}")
    print("-" * 70)
    for bat in batteries:
        print(f"{bat.name:<30} | {bat.bus_full_name:<12} | {bat.kw_rated:.2f} kW")
    print("="*70)

    print("\n" + "="*45)
    print(f"RESUMO DE ALOCAÇÃO POR BARRA/FASE")
    print(f"{'BARRA':<10} | {'FASES':<15} | {'QTD'}")
    print("-" * 45)
    sorted_alloc = sorted(allocation_count.items(), key=lambda x: x[0][0])
    for (bus, nodes), count in sorted_alloc:
        print(f"{bus:<10} | {nodes:<15} | {count}")
    print("="*45 + "\n")

    return dss, batteries, bat_associations

# ==============================================================================
#   4. LOOP DE SIMULAÇÃO (CORE)
#   Executa o fluxo de potência passo a passo (QSTS)
# ==============================================================================
def run_scenario(dss, batteries, bat_associations, control_active=False):
    steps = 96  # 24h * 4 steps/hora
    step_hours = 0.25 
    
    target_bus = CONFIG["BUS_ALVO"]
    target_phase = CONFIG["FASE_ALVO"]
    
    # Verifica se a fase alvo existe na barra (para evitar erro de plotagem)
    dss.circuit.set_active_bus(target_bus)
    existing_nodes = dss.bus.nodes
    if target_phase not in existing_nodes:
        print(f"\n[ERRO] A Barra {target_bus} não possui a Fase {target_phase}! Fases disponíveis: {existing_nodes}")

    # Reseta a simulação temporal
    dss.text("Reset")
    dss.text("Set Mode=Daily")
    dss.text("Set StepSize=15m")
    dss.text("Set Number=1")

    # Listas para guardar os dados históricos
    monitor_voltage = []
    results_p = {bat.name: [] for bat in batteries}
    results_q = {bat.name: [] for bat in batteries}
    results_pv = {bat.name: [] for bat in batteries}
    results_load_real = {bat.name: [] for bat in batteries}

    print(f"Simulando (Ctrl={control_active}) | Monitorando: {target_bus}.{target_phase}")

    # --- INÍCIO DO LOOP TEMPORAL ---
    for t in range(steps):
        # 1. OpenDSS resolve o fluxo de potência deste instante
        # Ele atualiza internamente as Cargas e PVs baseado nos LoadShapes do arquivo DSS
        dss.solution.solve()
        
        # 2. Monitoramento de Tensão
        dss.circuit.set_active_bus(target_bus)
        nodes = dss.bus.nodes
        if target_phase in nodes:
            idx = nodes.index(target_phase)
            # Lê tensão complexa e calcula magnitude (Módulo)
            voltages_complex = dss.bus.pu_voltages
            val = np.sqrt(voltages_complex[2*idx]**2 + voltages_complex[2*idx+1]**2)
            monitor_voltage.append(val)
        else:
            monitor_voltage.append(np.nan)

        # 3. Controle das Baterias
        for bat in batteries:
            # A. Ler Tensão Local (Para Volt-Var)
            dss.circuit.set_active_element(f"Storage.{bat.name}")
            # Pega magnitude da tensão no terminal 1
            v_mag = dss.cktelement.voltages_mag_ang[0] if dss.cktelement.voltages_mag_ang else 0
            
            # Converte para PU (Per Unit)
            dss.circuit.set_active_bus(bat.bus_full_name.split('.')[0])
            v_base = dss.bus.kv_base * 1000
            v_pu = v_mag / v_base if v_base > 0 else 1.0

            # B. Ler Potências Reais (Para Autoconsumo)
            assoc = bat_associations[bat.name]
            p_pv_now = 0.0
            try:
                # Lê potência saindo do PV (OpenDSS retorna negativo para gerador, invertemos para positivo)
                dss.circuit.set_active_element(f"PVSystem.{assoc['pv_name']}")
                p_pv_now = -1 * sum(dss.cktelement.powers[0::2]) 
            except: pass
            
            p_load_now = 0.0
            if assoc['load_name']:
                try:
                    # Lê potência consumida pela Carga
                    dss.circuit.set_active_element(f"Load.{assoc['load_name']}")
                    p_load_now = sum(dss.cktelement.powers[0::2])
                except: pass
            
            # C. Calcular Próximo Estado
            p_val, q_ref, state, p_signed = 0.0, 0.0, "IDLING", 0.0

            if control_active:
                # Chama a lógica da classe EnergyStorageSystem
                p_val, state = bat.get_self_consumption_p(p_pv_now, p_load_now)
                q_ref = bat.get_volt_var_q(v_pu)
                
                # Define sinal para plot e SOC
                if state == "CHARGING": p_signed = -p_val
                elif state == "DISCHARGING": p_signed = p_val
                
                # Atualiza SOC (Python side simulation)
                bat.update_soc(p_signed, step_hours)
                
                # Envia comando para o OpenDSS (será efetivo no próximo passo)
                # Truque: Se P=0, mantemos DISCHARGING para permitir que o inversor injete Q
                final_state = state if p_val != 0 else "DISCHARGING"
                dss.text(f"Edit Storage.{bat.name} state={final_state} kw={p_val} kvar={q_ref} %stored={bat.soc}")
            else:
                # Cenário Base: Bateria inativa
                dss.text(f"Edit Storage.{bat.name} state=IDLING kw=0 kvar=0")
            
            # Salva histórico
            results_p[bat.name].append(p_signed)
            results_q[bat.name].append(q_ref)
            results_pv[bat.name].append(p_pv_now)
            results_load_real[bat.name].append(p_load_now)

    return monitor_voltage, results_p, results_q, results_pv, results_load_real

# ==============================================================================
#   5. EXECUÇÃO PRINCIPAL (MAIN)
# ==============================================================================
if __name__ == "__main__":
    if os.path.exists(CONFIG["DSS_FILE"]):
        
        # --- Simulação 1: Base (Sem Bateria) ---
        print("\n--- INICIANDO CENÁRIO BASE ---")
        dss1, bats1, assoc1 = setup_circuit(CONFIG["DSS_FILE"])
        if not bats1: exit()
        v_base, _, _, _, _ = run_scenario(dss1, bats1, assoc1, control_active=False)
        
        # --- Simulação 2: Benchmark (Com Controle) ---
        print("\n--- INICIANDO CENÁRIO BENCHMARK ---")
        dss2, bats2, assoc2 = setup_circuit(CONFIG["DSS_FILE"])
        v_ctrl, p_ctrl, q_ctrl, pv_plt, ld_plt = run_scenario(dss2, bats2, assoc2, control_active=True)
        
        # --- Seleção da Bateria para Plotagem ---
        target_bus = CONFIG["BUS_ALVO"]
        bat_ex = None
        # Procura bateria na barra alvo
        for b in bats2:
            if b.bus_full_name.split('.')[0] == target_bus:
                bat_ex = b.name
                break
        
        # Se não achar, pega a primeira disponível
        if bat_ex is None:
            bat_ex = bats2[0].name
            print(f"AVISO: Nenhuma bateria encontrada diretamente na barra {target_bus}.")
            print(f"Usando dados da bateria {bat_ex} para os gráficos de potência.")
        
        load_name_clean = assoc2[bat_ex]['load_name'] or "N/A"
        
        # --- Configuração dos Gráficos ---
        n_steps = len(v_base)
        step_ticks = np.arange(0, n_steps, max(1, n_steps//12)) 
        hour_labels = [f"{int(i*0.25):02d}:00" for i in step_ticks]
        
        fig, axs = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
        
        # Plot 1: Tensão
        axs[0].plot(v_base, 'r--', label='Sem Bateria')
        axs[0].plot(v_ctrl, 'b-', linewidth=2, label='Com Bateria')
        axs[0].axhline(0.95, color='gray', linestyle=':', alpha=0.5)
        axs[0].axhline(1.05, color='gray', linestyle=':', alpha=0.5)
        axs[0].set_ylabel("Tensão (pu)")
        axs[0].set_title(f"Tensão {target_bus}.{CONFIG['FASE_ALVO']}")
        axs[0].legend(loc='upper right')
        axs[0].grid(True, alpha=0.3)

        # Plot 2: Potência Ativa
        axs[1].plot(pv_plt[bat_ex], color='orange', ls='--', lw=1.5, label=r'Geração PV')
        axs[1].plot(ld_plt[bat_ex], color='black', ls=':', lw=1.5, label=r'Carga')
        p_b = p_ctrl[bat_ex]
        axs[1].plot(p_b, 'g-', lw=1.5, label=r'Bateria')
        axs[1].fill_between(range(len(p_b)), p_b, where=[x > 0 for x in p_b], color='green', alpha=0.2, label='Descarga')
        axs[1].fill_between(range(len(p_b)), p_b, where=[x < 0 for x in p_b], color='red', alpha=0.2, label='Carga')
        axs[1].set_ylabel("kW")
        axs[1].set_title(f"Balanço: {bat_ex}")
        axs[1].legend(loc='upper right', fontsize='small', ncol=2)
        axs[1].grid(True, alpha=0.3)

        # Plot 3: Potência Reativa
        axs[2].plot(q_ctrl[bat_ex], 'purple', lw=1.5, label=r'Bateria Q')
        axs[2].axhline(0, color='black', lw=0.8)
        axs[2].set_ylabel("kvar")
        axs[2].set_xlabel("Horário do Dia")
        axs[2].set_title("Volt-Var (Sem Banda Morta)")
        axs[2].legend(loc='upper right')
        axs[2].grid(True, alpha=0.3)
        
        axs[2].set_xticks(step_ticks)
        axs[2].set_xticklabels(hour_labels, rotation=45)

        plt.tight_layout()
        plt.show()
    else:
        print("Arquivo não encontrado.")