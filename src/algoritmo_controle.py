import cvxpy as cp
import numpy as np
import logging

class OtimizadorBateria:
    def __init__(self, kw_rated, kva_rated, kwh_rated, v_base_v, r_ohm, x_ohm, horizonte_k=24, num_baterias_sistema=10):
        """
        Inicializa o otimizador L-QP (Local Quadratic Program) com horizonte MPC.
        """
        self.P_MAX = kw_rated
        self.P_MIN = -kw_rated
        self.S_INV = kva_rated
        self.E_MAX = kwh_rated
        self.E_MIN = 0.0
        self.K = horizonte_k  # Horizonte de predição (MPC)
        self.num_baterias_sistema = num_baterias_sistema
        
        # Limite máximo de potência reativa
        self.Q_MAX = np.sqrt(self.S_INV**2 - self.P_MAX**2)
        
        # Bases para conversão em p.u.
        self.S_BASE_KVA = 1000.0 
        self.S_BASE_VA = self.S_BASE_KVA * 1000.0
        self.Z_BASE = (v_base_v ** 2) / self.S_BASE_VA
        
        # Impedâncias p.u.
        self.R_PU = r_ohm / self.Z_BASE
        self.X_PU = x_ohm / self.Z_BASE
        
        self.V_0 = 1.0          # Tensão nominal (subestação / p.u.)
        self.V_THR = 1.10       # Tensão de limiar/alvo (p.u.) do artigo (IEEE 13NF)
        
        # Regra 6: Cálculo explícito do coeficiente de extensão rho_cm
        v_max_pu = self.Q_MAX / self.S_BASE_KVA
        u_max_pu = self.P_MAX / self.S_BASE_KVA
        
        numerador = 2 * (self.R_PU * u_max_pu + self.X_PU * v_max_pu)
        denominador = (self.V_0**2) - (self.V_THR**2)
        
        # Evitar divisão por zero caso V_0 == V_THR
        if abs(denominador) < 1e-6:
            self.RHO_CM = 1.0
        else:
            self.RHO_CM = abs(numerador / denominador)

        self.installed_solvers = cp.installed_solvers()

    def resolver_mpc(self, v_pu_medido, d_kw_arr, g_kw_arr, e_kvar_arr, eta_arr, soc_atual, step_h, sigma_val, zeta_arr):
        """
        Resolve o L-QP recebendo dinamicamente sigma_val e zeta_arr para permitir
        o tuning sistemático focado em ganhos do cliente, tensão ou redução de perdas.
        """
        # ==========================================================
        # Regra 1: Vetores de decisão multi-período
        # ==========================================================
        u = cp.Variable(self.K, name="u") # Potência Ativa (u > 0 = CARGA da bateria)
        v = cp.Variable(self.K, name="v") # Potência Reativa
        s = cp.Variable(self.K + 1, name="s") # SOC da bateria
        
        # Transformando previsões em p.u.
        d_pu = np.array(d_kw_arr) / self.S_BASE_KVA
        g_pu = np.array(g_kw_arr) / self.S_BASE_KVA
        e_pu = np.array(e_kvar_arr) / self.S_BASE_KVA
        
        # ==========================================================
        # Balanço de Potência na visão da rede (p_cm)
        # u > 0 aumenta a carga puxada da rede (bateria carregando)
        # ==========================================================
        p_cm = d_pu - g_pu + (u / self.S_BASE_KVA)
        q_cm = e_pu + (v / self.S_BASE_KVA) 

        custo_energia = 0
        reg_tensao = 0
        perdas = 0

        # Regras 4 e 5: Somatório ao longo do horizonte (Equação 32 do artigo)
        for k in range(self.K):
            # 1. Custo financeiro (Psi) em função da tarifa TOU (eta_arr)
            custo_energia += eta_arr[k] * (p_cm[k] * self.S_BASE_KVA) * step_h
            
            # 2. Regulação de tensão local com o sigma exato do tuning (E_til)
            E_til = 2 * (self.R_PU * p_cm[k] + self.X_PU * q_cm[k]) + self.RHO_CM * (self.V_0**2 - v_pu_medido**2)
            reg_tensao += sigma_val * cp.square(E_til) * step_h
            
            # 3. Perdas de linha com zeta dinâmico (zeta_arr)
            L_cm_pu = (self.R_PU / (self.V_0**2)) * (cp.square(p_cm[k]) + cp.square(q_cm[k]))
            L_cm_kw = L_cm_pu * self.S_BASE_KVA
            perdas += zeta_arr[k] * L_cm_kw * step_h
            
        objetivo = cp.Minimize(custo_energia + reg_tensao + perdas)
        
        # ==========================================================
        # Regras 2, 3 e 7: Restrições do Sistema
        # ==========================================================
        restricoes = []
        restricoes.append(s[0] == soc_atual)
        
        for k in range(self.K):
            # Dinâmica do SOC 
            restricoes.append(s[k+1] == s[k] + (u[k] * step_h))
            
            # Limites físicos e de caixa (limites de V adicionados)
            restricoes.append(u[k] >= self.P_MIN)
            restricoes.append(u[k] <= self.P_MAX)
            restricoes.append(v[k] >= -self.Q_MAX)
            restricoes.append(v[k] <= self.Q_MAX)
            restricoes.append(cp.norm(cp.hstack([u[k], v[k]])) <= self.S_INV)
            
            # Limites do SOC
            restricoes.append(s[k+1] >= self.E_MIN)
            restricoes.append(s[k+1] <= self.E_MAX)
            
        # Restrição obrigatória do artigo para evitar descarga precoce no final do dia
        restricoes.append(s[self.K] == soc_atual)
        
        prob = cp.Problem(objetivo, restricoes)
        
        try:
            if 'ECOS' in self.installed_solvers:
                prob.solve(solver=cp.ECOS, warm_start=True)
            else:
                prob.solve(solver=cp.SCS, warm_start=True)
                
            if prob.status not in ["optimal", "optimal_inaccurate"]:
                prob.solve(solver=cp.OSQP, warm_start=True)
                
        except Exception as e:
            logging.warning(f"[L-QP] Solver falhou: {e}")

        # ==========================================================
        # Regra 8: Retornar apenas u(1) e v(1)
        # ==========================================================
        if u.value is not None and v.value is not None:
            p_opt = float(u.value[0])
            q_opt = float(v.value[0])
            soc_opt = float(s.value[1])
        else:
            logging.warning(f"[L-QP] Status: {prob.status} -> fallback (0,0)")
            p_opt, q_opt, soc_opt = 0.0, 0.0, soc_atual
            
        return p_opt, q_opt, soc_opt