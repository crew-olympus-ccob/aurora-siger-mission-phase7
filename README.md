# Aurora Siger | SIFSM: Sistema Integrado de Futuro Sustentável em Marte (Fase 7)

**FIAP | Ciência da Computação | Grupo:** Gabriel, Lucas, Matheus, Miguel e Pedro

---

## Descrição

Sistema computacional desenvolvido para apoiar decisões sustentáveis na colônia Aurora Siger. Os dados operacionais da base ficam em banco relacional, com CRUD completo e tratamento de erros. Sobre eles o sistema aplica uma regra booleana de decisão implementada também em circuito lógico, organiza a operação em cinco estruturas de dados, simula o balanço energético de um sol marciano com integração matemática, estima consumo por regressão linear múltipla e oferece uma camada de agentes de IA com guardrails, tudo pelo terminal.

As fases anteriores trataram de infraestrutura (SIGIC), cognição (NCAS) e comunicação (SCIC). Esta trata de **sobrevivência com recursos finitos**: a colônia gera energia solar, armazena em bateria e consome em doze módulos, sem rede externa e sem reposição rápida de peça.

O SIFSM assume as três recomendações que a Fase 6 deixou abertas e responde à pergunta que faltava: **a colônia atravessa uma tempestade de poeira sem cortar carga?** A resposta é sim hoje, mas só porque dois módulos estão em manutenção. No pleno operacional, a mesma tempestade exige cortar 29 kW.

---

## Funcionalidades

| Bloco | Função |
|---|---|
| Banco de dados | SQLite com 7 tabelas, chaves estrangeiras e restrições de domínio |
| CRUD | Cadastrar, listar, alterar e excluir alertas, com try/except/else/finally |
| Lógica e automação | Regra booleana, simplificação por De Morgan, tabela verdade, circuito e sketch de Arduino |
| Estruturas de dados | Fila, pilha, tabela hash, árvore e grafo com Dijkstra |
| Simulação | Geração solar e carga da bateria em um sol marciano |
| Integração matemática | Simbólica (SymPy), numérica (SciPy quad) e por trapézios (NumPy) |
| Processamento de sinal | Convolução com média móvel para filtrar ruído de sensor |
| Modelagem linear | Regressão múltipla com interpretação de coeficientes e análise de colinearidade |
| Agentes de IA | Triador, especialistas, handoff, ferramentas, RAG, guardrails e sessão |
| Arquitetura | CPU, GPU, NPU, TPU, hierarquia de memória e processamento na borda |

---

## Como executar

```bash
pip install numpy pandas matplotlib seaborn scikit-learn scipy sympy

python codigo_fonte.py          # menu interativo
python codigo_fonte.py --demo   # executa tudo em sequência, sem digitar nada
```

Na primeira execução o sistema cria o banco a partir de `script_banco.sql` e gera as leituras simuladas. Nada precisa ser preparado antes.

A simulação também roda sozinha, caso queira ver essa parte isolada:

```bash
python simulacao_computacional.py   # balanço energético e integração matemática
```

**Dependências:** NumPy, Pandas, Matplotlib, Seaborn, scikit-learn, SciPy e SymPy. Todas foram trabalhadas na missão: SciPy entra pela integração numérica (`quad` e `cumulative_trapezoid`) e SymPy pela integração simbólica, ambos conteúdos desta fase; Seaborn vem da Fase 6. O banco usa `sqlite3`, e `os`, `sys`, `math`, `collections`, `datetime` e `re` são da biblioteca padrão, sem instalação. Python 3.9 ou superior.

**Sobre o SQLite:** foi escolhido porque não exige servidor nem instalação, guarda tudo em arquivo único e usa SQL padrão. O mesmo `script_banco.sql` roda em Oracle trocando `TEXT` por `VARCHAR2` e `REAL` por `NUMBER`.

---

## Módulos da colônia

| ID | Nome | Tipo | Prioridade | Consumo (kW) | Status | Origem |
|---|---|---|---|---|---|---|
| OXI | Produção de Oxigênio | suporte vital | 5/5 | 24.7 | ativo | Fase 5 |
| MED | Suporte Médico | suporte médico | 5/5 | 12.3 | ativo | Fase 5 |
| ENE | Armazenamento de Energia | energia | 5/5 | 5.4 | ativo | Fase 5 |
| COM | Comunicação | comunicação | 5/5 | 9.6 | manutenção | Fase 5 |
| HAB | Habitação | habitação | 4/5 | 18.5 | ativo | Fase 5 |
| CTR | Centro de Controle | controle | 4/5 | 15.1 | ativo | Fase 5 |
| DAT | Armazenamento de Dados | armazenamento | 4/5 | 11.2 | ativo | Fase 6 |
| COM-R | Enlace Redundante | comunicação | 3/5 | 8.9 | ativo | Fase 6 |
| BKP | Backup Redundante | armazenamento | 3/5 | 7.8 | ativo | Fase 6 |
| EXT | Antena Externa Remota | comunicação | 3/5 | 6.5 | ativo | Fase 6 |
| AGR | Agricultura | agricultura | 2/5 | 21.0 | manutenção | Fase 5 |
| LAB | Laboratório Científico | laboratório | 2/5 | 13.8 | ativo | Fase 5 |

O cadastro vem da Fase 5, com duas mudanças desta fase: a prioridade do **COM subiu de 3 para 5**, atendendo à recomendação do relatório da Fase 6, e AGR e COM entraram em manutenção por causa dos alertas herdados.

Módulos de **prioridade 2** (AGR e LAB, somando 34,8 kW) são os candidatos ao corte de carga: desligá-los não afeta suporte de vida.

A rede física entre os módulos, com as distâncias em metros, vem do grafo da Fase 4 e está na tabela `conexoes`.

---

## Arquivos da entrega

| Arquivo | Conteúdo |
|---|---|
| `codigo_fonte.py` | Arquivo principal: banco, CRUD, estruturas, regra lógica, regressão e menu |
| `simulacao_computacional.py` | Simulação energética e integração simbólica, numérica e por trapézios |
| `agentes_ia.py` | Camada multiagentes: triagem, handoff, ferramentas, RAG e guardrails |
| `script_banco.sql` | Criação das 7 tabelas e carga inicial |
| `dados_aurora_siger.csv` | Base de análise: 288 linhas, 12 módulos por 24 ciclos |
| `arduino_irrigacao.ino` | Sketch do microcontrolador com a mesma regra booleana |
| `circuito_logico.png` | Diagrama do circuito: portas lógicas, tabela verdade e esquema de ligações |
| `relatorio_tecnico.md` | Relatório técnico completo, com as 4 figuras |
| `README.md` | Este arquivo |
| `link_video.txt` | Link do vídeo no YouTube (não listado) |
| `graficos_ou_imagens/` | Os 3 gráficos gerados na execução, o circuito lógico e a evidência de execução |

O banco `aurora_siger.db` não acompanha a entrega: ele é criado na primeira execução, a partir do `script_banco.sql`.

O arquivo `graficos_ou_imagens/evidencia_execucao.txt` traz a saída completa de `python codigo_fonte.py --demo`, com 684 linhas e sem nenhum erro, como evidência de que a entrega roda de ponta a ponta.

Sobre o circuito: o enunciado aceita representação, explicação ou simulação. Optamos por representar, em `circuito_logico.png`, as portas lógicas, a tabela verdade e o esquema de ligações da placa, e por entregar o código embarcado em `arduino_irrigacao.ino`. Os pinos desenhados na figura são os mesmos declarados no sketch, de modo que diagrama e código não divergem.

---

## Menu do sistema

```
  1 - Visão geral da colônia (banco de dados)
  2 - Cadastrar, consultar, alterar e excluir (CRUD)
  3 - Regra booleana, circuito lógico e automação
  4 - Estruturas de dados (fila, pilha, hash, árvore e grafo)
  5 - Simulação energética e integração matemática
  6 - Modelagem linear e tomada de decisão
  7 - Agentes de IA, ferramentas e guardrails
  8 - Arquitetura computacional e desempenho
  9 - Sustentabilidade e cidadania digital
 10 - Análise final e gráficos
 11 - Recriar o banco e os dados simulados
  0 - Sair
```

O terminal é limpo ao voltar para o menu, então cada seção começa com a tela limpa.

---

## Exemplo de uso

**CRUD e tratamento de erros (opção 2):**

```
>>> TRATAMENTO DE ERROS: quatro tentativas inválidas de propósito
  Módulo inexistente  -> Dados inválidos: FOREIGN KEY constraint failed.
  Criticidade 7       -> Dados inválidos: CHECK constraint failed: critico IN (0, 1).
  Campo protegido     -> Campo 'codigo_modulo' não pode ser alterado.
  id inexistente      -> Nenhum alerta com id 9999.

  Nenhuma dessas tentativas derrubou o programa.
```

**Integração matemática pelos três caminhos (opção 5):**

```
--- Integração matemática: três caminhos, uma só resposta ---
  Simbólica (SymPy) ........   4055.268 kWh
  Numérica (SciPy quad) ....   4055.268 kWh  (erro estimado 1.51e-07)
  Trapézios (NumPy) ........   4055.300 kWh
  Maior divergência ........      0.032 kWh (0.0008%)
```

**Decisão de corte de carga (opção 5):**

```
  cenário                |  fator |  gerado (kWh) |  saldo (kWh) | carga mín.
  ----------------------------------------------------------------------------
  Céu limpo              |   1.00 |        4055.3 |       +993.8 |      38.6%
  Poeira moderada        |   0.70 |        2838.7 |       -222.8 |      37.3%
  Tempestade severa      |   0.45 |        1824.9 |      -1236.6 |      18.2%
```

**Agente com guardrail (opção 7):**

```
  Operador: Qual o consumo de energia da colônia e o que podemos desligar?

    guardrail_entrada  -> liberado
      O pedido cita uma ação ('desligar'), mas na forma de consulta.
    agente_triador     -> energia
    handoff            -> Agente de Energia
    ferramentas        -> consumo_por_modulo
    guardrail_saida    -> liberado (fundamentada em 1 registro do banco)
```

---

## Resultados

| Indicador | Valor |
|---|---|
| Registros no banco | 384 leituras, 12 módulos, 7 tabelas |
| Energia gerada por sol | 4055 kWh |
| Saldo em céu limpo | +994 kWh |
| Convergência das três integrações | 0,0008% |
| Redução de ruído por convolução | 53,6% |
| Modelo de consumo | R² 0,9768, MAE 0,68 kW |
| Corte exigido hoje na tempestade | 0 kW |
| **Corte exigido no pleno operacional** | **29 kW** |

O achado principal está na última linha. A colônia atravessa uma tempestade severa hoje com 18,2% de carga mínima, mas essa folga existe porque AGR e COM estão avariados. Quando voltarem ao pleno, o consumo sobe de 124,2 kW para 154,8 kW e o corte passa a ser obrigatório. É uma conclusão que nenhuma leitura isolada de sensor mostraria: foi preciso o banco guardar o histórico, a simulação projetar o cenário e o modelo estimar o consumo no pior caso.

---

## Estrutura do código

O sistema está dividido em três arquivos Python, mais o sketch do microcontrolador. O `codigo_fonte.py` é o arquivo principal e o único que precisa ser executado: ele importa os demais conforme a opção escolhida no menu.

A separação é proposital, e segue o que o enunciado prevê quando diz que um projeto pode ter mais de um arquivo Python desde que os nomes sejam organizados e intuitivos. Cada arquivo corresponde a um bloco avaliado, de modo que a parte procurada seja encontrada pelo nome:

- `simulacao_computacional.py` tem nome padronizado pelo próprio enunciado, previsto para quando a simulação fica fora do código principal.
- `agentes_ia.py` ficou à parte pelo mesmo motivo: concentra guardrails, triagem, handoff, ferramentas determinísticas e RAG num lugar só.
- `arduino_irrigacao.ino` está separado por obrigação técnica. É C++ para microcontrolador e não roda junto com o Python.

```
codigo_fonte.py
├── Bloco 1: banco de dados, CRUD e tratamento de erros
│       conectar, criar_banco, gerar_leituras,
│       crud_listar, crud_cadastrar, crud_alterar, crud_excluir
├── Bloco 2: estruturas de dados
│       FilaSolicitacoes, PilhaHistorico, IndiceSensores,
│       ArvorePrioridades, GrafoColonia (Dijkstra)
├── Bloco 3: regra booleana e circuito lógico
│       regra_irrigacao, tabela_verdade, demonstrar_simplificacao,
│       verificar_equivalencia
├── Bloco 4: carga dos dados para análise
│       carregar_base, consumo_total_ativo, cenario_corte
├── Bloco 5: opções do menu (1 a 10)
└── Interface: banner, menu_principal, limpar_terminal, main

simulacao_computacional.py
├── potencia_solar, energia_simbolica, energia_numerica, energia_trapezios
├── valor_medio_funcao, estado_de_carga, filtrar_sensor
└── simular_balanco_energetico, corte_necessario, comparar_cenarios

agentes_ia.py
├── guardrail_entrada, guardrail_saida
├── ferramentas determinísticas sobre o banco
├── recuperar_contexto (RAG), agente_triador
├── agente_energia, agente_ambiental, agente_manutencao, agente_dados
└── SessaoAgentes, atender, exibir_atendimento
```

---

*Aurora Siger. Exploramos dados. Construímos soluções. Geramos impacto para o amanhã em Marte.*
