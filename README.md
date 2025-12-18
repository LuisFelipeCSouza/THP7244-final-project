# Trabalho Final da Disciplina Redes Elétricas Inteligentes: Proteção, Controle, Otimização

**Professores:**  
- Lucas Silveira  
- Raimundo Furtado  

**Data de início:** 04/12/2025  
**Prazo final de entrega:** Final de fevereiro de 2026  

---

## 📘 Contexto
Este repositório contém o desenvolvimento do trabalho final da disciplina **Redes Elétricas Inteligentes: Proteção, Controle, Otimização**.  
O trabalho é baseado na replicação dos resultados obtidos no artigo:

**Optimization-Based Operation of Distribution Grids With Residential Battery Storage: Assessing Utility and Customer Benefits**

---

## 📄 Resumo do artigo
O artigo aborda os desafios técnicos criados pelo aumento da geração distribuída de energia solar fotovoltaica (PV) em redes de distribuição, especialmente no controle de tensão.  
A proposta é um método de **otimização para despacho de baterias residenciais** que:
- Considera medições locais (behind-the-meter).  
- Utiliza potência real e reativa de forma acoplada para regulação de tensão e redução de perdas.  
- É formulado como **Local-Quadratic Program (L-QP)** baseado nas equações lineares de fluxo de potência (**LinDistFlow**).  

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

## 📦 Gerenciamento de Dependências com UV

Este projeto utiliza o **UV** para instalar e gerenciar pacotes Python.  
As dependências são registradas automaticamente no arquivo `pyproject.toml` e bloqueadas em `uv.lock`.

### ➕ Adicionar uma nova dependência

Para instalar e registrar uma biblioteca no projeto:

```bash
uv add nome-do-pacote
```

Exemplo:

```bash
uv add numpy pandas matplotlib
```

### ➕ Adicionar dependência apenas para desenvolvimento

Se a biblioteca for usada apenas em ambiente de desenvolvimento (ex.: ferramentas de teste):

```bash
uv add --dev pytest black
```

### 🔄 Atualizar dependências

Para atualizar todas as dependências para as versões mais recentes compatíveis:

```bash
uv lock --upgrade
uv sync
```

### 📑 Instalar dependências existentes
Quem clonar o repositório só precisa rodar:

```bash
uv sync
```

Isso cria o ambiente virtual `.venv` e instala todas as dependências conforme `pyproject.toml` e `uv.lock`.

---

## 📂 Arquivos importantes

- **`pyproject.toml`** → lista de dependências e metadados do projeto.  
- **`uv.lock`** → garante que todos usem as mesmas versões de pacotes.  
- **`.venv/`** → ambiente virtual criado automaticamente (não deve ser commitado).  

---