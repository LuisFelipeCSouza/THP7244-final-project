# Pendências

## Notebook
- [ ] `geracao_curvas_carga_ieee13.ipynb`
  - Atualmente gera apenas curvas de carga.
  - Implementar PV e Bateria para gerar o arquivo `.csv` com a curva de irradiância do PV.

## Scripts
- [ ] `lindist3flow.py`
  - Ler a informação do PV.
  - Somar a potência do PV à carga agregada de cada barra.
- [ ] `opendss2lindist3flow.py`
  - Adicionar informações do PV para exportar no `.json`.
- [ ] `simulation_env.py`
  - Ler informações do PV.
  - Calcular a potência de saída considerando PV e Bateria.

## Geral
- [ ] Complementar o que falta (PV e Bateria).
- [ ] Implementar a relação entre PV e Bateria para alimentar o `lindist3flow`.
