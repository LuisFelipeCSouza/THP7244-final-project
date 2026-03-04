import py_dss_interface
import numpy as np
import random
import os
import sys
import csv
import matplotlib.pyplot as plt

try:
    from algoritmo_controle import OtimizadorBateria
except ImportError:
    print("❌ ERRO: 'algoritmo_controle.py' não encontrado.")
    sys.exit(1)

# ==============================================================================
#   CONFIGURAÇÕES
# ==============================================================================
CONFIG = {
    "DSS_FILE": r"C:\Users\Caio\Desktop\codigos\mestrado\trabfinalredes\Nova\13Bus-Modificado_1002\IEEE13Nodeckt.dss", # MUDAR CONFORME SEU CAMINHO LOCAL SELECIONE O ITEM 'IEEE13Nodeckt.dss'
    "BUS_ALVO": "675",      
    "FASE_ALVO": 3,         
    "SEED": 42,
    "STEP_MIN": 60,
    "HORIZONTE_MPC": 24,
    "PASSOS_SIMULACAO": 24,
    "OUTPUT_CSV": "resultados_cenario_otimo.csv" 
}

# ==============================================================================
#   CLASSE BATERIA
# ==============================================================================
class SmartBattery:
    def __init__(self, dss_obj, name, bus, kv, kw, kwh, r_th, x_th, kva_rated, num_baterias_sistema):
        self.dss = dss_obj
        self.name = name
        self.bus_full = bus
        self.kv = kv
        self.kw_rated = kw
        self.kwh_rated = kwh
        self.soc = 0.5 * kwh
        self.s_inv = kva_rated
        
        self.k_steps = CONFIG["HORIZONTE_MPC"]
        self.otimizador = OtimizadorBateria(
            kw, self.s_inv, kwh, kv*1000, r_th, x_th, 
            horizonte_k=self.k_steps, 
            num_baterias_sistema=num_baterias_sistema
        )
        self.last_p = 0.0
        self.last_q = 0.0

    def control_step(self, mode, d_kw_arr, g_kw_arr, e_kvar_arr, v_pu, eta_arr, step_h, sigma_val, zeta_arr):
        p_ref, q_ref = 0.0, 0.0
        
        if mode != "Sem Bateria":
            p_ref, q_ref, self.soc = self.otimizador.resolver_mpc(
                v_pu, d_kw_arr, g_kw_arr, e_kvar_arr, eta_arr, self.soc, step_h, sigma_val, zeta_arr
            )
        
        perc = (self.soc / self.kwh_rated) * 100.0
        dss_kw = -p_ref
        dss_kvar = -q_ref

        THRESHOLD = 0.01  
        if p_ref > THRESHOLD:
            state = "CHARGING"
        elif p_ref < -THRESHOLD:
            state = "DISCHARGING"
        else:
            state = "IDLING"

        self.dss.text(
            f"Edit Storage.{self.name} State={state} kW={dss_kw:.3f} kvar={dss_kvar:.3f} %stored={perc:.2f}"
        )
        self.last_p, self.last_q = p_ref, q_ref

# ==============================================================================
#   FUNÇÕES AUXILIARES
# ==============================================================================
def get_voltage_magnitude_pu(dss, bus_name, phase):
    dss.circuit.set_active_bus(bus_name)
    nodes = dss.bus.nodes
    vals = dss.bus.pu_voltages 
    
    if phase in nodes:
        idx = nodes.index(phase)
        re = vals[2*idx]
        im = vals[2*idx+1]
        return (re**2 + im**2)**0.5
    return 1.0 

def setup_simulation(quiet=False):
    random.seed(CONFIG["SEED"])
    dss = py_dss_interface.DSS()
    dss.text("Clear")
    if not os.path.exists(CONFIG["DSS_FILE"]): 
        print(f"❌ ERRO: Arquivo DSS não encontrado: {CONFIG['DSS_FILE']}")
        return None, [], {}
        
    dss.text(f"Compile ({CONFIG['DSS_FILE']})")
    dss.text("Set VoltageBases=[115.0, 4.16, 0.48]")
    dss.text("CalcVoltageBases")
    dss.text("Solve Mode=FaultStudy")
    
    map_loads = {}
    dss.loads.first()
    for _ in range(dss.loads.count):
        b_name = dss.cktelement.bus_names[0].split('.')[0]
        if b_name not in map_loads:
            map_loads[b_name] = {'kw': dss.loads.kw, 'kvar': dss.loads.kvar}
        dss.loads.next()

    todos_pvs = []
    dss.pvsystems.first()
    for _ in range(dss.pvsystems.count):
        todos_pvs.append({
            'name': dss.pvsystems.name,
            'bus_full': dss.cktelement.bus_names[0],
            'pmpp': dss.pvsystems.pmpp
        })
        dss.pvsystems.next()
    
    num_total_pvs = len(todos_pvs)
    num_baterias = max(1, int(num_total_pvs * 0.30))
    pvs_sorteados = random.sample(todos_pvs, num_baterias)

    if not quiet:
        print(f"   🔋 Espalhando baterias pela rede (30% de penetração)...")

    batteries = []
    assocs = {}

    for idx, pv in enumerate(pvs_sorteados):
        bus_full = pv['bus_full']
        bus_name = bus_full.split('.')[0]
        
        dss.circuit.set_active_bus(bus_name)
        z = dss.bus.zsc_matrix
        r, x = (z[0], z[1]) if z and len(z)>=2 else (0.1, 0.1)
        if r < 1e-5: r = 0.05
        kv_base = dss.bus.kv_base
        
        load_data = map_loads.get(bus_name, {'kw': 2.0, 'kvar': 0.5})
        
        kw = 1.5 * pv['pmpp']
        kwh = 2.0 * kw      
        kva = 1.2 * kw      
        
        bat_name = f"Bat_Dist_{idx+1}_{bus_name}"
        phases = 1 if '.' in bus_full else 3
        
        dss.text(f"New Storage.{bat_name} phases={phases} bus1={bus_full} kV={kv_base} kVA={kva} kWrated={kw} kWhrated={kwh} %stored=50 state=IDLING DISPMODE=EXTERNAL")
        
        b = SmartBattery(dss, bat_name, bus_full, kv_base, kw, kwh, r, x, kva, num_baterias_sistema=num_baterias)
        batteries.append(b)
        
        assocs[bat_name] = {
            'pmpp_nominal': pv['pmpp'],
            'load_kw': load_data['kw'],
            'load_kvar': load_data['kvar']
        }

    dss.text("Set Mode=Daily")
    dss.text(f"Set StepSize={CONFIG['STEP_MIN']}m")
    dss.text("Set Number=1") 
    dss.text("CalcVoltageBases")
    
    return dss, batteries, assocs

# ==============================================================================
#   LOOP PRINCIPAL DE SIMULAÇÃO
# ==============================================================================
def run_scenario(config_dict, quiet=True):
    scenario_name = config_dict["nome"]
    sigma_val = config_dict["sigma"]
    zeta_rule = config_dict["zeta"]
    
    print(f"\n▶️  Executando: {scenario_name}")
    dss, batteries, assocs = setup_simulation(quiet)
    if not dss: return None
    
    res = {"v": [], "p": [], "q": [], "perdas_kw": [], "eta": []}
    
    steps = CONFIG["PASSOS_SIMULACAO"]
    K_horizonte = CONFIG["HORIZONTE_MPC"]
    
    for i in range(steps):
        if not quiet:
            percent = (i + 1) / steps
            bar_len = 30
            filled_len = int(bar_len * percent)
            bar = '█' * filled_len + '-' * (bar_len - filled_len)
            sys.stdout.write(f'\r   [{bar}] {percent*100:.1f}% (Passo {i+1}/{steps})')
            sys.stdout.flush()
        
        p_sum, q_sum = 0, 0
        tarifa_atual = 0.0
        
        for bat in batteries:
            assoc = assocs[bat.name]
            pmpp_nominal = assoc['pmpp_nominal']
            d_kw_atual = assoc['load_kw']
            e_kvar_atual = assoc['load_kvar']
            
            target_ph = int(bat.bus_full.split('.')[1]) if '.' in bat.bus_full else 1
            v_pu = get_voltage_magnitude_pu(dss, bat.bus_full.split('.')[0], target_ph)
            
            d_arr, g_arr, e_arr, eta_arr, zeta_arr = [], [], [], [], []
            
            for k in range(K_horizonte):
                h_futura = ((i + k) * (CONFIG["STEP_MIN"]/60)) % 24
                
                if 7 <= h_futura < 9 or 17 <= h_futura < 20:
                    eta_val = 0.144
                elif 9 <= h_futura < 17 or 20 <= h_futura < 22:
                    eta_val = 0.065
                else:
                    eta_val = 0.032
                eta_arr.append(eta_val)
                if k == 0: tarifa_atual = eta_val 
                
                # Interpreta regra Zeta
                if isinstance(zeta_rule, str) and "*eta" in zeta_rule:
                    mult = float(zeta_rule.split("*")[0])
                    zeta_arr.append(mult * eta_val)
                elif zeta_rule == "eta":
                    zeta_arr.append(eta_val)
                else:
                    zeta_arr.append(float(zeta_rule))
                
                if 6 <= h_futura <= 18:
                    fator_sol = np.sin((h_futura - 6) * np.pi / 12)
                    g_arr.append(pmpp_nominal * fator_sol)
                else:
                    g_arr.append(0.0)
                    
                fator_carga = 1.3 if 18 <= h_futura <= 22 else 0.8
                d_arr.append(d_kw_atual * fator_carga)
                e_arr.append(e_kvar_atual * fator_carga)

            bat.control_step(scenario_name, d_arr, g_arr, e_arr, v_pu, eta_arr, CONFIG["STEP_MIN"]/60, sigma_val, zeta_arr)
            p_sum += bat.last_p
            q_sum += bat.last_q
            
        dss.solution.solve()
        
        v_final = get_voltage_magnitude_pu(dss, CONFIG["BUS_ALVO"], CONFIG["FASE_ALVO"])
        res["v"].append(v_final)
        res["p"].append(-p_sum)
        res["q"].append(-q_sum)
        
        perdas_totais_w = dss.circuit.losses[0]
        res["perdas_kw"].append(perdas_totais_w / 1000.0)
        res["eta"].append(tarifa_atual)
        
    if not quiet:
        print("\n   ✅ Concluído!")
    return res

if __name__ == "__main__":
    print("\n=======================================================")
    print(" SIMULAÇÃO COM PARÂMETROS ÓTIMOS (TUNING SISTEMÁTICO)")
    print("=======================================================\n")

    # Valores descobertos pela nossa metaheurística:
    SIGMA_OTIMO = 0.7457
    ZETA_MULT_OTIMO = 34.4

    # Vamos rodar a linha de base e o cenário vencedor
    SETS_PARAMETROS = [
        {"nome": "Sem Bateria", "sigma": 0.0, "zeta": "0"},
        {
            "nome": f"Cenário Ótimo (Sigma={SIGMA_OTIMO}, Zeta={ZETA_MULT_OTIMO}*eta)", 
            "sigma": SIGMA_OTIMO, 
            "zeta": f"{ZETA_MULT_OTIMO}*eta"
        }
    ]

    data = {}
    for cfg in SETS_PARAMETROS:
        r = run_scenario(cfg, quiet=False)
        if r: data[cfg["nome"]] = r

    if data:
        print("\n💾 Salvando dados em CSV...")
        
        # Monta os cabeçalhos para o CSV
        headers = ["Passo_Tempo"]
        for sc_name in data.keys():
            headers.append(f"{sc_name} - Tensão (p.u.)")
            if sc_name != "Sem Bateria":
                headers.append(f"{sc_name} - P (kW)")
                headers.append(f"{sc_name} - Q (kvar)")
        
        # Escreve o arquivo CSV usando ponto e vírgula como separador (padrão Brasil/Excel)
        with open(CONFIG["OUTPUT_CSV"], mode='w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file, delimiter=';')
            writer.writerow(headers)
            
            num_passos = len(data["Sem Bateria"]["v"])
            for i in range(num_passos):
                row = [i]
                for sc_name in data.keys():
                    row.append(f"{data[sc_name]['v'][i]:.4f}".replace('.', ','))
                    if sc_name != "Sem Bateria":
                        row.append(f"{data[sc_name]['p'][i]:.4f}".replace('.', ','))
                        row.append(f"{data[sc_name]['q'][i]:.4f}".replace('.', ','))
                writer.writerow(row)
                
        print(f"✅ Dados salvos com sucesso em: {CONFIG['OUTPUT_CSV']}")

        print("\n📊 Plotando resultados finais...")
        t = np.arange(len(data["Sem Bateria"]["v"]))
        fig, axs = plt.subplots(3, 1, figsize=(10, 12), sharex=True)
        
        # Gráfico 1: Tensão
        for sc_name, d in data.items():
            if sc_name == "Sem Bateria":
                axs[0].plot(t, d["v"], label=sc_name, lw=2, color='gray', linestyle='--')
            else:
                axs[0].plot(t, d["v"], label=sc_name, lw=2, color="blue")
                
        axs[0].set_ylabel("Tensão (p.u.)")
        axs[0].legend(loc='upper right', fontsize='small')
        axs[0].grid(True, alpha=0.3)
        axs[0].set_title(f"Tensão na Barra {CONFIG['BUS_ALVO']} (Fase {CONFIG['FASE_ALVO']})")
        axs[0].axhline(0.95, c='red', ls=':', alpha=0.7)
        axs[0].axhline(1.05, c='red', ls=':', alpha=0.7)
        
        # Gráficos 2 e 3: Potência Ativa e Reativa
        otimo_nome = SETS_PARAMETROS[1]["nome"]
        
        axs[1].plot(t, data[otimo_nome]["p"], lw=2, color="green", label="Ativa (kW)")
        axs[1].set_ylabel("kW")
        axs[1].legend(loc='upper right')
        axs[1].grid(True, alpha=0.3)
        axs[1].set_title("Potência Ativa Despachada (Soma das ~451 Baterias)")
        
        axs[2].plot(t, data[otimo_nome]["q"], lw=2, color="purple", label="Reativa (kvar)")
        axs[2].set_ylabel("kvar")
        axs[2].legend(loc='upper right')
        axs[2].grid(True, alpha=0.3)
        axs[2].set_title("Potência Reativa Despachada (Soma das ~451 Baterias)")
        axs[2].set_xlabel("Hora do Dia (Passos)")
        
        plt.tight_layout()
        nome_img = "resultado_cenario_otimo.png"
        plt.savefig(nome_img)
        print(f"\n✅ Imagem do cenário ótimo salva com sucesso em: {nome_img}")
        plt.show()