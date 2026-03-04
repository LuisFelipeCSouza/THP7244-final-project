# 🔴 Relatório de Erro Metodológico — Implementação L-QP

> **Repositório:** Simulação de Baterias Residenciais com OpenDSS e IEEE 13 Node Test Feeder  
> **Arquivos afetados:** `algoritmo_controle.py`, `cenario_opendss.py`  
> **Referência do artigo:** DE CARVALHO et al., *"Optimization-Based Operation of Distribution Grids With Residential Battery Storage"*, IEEE Transactions on Power Systems, vol. 38, n. 1, jan. 2023.

---

## 📋 Sumário

1. [Descrição do Erro](#1-descrição-do-erro)
2. [O que o Artigo Propõe](#2-o-que-o-artigo-propõe)
3. [O que o Código Atual Faz](#3-o-que-o-código-atual-faz)
4. [Comparação Visual](#4-comparação-visual)
5. [Consequências do Erro](#5-consequências-do-erro)
6. [Plano de Correção Passo a Passo](#6-plano-de-correção-passo-a-passo)
7. [Mudanças Necessárias nos Arquivos](#7-mudanças-necessárias-nos-arquivos)
8. [Checklist de Validação](#8-checklist-de-validação)

---

## 1. Descrição do Erro

O código implementa o algoritmo L-QP (Local Quadratic Program) do artigo de referência de forma **incorreta do ponto de vista metodológico**. O erro central consiste em:

> ❌ **O otimizador L-QP é resolvido repetidamente a cada passo de tempo** (horizonte rolante / MPC), quando o artigo propõe que ele seja resolvido **uma única vez no início do dia**, utilizando curvas preditivas completas de carga e geração para as 24 horas seguintes.

Esse equívoco altera fundamentalmente a natureza do problema: em vez de um **escalonamento day-ahead** (como definido no artigo), o código executa um **Controle Preditivo baseado em Modelo (MPC) com re-otimização contínua**, o que não corresponde à formulação proposta, nem aos resultados reportados nas simulações.

---

## 2. O que o Artigo Propõe

O artigo (Seção IV, parágrafo de configurações numéricas) é explícito:

> *"Customers with a battery storage system **schedule their battery power flows for the day-ahead**, i.e., T = 24 h."*

O fluxo correto descrito pelos autores é:

```
[Início do dia — t = 0 (meia-noite)]
        │
        ▼
  Coletar previsões day-ahead:
  - Perfil de carga: d(k), e(k)  para k = 1..K
  - Geração FV:     g(k)         para k = 1..K
  - Tarifa TOU:     η(k)         para k = 1..K
  - Tensão medida:  V_pu         (medição local atual)
        │
        ▼
  Resolver L-QP UMA VEZ → obtém u*(1..K) e v*(1..K)
        │
        ▼
  Aplicar o cronograma completo ao longo das 24h
  (sem re-otimizar a cada passo)
        │
        ▼
[Fim do dia — repetir no próximo dia]
```

**Parâmetros de simulação do artigo:**
| Parâmetro | Valor |
|---|---|
| Passo de tempo (Δ) | 5 minutos = 5/60 h |
| Horizonte total (K) | **288 passos** (24h × 12 passos/h) |
| Otimizações por dia | **1** (day-ahead) |
| Solver | `quadprog` (MATLAB) / equivalente Python |
| Tempo de solução | ~2 segundos por cliente |

---

## 3. O que o Código Atual Faz

### `cenario_opendss.py`

```python
CONFIG = {
    "STEP_MIN": 60,           # ❌ Passo de 60 min (artigo usa 5 min)
    "HORIZONTE_MPC": 24,      # ❌ Horizonte de apenas 24 passos
    "PASSOS_SIMULACAO": 24,   # ❌ 24 passos no total (deveria ser 288)
}

# No loop principal — ERRO CENTRAL:
for i in range(steps):          # loop roda 24 vezes
    for bat in batteries:
        bat.control_step(...)   # ❌ chama resolver_mpc() A CADA PASSO
```

### `algoritmo_controle.py`

```python
def resolver_mpc(self, v_pu_medido, ...):
    # ❌ É chamado 24 vezes ao longo do dia
    # ❌ A cada chamada, reconstrói e resolve o problema completo
    # ❌ A restrição terminal força s[K] == soc_atual (SOC do momento),
    #    não o SOC inicial do dia (s0), violando a eq. (12) do artigo
    restricoes.append(s[self.K] == soc_atual)  # ❌ deveria ser s0 fixo
```

**O comportamento resultante é:**
- 24 otimizações independentes são executadas por bateria por dia
- Cada otimização "esquece" o plano anterior e reotimiza do estado atual
- A restrição de SOC terminal muda a cada passo, tornando o problema inconsistente com o artigo
- O custo computacional é desnecessariamente multiplicado por 24×

---

## 4. Comparação Visual

```
ARTIGO (correto):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
t=0h                                                    t=24h
 │  [Resolve L-QP com K=288 pontos]                       │
 │──────────────────────────────────────────────────────►  │
 ▲                                                         │
 Única otimização                                          │
 Aplica u*(1), u*(2), ..., u*(288) em sequência           │
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CÓDIGO ATUAL (incorreto):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
t=0h   t=1h   t=2h  ...                             t=23h
 │      │      │                                      │
[LQP]  [LQP]  [LQP] ...                            [LQP]
 ▲      ▲      ▲                                      ▲
 24 otimizações separadas, cada uma com horizonte
 rolante de 24h a partir do estado atual do SOC
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 5. Consequências do Erro

| Aspecto | Impacto |
|---|---|
| **Fidelidade ao artigo** | 🔴 Crítico — o método simulado não é o L-QP proposto |
| **Restrição terminal de SOC** | 🔴 Crítico — `s[K] == soc_atual` muda a cada passo, impedindo planejamento de longo prazo coerente |
| **Granularidade temporal** | 🟠 Alto — passos de 60 min vs. 5 min do artigo perdem dinâmica intrahorária |
| **Custo computacional** | 🟡 Médio — 24× mais chamadas ao solver do que o necessário |
| **Resultados comparáveis** | 🔴 Crítico — os valores de tensão, perdas e economia não são comparáveis aos das Tabelas I e II do artigo |
| **Curvas preditivas** | 🟠 Alto — o perfil senoidal simples de FV e fator fixo de carga não refletem os dados reais do dataset [24] |

---

## 6. Plano de Correção Sugerido - Passo a Passo

### Passo 1 — Corrigir a granularidade temporal

Em `cenario_opendss.py`, alterar:

```python
# ANTES (incorreto)
CONFIG = {
    "STEP_MIN": 60,
    "HORIZONTE_MPC": 24,
    "PASSOS_SIMULACAO": 24,
}

# DEPOIS (correto, seguindo o artigo)
CONFIG = {
    "STEP_MIN": 5,             # ✅ 5 minutos como no artigo
    "K_TOTAL": 288,            # ✅ 288 passos = 24h × 12 passos/h
    "PASSOS_SIMULACAO": 288,   # ✅ simulação roda todos os 288 passos
}
```

---

### Passo 2 — Gerar as curvas preditivas completas (day-ahead) ANTES do loop

Mover a construção dos vetores `d_arr`, `g_arr`, `e_arr`, `eta_arr`, `zeta_arr` para **fora do loop de simulação**. Eles devem ser construídos uma única vez, para todos os K=288 pontos, no início do dia:

```python
# Fora do loop — construção day-ahead
def gerar_previsoes_day_ahead(assoc, K, step_h, zeta_rule):
    d_arr, g_arr, e_arr, eta_arr, zeta_arr = [], [], [], [], []
    
    for k in range(K):
        h = k * step_h  # hora do dia (0.0 a 23.917)
        
        # Tarifa TOU (igual ao artigo)
        if 7 <= h < 9 or 17 <= h < 20:
            eta = 0.144
        elif 9 <= h < 17 or 20 <= h < 22:
            eta = 0.065
        else:
            eta = 0.032
        eta_arr.append(eta)
        
        # Zeta
        if isinstance(zeta_rule, str) and "*eta" in zeta_rule:
            mult = float(zeta_rule.split("*")[0])
            zeta_arr.append(mult * eta)
        else:
            zeta_arr.append(float(zeta_rule))
        
        # Geração FV (perfil senoidal diurno)
        if 6 <= h <= 18:
            g_arr.append(assoc['pmpp_nominal'] * np.sin((h - 6) * np.pi / 12))
        else:
            g_arr.append(0.0)
        
        # Carga (perfil com pico noturno)
        fator = 1.3 if 18 <= h <= 22 else 0.8
        d_arr.append(assoc['load_kw'] * fator)
        e_arr.append(assoc['load_kvar'] * fator)
    
    return d_arr, g_arr, e_arr, eta_arr, zeta_arr
```

---

### Passo 3 — Resolver o L-QP UMA ÚNICA VEZ por bateria por dia

Refatorar `algoritmo_controle.py` para que `resolver_mpc` seja chamado **uma vez** e retorne o **cronograma completo** `u*(1..K)` e `v*(1..K)`:

```python
def resolver_dia_completo(self, v_pu_medido, d_kw_arr, g_kw_arr,
                           e_kvar_arr, eta_arr, soc_inicial,
                           step_h, sigma_val, zeta_arr):
    """
    Resolve o L-QP para as 24h completas (K passos).
    Retorna os cronogramas completos u_schedule e v_schedule.
    """
    K = self.K  # = 288
    u = cp.Variable(K)
    v = cp.Variable(K)
    s = cp.Variable(K + 1)

    # ... (mesma formulação atual, sem alteração na função objetivo) ...

    restricoes = [s[0] == soc_inicial]  # ✅ SOC inicial fixo do dia
    for k in range(K):
        restricoes.append(s[k+1] == s[k] + u[k] * step_h)
        # ... demais restrições físicas ...

    # ✅ Restrição terminal: retornar ao SOC inicial ao fim do dia
    restricoes.append(s[K] == soc_inicial)

    prob = cp.Problem(cp.Minimize(objetivo), restricoes)
    prob.solve(solver=cp.ECOS)

    # Retorna o cronograma COMPLETO
    return u.value, v.value, s.value
```

---

### Passo 4 — Armazenar o cronograma e aplicar passo a passo na simulação

No loop principal de `cenario_opendss.py`, separar a fase de **planejamento** da fase de **aplicação**:

```python
def run_scenario(config_dict, quiet=True):
    dss, batteries, assocs = setup_simulation(quiet)
    K = CONFIG["K_TOTAL"]
    step_h = CONFIG["STEP_MIN"] / 60.0

    # ── FASE 1: PLANEJAMENTO (executa UMA vez, antes do loop) ──────────────
    schedules = {}
    for bat in batteries:
        assoc = assocs[bat.name]
        v_pu_inicial = get_voltage_magnitude_pu(dss, ...)

        d_arr, g_arr, e_arr, eta_arr, zeta_arr = gerar_previsoes_day_ahead(
            assoc, K, step_h, config_dict["zeta"]
        )

        u_sched, v_sched, s_sched = bat.otimizador.resolver_dia_completo(
            v_pu_inicial, d_arr, g_arr, e_arr, eta_arr,
            bat.soc, step_h, config_dict["sigma"], zeta_arr
        )
        schedules[bat.name] = {"u": u_sched, "v": v_sched}

    # ── FASE 2: APLICAÇÃO (loop de simulação — apenas executa o plano) ─────
    res = {"v": [], "p": [], "q": [], "perdas_kw": [], "eta": []}

    for i in range(K):
        for bat in batteries:
            p_ref = schedules[bat.name]["u"][i]  # ✅ usa cronograma pré-calculado
            q_ref = schedules[bat.name]["v"][i]
            bat.aplicar_despacho(p_ref, q_ref)   # novo método simples

        dss.solution.solve()
        # ... coleta resultados ...
```

---

### Passo 5 — Corrigir o método `aplicar_despacho` na classe `SmartBattery`

Substituir `control_step` por um método mais simples que **apenas aplica** o despacho pré-calculado, sem chamar o otimizador:

```python
def aplicar_despacho(self, p_ref_kw, q_ref_kvar):
    """Aplica o despacho pré-calculado pelo cronograma day-ahead."""
    self.soc += p_ref_kw * (CONFIG["STEP_MIN"] / 60.0)
    perc = (self.soc / self.kwh_rated) * 100.0
    
    THRESHOLD = 0.01
    if p_ref_kw > THRESHOLD:
        state = "CHARGING"
    elif p_ref_kw < -THRESHOLD:
        state = "DISCHARGING"
    else:
        state = "IDLING"
    
    self.dss.text(
        f"Edit Storage.{self.name} State={state} "
        f"kW={-p_ref_kw:.3f} kvar={-q_ref_kvar:.3f} %stored={perc:.2f}"
    )
    self.last_p = p_ref_kw
    self.last_q = q_ref_kvar
```

---

### Passo 6 — (Opcional, mas recomendado) Usar dados reais de carga e FV

O artigo utiliza dados reais de 100 clientes residenciais australianos com resolução de 5 minutos (dataset NextGen [24]). Para maior fidelidade:

- Substituir o perfil senoidal de FV por dados medidos (arquivo CSV)
- Substituir os fatores fixos de carga por perfis reais por cliente
- Usar o procedimento de previsão day-ahead descrito em [11] do artigo

---

## 7. Mudanças Necessárias nos Arquivos

### `algoritmo_controle.py`

| Linha / Função | Alteração |
|---|---|
| `__init__` | Manter `self.K = 288` (não 24) |
| `resolver_mpc` → renomear para `resolver_dia_completo` | Recebe `soc_inicial` fixo do dia; retorna vetores completos `u[0..K-1]`, `v[0..K-1]` |
| Restrição terminal | `s[K] == soc_inicial` (fixo, não `soc_atual`) |

### `cenario_opendss.py`

| Seção | Alteração |
|---|---|
| `CONFIG` | `STEP_MIN=5`, `K_TOTAL=288`, `PASSOS_SIMULACAO=288` |
| `SmartBattery.control_step` | Substituir por `aplicar_despacho(p, q)` |
| `run_scenario` | Separar em Fase 1 (planejamento) e Fase 2 (aplicação) |
| Construção de `d_arr`, `g_arr` | Mover para fora do loop, gerar vetores de 288 pontos |

---

## 8. Checklist de Validação

Após a correção, os resultados devem ser comparados com as Tabelas I e II do artigo.

- [ ] O otimizador é chamado **uma vez por bateria por dia**
- [ ] Os vetores de entrada (`d_arr`, `g_arr`, `eta_arr`) têm **288 elementos**
- [ ] O passo de tempo é **5 minutos** (Δ = 5/60 h)
- [ ] A restrição terminal é **`s[288] == s0`** (SOC inicial do dia, valor fixo)
- [ ] O loop de simulação aplica `u*(i)` e `v*(i)` diretamente, **sem re-otimizar**
- [ ] A tensão no nó 675 (fase C) apresenta **redução dos desvios** em relação à baseline
- [ ] As perdas totais no IEEE 13NF são **menores com L-QP** do que com Benchmark
- [ ] A economia média por cliente com L-QP é **ligeiramente menor** do que com Benchmark (conforme Tabela I)

---

> **Nota:** A abordagem MPC com horizonte rolante (como implementada atualmente) é uma extensão válida e encontrada na literatura, mas representa um **algoritmo diferente** do L-QP day-ahead proposto no artigo. Se o objetivo é implementar e validar exatamente o método do artigo, as correções acima são obrigatórias.
