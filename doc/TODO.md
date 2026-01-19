# Pendências

- Notebook: `geracao_curvas_carga_ieee13.ipynb`
    - Gera apenas curvas de carga, precisa implementar o PV e Bateria, para gerar o arquivo `.csv` com a curva de irradiância do PV 
- Script: `lindist3flow.py`, `opendss2lindist3flow.py`, `simulation_env.py`
    - Os códigos ainda não contemplam o PV, adiciar esta funcionalidade.
    - `lindist3flow.py`: Ler a informação do PV, e "somar" a potência deste, a carga agregada de cada barra
    - `opendss2lindist3flow.py`: Adicionar as informações do PV para exportar no `.json`
    - `simulation_env.py`: Fazer a leitura das informações do PV, fazer o calculo da potência de saída.


* Complementar o que falta (PV e bateria)

> OBS: Implementar a relação entre PV e Bateria para alimentar o lindist3flow
