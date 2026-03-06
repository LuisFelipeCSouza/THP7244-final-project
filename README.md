# Trabalho Final da Disciplina Redes Elétricas Inteligentes: Proteção, Controle, Otimização

**Professores:**  

- Lucas Silveira
- Raimundo Furtado  

**Data de início:** 04/12/2025  
**Prazo final de entrega:** Final de fevereiro de 2026  

---

## 📘 Contexto

Este repositório contém o desenvolvimento do trabalho final da disciplina **Redes Elétricas Inteligentes: Proteção, Controle, Otimização**.  
O trabalho é baseado na replicação dos resultados obtidos no artigo: [**Optimization-Based Operation of Distribution Grids With Residential Battery Storage: Assessing Utility and Customer Benefits**](https://ieeexplore.ieee.org/document/9744477)

---

## 📄 Resumo do artigo

O artigo aborda os desafios técnicos criados pelo aumento da geração distribuída de energia solar fotovoltaica (PV) em redes de distribuição, especialmente no controle de tensão.  
A proposta é um método de **otimização para despacho de baterias residenciais** que:

- Considera medições locais (behind-the-meter).  

- Utiliza potência real e reativa de forma acoplada para regulação de tensão e redução de perdas.  
- É formulado como **Local-Quadratic Program (L-QP)** baseado nas equações lineares de fluxo de potência ([**LinDist3Flow**](https://arxiv.org/abs/1606.04492)).  

Os testes foram realizados nos sistemas **IEEE 13 barras** e **IEEE 123 barras**, com dados realistas de carga residencial e geração PV.  
Os resultados demonstram vantagens técnicas e econômicas da abordagem proposta.

---

## 🎯 Objetivos do Trabalho

Os itens a serem desenvolvidos são:

1. Elaboração de uma **apresentação explicativa** sobre os pontos mais importantes do artigo.  
2. Atualização da **revisão bibliográfica** relacionada ao tema.  
3. **Modelagem dos sistemas de distribuição** (13 barras e 123 barras) utilizando as bibliotecas **OpenDER** e **OpenDERinterface**.  
4. Implementação do **fluxo de potência ótimo** conforme descrito no artigo.  
5. Comparação dos resultados obtidos com os apresentados no artigo.  
6. Implementação de algum dos pontos sugeridos na **conclusão como trabalho futuro**.  

---

## 📅 Cronograma

- **Janeiro 2026:** Primeira entrega parcial.  
- **Fevereiro 2026 (início):** Segunda entrega parcial.  
- **Fevereiro 2026 (final):** Entrega final do trabalho.  

Reuniões de orientação podem ser agendadas nos horários previstos para as aulas da disciplina.  
> ⚠️ **Importante:** Não serão tiradas dúvidas técnicas por WhatsApp.

---

## 📦 Instalação das Dependências

Este projeto utiliza o **UV** para gerenciar os pacotes Python, garantindo a reprodutibilidade do ambiente para todos os membros da equipe. 

Para instalar todas as dependências necessárias, basta clonar o repositório e executar o seguinte comando na raiz do projeto:

```bash
uv sync
```

Isso criará automaticamente o ambiente virtual (`.venv`) e instalará todas as bibliotecas exatas conforme configurado no projeto.

---

## 🗂️ Estrutura do Projeto

O repositório está organizado de forma modular para separar dados, código-fonte e resultados:

- **`data/`**: Contém todos os insumos da simulação. Inclui as modelagens dos circuitos no OpenDSS (sistemas da IEEE de 13, 34 e 123 barras) e as bases de dados de perfis de carga e geração fotovoltaica.

- **`src/`**: Guarda o "motor" matemático e de controle do projeto. Aqui ficam os módulos Python reutilizáveis (classes e funções), como o algoritmo do MPC, modelagem LinDist3Flow e ambiente de simulação.

- **`scripts/`**: Contém os arquivos de execução principal (ex: `main.py` e cenários do OpenDSS). É por aqui que as simulações e o tuning da metaheurística devem ser inicializados.

- **`notebooks/`**: Ambientes de experimentação em Jupyter Notebook. Usados para Análise Exploratória de Dados (EDA), limpeza de bases sintéticas e testes isolados nos circuitos.

- **`output/`**: Pasta destinada a armazenar os resultados gerados após a execução dos scripts, como tabelas `.csv` e gráficos `.png`.

- **`doc/`**: Documentação de apoio do projeto, relatórios metodológicos e anotações gerais.

## 🗂️ Arquivos Descontinuados

Mudanças de estratégias fizeram com o desenvolvimento de alguns códigos fossem descontinuádos, a saber:

- [`src/lindist3flow.py`](src/lindist3flow.py)

- [`src/opendss2lindist3flow.py`](src/opendss2lindist3flow.py)

- [`src/simulation_env.py`](src/simulation_env.py)
