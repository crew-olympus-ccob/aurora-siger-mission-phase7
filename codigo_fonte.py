"""
===============================================================================
 SIFSM: SISTEMA INTEGRADO DE FUTURO SUSTENTÁVEL EM MARTE
 Aurora Siger | Base Harmonia-7 | FIAP, Ciência da Computação, Fase 7
 Grupo: Gabriel, Lucas, Matheus, Miguel e Pedro
-------------------------------------------------------------------------------
 Arquivo principal do sistema.

 CONTINUIDADE DA MISSÃO
   Fase 4, SIGIC: mapeou a infraestrutura da colônia como um grafo, com as
                  distâncias físicas entre os módulos. Esse grafo é reusado
                  aqui, na tabela conexoes.
   Fase 5, NCAS:  núcleo cognitivo com arquivos texto e JSON, regras booleanas
                  e prompts. Dele vêm o cadastro de módulos e os operadores.
   Fase 6, SCIC:  análise de latência, que descobriu a antena do módulo COM se
                  degradando e deixou três recomendações em aberto.
   Fase 7, SIFSM: este sistema leva tudo para um banco de dados relacional,
                  acrescenta a camada de energia e sustentabilidade e assume
                  as três pendências da fase anterior como alertas ativos.

 O QUE O SISTEMA FAZ
   Organiza os dados da colônia em banco SQLite com CRUD completo, aplica uma
   regra booleana de decisão implementada também como circuito lógico, usa
   cinco estruturas de dados para organizar a operação, simula o balanço
   energético de um sol marciano com integração matemática, estima consumo por
   regressão linear múltipla e oferece uma camada de agentes de IA com
   guardrails sobre o próprio banco.

 EXECUÇÃO
   Modo interativo:    python codigo_fonte.py
   Modo demonstração:  python codigo_fonte.py --demo

 DEPENDÊNCIAS
   numpy, pandas, matplotlib, seaborn, scikit-learn, scipy e sympy.
   Todas foram trabalhadas nesta fase ou nas anteriores da missão.
   O banco usa sqlite3, que já vem com o Python.
===============================================================================
"""

import os
import sys
import math
import sqlite3
from collections import deque
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")  # backend sem janela: salva os gráficos em arquivo
import matplotlib.pyplot as plt
import seaborn as sns

from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

# Módulos do próprio projeto
try:
    import simulacao_computacional as sim
    import agentes_ia as ia
except ImportError as erro:  # pragma: no cover
    print(f"[ERRO] Arquivo do projeto não encontrado: {erro}")
    print("       codigo_fonte.py, simulacao_computacional.py e agentes_ia.py")
    print("       precisam estar na mesma pasta.")
    sys.exit(1)

# Acentuação correta mesmo em terminais Windows com codificação legada
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass

# -----------------------------------------------------------------------------
# CONFIGURAÇÕES GERAIS
# -----------------------------------------------------------------------------
PASTA = os.path.dirname(os.path.abspath(__file__))
ARQUIVO_BANCO = os.path.join(PASTA, "aurora_siger.db")
ARQUIVO_SQL = os.path.join(PASTA, "script_banco.sql")
ARQUIVO_CSV = os.path.join(PASTA, "dados_aurora_siger.csv")
PASTA_GRAFICOS = os.path.join(PASTA, "graficos_ou_imagens")

CICLOS = 24                  # sóis marcianos simulados
DATA_INICIAL = "2026-09-27"  # dia seguinte ao último ciclo da Fase 6
UMIDADE_LIMITE = 35.0        # abaixo disso o cultivo precisa de irrigação
CARGA_MINIMA_PCT = 15.0      # piso de segurança da bateria

# Os valores de dado ficam sem acento no banco, porque são usados para filtrar
# e agrupar. A acentuação é aplicada só na hora de exibir.
ROTULOS = {
    "ATIVO": "ativo", "ALERTA": "alerta", "MANUTENCAO": "manutenção",
    "habitacao": "habitação", "suporte_medico": "suporte médico",
    "suporte_vida": "suporte vital", "comunicacao": "comunicação",
    "laboratorio": "laboratório", "agricultura": "agricultura",
    "armazenamento": "armazenamento", "controle": "controle", "energia": "energia",
}


def rotulo(valor):
    """Texto acentuado de um valor de dado, só para exibição."""
    return ROTULOS.get(str(valor), str(valor))


sns.set_theme(style="whitegrid")
pd.set_option("display.width", 170)
pd.set_option("display.max_columns", 30)


# =============================================================================
# BLOCO 1: BANCO DE DADOS, CRUD E TRATAMENTO DE ERROS
# =============================================================================
def conectar():
    """Abre a conexão com o banco, ligando a checagem de chave estrangeira.

    O SQLite não valida chave estrangeira por padrão: o PRAGMA abaixo liga
    essa checagem, para que um alerta não aponte para um módulo inexistente."""
    con = sqlite3.connect(ARQUIVO_BANCO)
    con.execute("PRAGMA foreign_keys = ON")
    return con


def criar_banco(forcar=False):
    """Cria o banco a partir de script_banco.sql e gera as leituras simuladas.

    Usa try/except/else/finally para separar com clareza o que é erro de
    arquivo, erro de SQL e o encerramento da conexão."""
    if os.path.exists(ARQUIVO_BANCO) and not forcar:
        return False

    con = None
    try:
        with open(ARQUIVO_SQL, encoding="utf-8") as arquivo:
            script = arquivo.read()
        con = sqlite3.connect(ARQUIVO_BANCO)
        con.executescript(script)
    except FileNotFoundError:
        print(f"\n[ERRO] script_banco.sql não encontrado em {PASTA}.")
        print("       O arquivo faz parte da entrega e precisa estar na pasta.")
        return False
    except sqlite3.Error as erro:
        print(f"\n[ERRO] Falha ao criar o banco: {erro}")
        return False
    else:
        con.commit()
        print("\n[OK] Banco criado a partir de script_banco.sql.")
    finally:
        if con is not None:
            con.close()

    gerar_leituras()
    return True


def gerar_leituras(exibir=True):
    """Gera a telemetria simulada dos 24 ciclos e grava no banco e no CSV.

    PROCESSO GERADOR, documentado para que o resultado seja auditável:

        consumo = base_do_módulo
                + 0,080 x ocupação (%)
                + 0,120 x (frio externo em graus abaixo de -20 C)
                + 6,000 x (1 - fator_de_luz)
                + ruído

    A relação é linear de propósito: é ela que a regressão do BLOCO 6 precisa
    recuperar. Os coeficientes têm leitura física direta, ou seja, cada 10% de
    ocupação pesa 0,8 kW, cada grau a menos de temperatura externa pesa
    0,12 kW e uma tempestade fechada soma 6 kW de consumo por módulo.

    A semente é fixa (42), então a base é sempre a mesma."""
    rng = np.random.default_rng(42)
    con = conectar()
    try:
        modulos = con.execute(
            "SELECT codigo, tipo, prioridade, consumo_kw FROM modulos").fetchall()
        sensores = con.execute(
            "SELECT codigo_sensor, codigo_modulo, grandeza FROM sensores").fetchall()
        por_modulo = {}
        for cod_sensor, cod_modulo, grandeza in sensores:
            por_modulo.setdefault((cod_modulo, grandeza), cod_sensor)

        linhas_csv, leituras = [], []
        for ciclo in range(1, CICLOS + 1):
            data = (pd.Timestamp(DATA_INICIAL) + timedelta(days=ciclo - 1)).strftime("%Y-%m-%d")

            # Tempestade de poeira nos ciclos 10 a 14: o fator de luz cai
            if 10 <= ciclo <= 14:
                fator_luz = float(rng.uniform(0.45, 0.70))
            else:
                fator_luz = float(rng.uniform(0.88, 1.00))

            temperatura_externa = float(rng.normal(-55.0, 12.0))
            geracao = sim.POTENCIA_PICO_KW * fator_luz * (2 / math.pi)

            for codigo, tipo, prioridade, consumo_base in modulos:
                ocupacao = float(np.clip(rng.normal(45 + prioridade * 6, 15), 5, 99))
                frio = max(0.0, -temperatura_externa - 20.0)
                consumo = (consumo_base
                           + 0.080 * ocupacao
                           + 0.120 * frio
                           + 6.000 * (1 - fator_luz)
                           + float(rng.normal(0, 0.8)))
                consumo = round(max(consumo, 0.5), 2)

                linhas_csv.append({
                    "ciclo": ciclo,
                    "data": data,
                    "codigo_modulo": codigo,
                    "tipo_modulo": tipo,
                    "prioridade": prioridade,
                    "consumo_base_kw": consumo_base,
                    "consumo_kw": consumo,
                    "ocupacao_pct": round(ocupacao, 1),
                    "temperatura_externa_c": round(temperatura_externa, 1),
                    "fator_luz": round(fator_luz, 3),
                    "geracao_solar_kw": round(geracao, 2),
                })

                sensor = por_modulo.get((codigo, "consumo"))
                if sensor:
                    leituras.append((sensor, ciclo, data, consumo))

            # Sensores específicos de alguns módulos
            umidade = float(np.clip(rng.normal(38 - 8 * (1 - fator_luz), 9), 5, 95))
            if por_modulo.get(("AGR", "umidade")):
                leituras.append((por_modulo[("AGR", "umidade")], ciclo, data, round(umidade, 1)))
            if por_modulo.get(("AGR", "luminosidade")):
                leituras.append((por_modulo[("AGR", "luminosidade")], ciclo, data,
                                 round(float(rng.uniform(200, 900)) * fator_luz, 1)))
            if por_modulo.get(("HAB", "temperatura")):
                leituras.append((por_modulo[("HAB", "temperatura")], ciclo, data,
                                 round(float(rng.normal(21.5, 1.2)), 1)))
            if por_modulo.get(("ENE", "geracao_solar")):
                leituras.append((por_modulo[("ENE", "geracao_solar")], ciclo, data, round(geracao, 2)))
            if por_modulo.get(("ENE", "carga_bateria")):
                leituras.append((por_modulo[("ENE", "carga_bateria")], ciclo, data,
                                 round(float(np.clip(rng.normal(70 - 25 * (1 - fator_luz), 10), 5, 100)), 1)))

            # Latências herdadas da Fase 6: COM segue degradando, COM-R estável
            for cod_mod, base, cresce in [("COM", 47.0, 0.95), ("COM-R", 48.0, 0.0),
                                          ("EXT", 70.0, 0.0)]:
                sensor = por_modulo.get((cod_mod, "latencia"))
                if sensor:
                    valor = base + cresce * ciclo + 31.0 * (1 - fator_luz) + float(rng.normal(0, 3.2))
                    leituras.append((sensor, ciclo, data, round(max(valor, 5.0), 2)))

            for cod_mod in ["DAT", "BKP"]:
                sensor = por_modulo.get((cod_mod, "carga_dados"))
                if sensor:
                    leituras.append((sensor, ciclo, data, round(float(rng.uniform(120, 480)), 1)))

        con.execute("DELETE FROM leituras")
        con.executemany(
            "INSERT INTO leituras (codigo_sensor, ciclo, data, valor) VALUES (?, ?, ?, ?)",
            leituras)
        con.commit()
    except sqlite3.Error as erro:
        print(f"\n[ERRO] Falha ao gravar as leituras: {erro}")
        return None
    finally:
        con.close()

    base = pd.DataFrame(linhas_csv)
    base.to_csv(ARQUIVO_CSV, index=False, encoding="utf-8")

    if exibir:
        print(f"[OK] {len(leituras)} leituras gravadas no banco.")
        print(f"[OK] {len(base)} linhas exportadas para dados_aurora_siger.csv.")
    return base


# ---- CRUD sobre a tabela de alertas -----------------------------------------
def crud_listar(con, apenas_abertos=False):
    """READ: lista os alertas registrados."""
    sql = "SELECT id, codigo_modulo, tipo, critico, mensagem, data, resolvido FROM alertas"
    if apenas_abertos:
        sql += " WHERE resolvido = 0"
    sql += " ORDER BY resolvido, critico DESC, id"
    return con.execute(sql).fetchall()


def crud_cadastrar(con, codigo_modulo, tipo, critico, mensagem):
    """CREATE: insere um alerta novo, validando a entrada.

    O try/except separa três situações: módulo inexistente (viola a chave
    estrangeira), valor fora do domínio (viola o CHECK) e qualquer outra
    falha do banco."""
    data = datetime.now().strftime("%Y-%m-%d")
    try:
        cursor = con.execute(
            "INSERT INTO alertas (codigo_modulo, tipo, critico, mensagem, data, resolvido) "
            "VALUES (?, ?, ?, ?, ?, 0)",
            (codigo_modulo.upper(), tipo, int(critico), mensagem, data))
        con.commit()
    except sqlite3.IntegrityError as erro:
        return None, (f"Dados inválidos: {erro}. Confira se o módulo existe e se "
                      "a criticidade é 0 ou 1.")
    except sqlite3.Error as erro:
        return None, f"Falha no banco de dados: {erro}"
    else:
        return cursor.lastrowid, f"Alerta #{cursor.lastrowid} cadastrado."


def crud_alterar(con, id_alerta, campo, valor):
    """UPDATE: altera um campo do alerta.

    O nome do campo é validado contra uma lista fechada antes de entrar no
    SQL, o que evita injeção por interpolação de identificador."""
    permitidos = {"tipo", "critico", "mensagem", "resolvido"}
    if campo not in permitidos:
        return False, f"Campo '{campo}' não pode ser alterado. Use: {', '.join(sorted(permitidos))}."
    try:
        cursor = con.execute(f"UPDATE alertas SET {campo} = ? WHERE id = ?", (valor, id_alerta))
        con.commit()
    except sqlite3.Error as erro:
        return False, f"Falha ao alterar: {erro}"
    else:
        if cursor.rowcount == 0:
            return False, f"Nenhum alerta com id {id_alerta}."
        return True, f"Alerta #{id_alerta} atualizado: {campo} = {valor}."


def crud_excluir(con, id_alerta):
    """DELETE: remove um alerta pelo id."""
    try:
        cursor = con.execute("DELETE FROM alertas WHERE id = ?", (id_alerta,))
        con.commit()
    except sqlite3.Error as erro:
        return False, f"Falha ao excluir: {erro}"
    else:
        if cursor.rowcount == 0:
            return False, f"Nenhum alerta com id {id_alerta}."
        return True, f"Alerta #{id_alerta} excluído."


# =============================================================================
# BLOCO 2: ESTRUTURAS DE DADOS
# =============================================================================
class FilaSolicitacoes:
    """FILA de atendimento da tripulação, em duas faixas de urgência.

    Solicitações de urgência 4 ou 5 entram na fila prioritária; o resto vai
    para a fila normal. Dentro de cada faixa vale a ordem de chegada, que é o
    comportamento clássico de fila (FIFO). Usa collections.deque, com remoção
    da frente em tempo constante, diferente de uma lista comum."""

    def __init__(self):
        self.prioritaria = deque()
        self.normal = deque()

    def enfileirar(self, solicitacao):
        if solicitacao["urgencia"] >= 4:
            self.prioritaria.append(solicitacao)
        else:
            self.normal.append(solicitacao)

    def atender(self):
        if self.prioritaria:
            return self.prioritaria.popleft()
        if self.normal:
            return self.normal.popleft()
        return None

    def __len__(self):
        return len(self.prioritaria) + len(self.normal)


class PilhaHistorico:
    """PILHA de ações executadas, com desfazer.

    O último registro entra e é o primeiro a sair (LIFO), que é exatamente o
    comportamento de um desfazer. Cada ação guarda a informação necessária
    para ser revertida no banco."""

    def __init__(self):
        self.itens = []

    def empilhar(self, acao):
        self.itens.append(acao)

    def desempilhar(self):
        return self.itens.pop() if self.itens else None

    def topo(self):
        return self.itens[-1] if self.itens else None

    def __len__(self):
        return len(self.itens)


class IndiceSensores:
    """TABELA HASH para busca de sensor em tempo constante.

    O dicionário do Python é uma tabela hash: a chave vira posição por meio da
    função de espalhamento, então a busca não depende da quantidade de
    registros. Com 16 sensores a diferença é pequena, mas a estrutura é a que
    sustenta a consulta quando a colônia crescer para milhares deles."""

    def __init__(self):
        self.por_codigo = {}
        self.por_modulo = {}
        self.colisoes_simuladas = 0

    def inserir(self, codigo_sensor, codigo_modulo, grandeza, unidade):
        registro = {"codigo": codigo_sensor, "modulo": codigo_modulo,
                    "grandeza": grandeza, "unidade": unidade}
        self.por_codigo[codigo_sensor.upper()] = registro
        self.por_modulo.setdefault(codigo_modulo, []).append(registro)

    def buscar(self, codigo_sensor):
        return self.por_codigo.get(str(codigo_sensor).upper())

    def do_modulo(self, codigo_modulo):
        return self.por_modulo.get(codigo_modulo, [])

    def posicao_hash(self, codigo_sensor, tamanho_tabela=16):
        """Mostra em qual balde a chave cairia, para fins didáticos."""
        return hash(str(codigo_sensor).upper()) % tamanho_tabela

    def __len__(self):
        return len(self.por_codigo)


class NoArvore:
    """Nó da árvore de prioridades."""

    def __init__(self, nome, nivel=None):
        self.nome = nome
        self.nivel = nivel
        self.filhos = []

    def adicionar(self, filho):
        self.filhos.append(filho)
        return filho


class ArvorePrioridades:
    """ÁRVORE de classificação dos módulos por criticidade.

    Organiza a colônia em três níveis de resposta. A hierarquia importa porque
    o corte de carga desce a árvore de baixo para cima: primeiro sai o que
    está na folha menos crítica, e o suporte de vida é o último a ser tocado."""

    def __init__(self):
        self.raiz = NoArvore("Aurora Siger")

    def montar(self, modulos):
        faixas = {
            "Suporte de vida (prioridade 5)": [5],
            "Operação essencial (prioridade 4)": [4],
            "Apoio e pesquisa (prioridade 1 a 3)": [1, 2, 3],
        }
        for nome, niveis in faixas.items():
            galho = self.raiz.adicionar(NoArvore(nome))
            for codigo, nome_mod, prioridade, consumo in modulos:
                if prioridade in niveis:
                    galho.adicionar(NoArvore(f"{codigo} ({nome_mod}), {consumo:.1f} kW",
                                             prioridade))
        return self.raiz

    def percorrer(self, no=None, profundidade=0, saida=None):
        """Percurso em profundidade, devolvendo as linhas já indentadas."""
        if saida is None:
            saida = []
        if no is None:
            no = self.raiz
        saida.append(("  " * profundidade) + ("- " if profundidade else "") + no.nome)
        for filho in no.filhos:
            self.percorrer(filho, profundidade + 1, saida)
        return saida

    def folhas_cortaveis(self):
        """Devolve as folhas do galho menos crítico, que é por onde o corte começa."""
        for galho in self.raiz.filhos:
            if "Apoio e pesquisa" in galho.nome:
                return [f.nome for f in galho.filhos]
        return []


class GrafoColonia:
    """GRAFO da rede física da colônia, herdado da Fase 4 (SIGIC).

    Cada módulo é um vértice e cada ligação física é uma aresta com a
    distância em metros. Sobre essa estrutura roda o Dijkstra, que responde
    por qual caminho a energia deve ser enviada de um módulo a outro com a
    menor perda de transmissão."""

    INFINITO = float("inf")

    def __init__(self):
        self.adjacencia = {}

    def carregar(self, modulos, conexoes):
        self.adjacencia = {codigo: [] for codigo in modulos}
        for origem, destino, distancia in conexoes:
            self.adjacencia[origem].append((destino, distancia))
            self.adjacencia[destino].append((origem, distancia))
        return self

    def dijkstra(self, origem):
        """Menor caminho de um módulo para todos os outros.

        Implementado com seleção do menor pendente a cada passo, sem heap,
        para deixar o algoritmo visível. Com 12 vértices o custo é
        irrelevante; numa rede grande valeria a fila de prioridade."""
        distancia = {no: self.INFINITO for no in self.adjacencia}
        anterior = {no: None for no in self.adjacencia}
        distancia[origem] = 0
        pendentes = set(self.adjacencia)

        while pendentes:
            atual = min(pendentes, key=lambda no: distancia[no])
            if distancia[atual] == self.INFINITO:
                break
            pendentes.remove(atual)
            for vizinho, peso in self.adjacencia[atual]:
                if vizinho in pendentes:
                    candidato = distancia[atual] + peso
                    if candidato < distancia[vizinho]:
                        distancia[vizinho] = candidato
                        anterior[vizinho] = atual
        return distancia, anterior

    def caminho(self, anterior, destino):
        rota, atual = [], destino
        while atual is not None:
            rota.insert(0, atual)
            atual = anterior[atual]
        return rota

    def grau(self, no):
        return len(self.adjacencia.get(no, []))


# =============================================================================
# BLOCO 3: REGRA BOOLEANA E CIRCUITO LÓGICO
# =============================================================================
def regra_irrigacao(agr_ativo, umidade_baixa, sensor_ok, reserva_ok):
    """Regra de decisão do SIFSM para liberar irrigação do cultivo.

        IRRIGAR = AGR_ATIVO AND UMIDADE_BAIXA AND SENSOR_OK AND RESERVA_OK

    Em palavras: só irriga se o módulo agrícola estiver operante, a umidade
    estiver abaixo do limite, o sensor for confiável e a bateria estiver
    acima do piso de segurança. A água é cara em Marte e a bomba consome
    energia, então os quatro precisam valer ao mesmo tempo."""
    return agr_ativo and umidade_baixa and sensor_ok and reserva_ok


def tabela_verdade():
    """Monta a tabela verdade completa dos quatro sinais de entrada."""
    linhas = []
    for a in (0, 1):
        for u in (0, 1):
            for s in (0, 1):
                for r in (0, 1):
                    linhas.append((a, u, s, r, int(regra_irrigacao(a, u, s, r))))
    return linhas


def demonstrar_simplificacao():
    """Mostra a simplificação booleana da forma original para a forma mínima.

    A equipe de operação escreveu a regra pensando nos dois casos de falha de
    sensor, que é como o problema aparece na prática:

        IRRIGAR = (AGR AND UMID AND SENSOR AND RESERVA)
                  OR (AGR AND UMID AND SENSOR AND NOT RESERVA AND FALSO)

    O segundo termo nunca é verdadeiro, então some. Sobra o produto lógico
    mínimo. A segunda demonstração é a que importa de verdade, aplicando
    De Morgan sobre a condição de BLOQUEIO:

        BLOQUEAR = NOT IRRIGAR
                 = NOT (AGR AND UMID AND SENSOR AND RESERVA)
                 = NOT AGR OR NOT UMID OR NOT SENSOR OR NOT RESERVA

    Essa forma é a que o circuito usa para acender o LED vermelho, porque
    basta uma condição falhar para bloquear."""
    return [
        "Regra original, como a operação descreveu:",
        "  IRRIGAR = (AGR AND UMID AND SENSOR AND RESERVA)",
        "            OR (AGR AND UMID AND SENSOR AND NOT RESERVA AND FALSO)",
        "",
        "Passo 1, elemento absorvente: qualquer termo multiplicado por FALSO é FALSO.",
        "  IRRIGAR = (AGR AND UMID AND SENSOR AND RESERVA) OR FALSO",
        "",
        "Passo 2, elemento neutro da soma lógica: X OR FALSO = X.",
        "  IRRIGAR = AGR AND UMID AND SENSOR AND RESERVA     <- forma mínima",
        "",
        "Agora a condição de bloqueio, por De Morgan:",
        "  BLOQUEAR = NOT (AGR AND UMID AND SENSOR AND RESERVA)",
        "  BLOQUEAR = NOT AGR OR NOT UMID OR NOT SENSOR OR NOT RESERVA",
        "",
        "Leitura prática: irrigar exige as quatro condições juntas, mas basta",
        "uma falhar para bloquear. É por isso que o circuito usa uma porta AND",
        "de quatro entradas para a bomba e um NOT na saída para o LED de alerta.",
    ]


def verificar_equivalencia():
    """Confirma numericamente que as duas formas da regra são equivalentes."""
    divergencias = 0
    for a, u, s, r, saida_minima in tabela_verdade():
        forma_original = (a and u and s and r) or (a and u and s and (not r) and False)
        bloqueio_de_morgan = (not a) or (not u) or (not s) or (not r)
        if int(forma_original) != saida_minima or bloqueio_de_morgan == bool(saida_minima):
            divergencias += 1
    return divergencias


# =============================================================================
# BLOCO 4: CARGA DOS DADOS PARA ANÁLISE
# =============================================================================
def carregar_base():
    """Lê o CSV de análise, recriando-o se necessário."""
    if not os.path.exists(ARQUIVO_CSV):
        print("\n[AVISO] dados_aurora_siger.csv não encontrado. Gerando novamente.")
        return gerar_leituras(exibir=False)
    try:
        return pd.read_csv(ARQUIVO_CSV)
    except (pd.errors.EmptyDataError, pd.errors.ParserError) as erro:
        print(f"\n[ERRO] CSV ilegível ({erro}). Gerando novamente.")
        return gerar_leituras(exibir=False)


def cenario_corte(con):
    """Calcula o corte de carga necessário agora e quando a colônia voltar ao pleno.

    Hoje AGR e COM estão em manutenção, o que reduz o consumo e dá folga.
    A pergunta que importa para o planejamento é outra: quando os dois
    voltarem a operar, a colônia ainda atravessa uma tempestade severa?"""
    atual = consumo_total_ativo(con)
    pleno = float(con.execute("SELECT SUM(consumo_kw) FROM modulos").fetchone()[0] or 0.0)

    corte_atual, _, soc_atual = sim.corte_necessario(atual, 0.45)
    corte_pleno, _, soc_pleno = sim.corte_necessario(pleno, 0.45)

    cortaveis = con.execute(
        "SELECT codigo, nome, consumo_kw FROM modulos "
        "WHERE prioridade <= 2 ORDER BY consumo_kw DESC").fetchall()
    disponivel = sum(linha[2] for linha in cortaveis)

    return {"atual": atual, "pleno": pleno,
            "corte_atual": corte_atual, "soc_atual": soc_atual,
            "corte_pleno": corte_pleno, "soc_pleno": soc_pleno,
            "cortaveis": cortaveis, "disponivel": disponivel}


def consumo_total_ativo(con):
    """Soma o consumo cadastrado dos módulos em operação."""
    linha = con.execute(
        "SELECT SUM(consumo_kw) FROM modulos WHERE status != 'MANUTENCAO'").fetchone()
    return float(linha[0] or 0.0)


# =============================================================================
# BLOCO 5: OPÇÕES DO MENU
# =============================================================================
def cabecalho(titulo):
    print("\n" + "=" * 78)
    print(f" {titulo}")
    print("=" * 78)


def opcao_visao_geral(con):
    """Visão geral da colônia, direto do banco."""
    cabecalho("1. VISÃO GERAL DA COLÔNIA (BANCO DE DADOS)")

    modulos = con.execute(
        "SELECT codigo, nome, tipo, prioridade, consumo_kw, status, origem_cadastro "
        "FROM modulos ORDER BY prioridade DESC, consumo_kw DESC").fetchall()

    print(f"{'cód.':<6} | {'módulo':<26} | {'tipo':<16} | {'prior.':>6} | "
          f"{'kW':>6} | {'status':<10} | origem")
    print("-" * 102)
    for codigo, nome, tipo, prioridade, consumo, status, origem in modulos:
        print(f"{codigo:<6} | {nome:<26} | {rotulo(tipo):<16} | {prioridade:>6} | "
              f"{consumo:>6.1f} | {rotulo(status):<10} | {origem}")

    total = sum(m[4] for m in modulos)
    ativos = sum(m[4] for m in modulos if m[5] != "MANUTENCAO")
    print(f"\nConsumo cadastrado total ....... {total:7.1f} kW")
    print(f"Consumo dos módulos ativos ..... {ativos:7.1f} kW")

    print("\n--- Volume de dados no banco ---")
    for tabela in ["modulos", "conexoes", "sensores", "leituras", "alertas",
                   "manutencoes", "solicitacoes"]:
        qtd = con.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
        print(f"  {tabela:<14} {qtd:>5} registros")

    print("\n--- Herança das fases anteriores ---")
    print("  O cadastro de módulos vem da Fase 5 (NCAS), a rede física da")
    print("  Fase 4 (SIGIC) e os alertas abertos da Fase 6 (SCIC).")


def opcao_crud(con, roteiro=None):
    """CRUD completo sobre a tabela de alertas, com tratamento de erros."""
    cabecalho("2. CADASTRAR, CONSULTAR, ALTERAR E EXCLUIR (CRUD)")

    def mostrar():
        registros = crud_listar(con)
        print(f"\n{'id':>3} | {'módulo':<6} | {'tipo':<26} | {'crít.':>5} | "
              f"{'resolv.':>7} | mensagem")
        print("-" * 104)
        for _id, mod, tipo, critico, mensagem, _data, resolvido in registros:
            print(f"{_id:>3} | {mod:<6} | {tipo[:26]:<26} | {'sim' if critico else 'não':>5} | "
                  f"{'sim' if resolvido else 'não':>7} | {mensagem[:40]}")
        return registros

    print("Operações demonstradas sobre a tabela 'alertas'.")
    print("\n>>> READ: estado atual da tabela")
    mostrar()

    if roteiro is None:
        print("\n  [1] Cadastrar   [2] Alterar   [3] Excluir   [ENTER] voltar")
        escolha = entrada("  Opção: ")
        if escolha == "1":
            mod = entrada("  Código do módulo (ex.: OXI): ").upper()
            tipo = entrada("  Tipo do alerta: ") or "Ocorrência operacional"
            critico = entrada("  É crítico? (s/n): ").lower().startswith("s")
            msg = entrada("  Mensagem: ") or "Registrado pelo operador."
            _id, aviso = crud_cadastrar(con, mod, tipo, critico, msg)
            print(f"  {aviso}")
            if _id:
                mostrar()
        elif escolha == "2":
            try:
                _id = int(entrada("  id do alerta: "))
            except ValueError:
                print("  [ERRO] Informe um número inteiro.")
                return
            campo = entrada("  Campo (tipo/critico/mensagem/resolvido): ")
            valor = entrada("  Novo valor: ")
            ok, aviso = crud_alterar(con, _id, campo, valor)
            print(f"  {aviso}")
            if ok:
                mostrar()
        elif escolha == "3":
            try:
                _id = int(entrada("  id do alerta: "))
            except ValueError:
                print("  [ERRO] Informe um número inteiro.")
                return
            ok, aviso = crud_excluir(con, _id)
            print(f"  {aviso}")
            if ok:
                mostrar()
        return

    # --- modo demonstração: executa o ciclo completo sem digitação ---
    print("\n>>> CREATE: cadastrando um alerta novo")
    novo_id, aviso = crud_cadastrar(
        con, "OXI", "Consumo acima do previsto", True,
        "Compressor operando acima da faixa durante a tempestade.")
    print(f"  {aviso}")

    print("\n>>> UPDATE: marcando o alerta como resolvido")
    ok, aviso = crud_alterar(con, novo_id, "resolvido", 1)
    print(f"  {aviso}")

    print("\n>>> DELETE: removendo o alerta de teste")
    ok, aviso = crud_excluir(con, novo_id)
    print(f"  {aviso}")

    print("\n>>> TRATAMENTO DE ERROS: quatro tentativas inválidas de propósito")
    _id, aviso = crud_cadastrar(con, "XXX", "Teste", 0, "Módulo que não existe")
    print(f"  Módulo inexistente  -> {aviso}")
    _id, aviso = crud_cadastrar(con, "HAB", "Teste", 7, "Criticidade fora do domínio")
    print(f"  Criticidade 7       -> {aviso}")
    ok, aviso = crud_alterar(con, 1, "codigo_modulo", "LAB")
    print(f"  Campo protegido     -> {aviso}")
    ok, aviso = crud_excluir(con, 9999)
    print(f"  id inexistente      -> {aviso}")
    print("\n  Nenhuma dessas tentativas derrubou o programa: todas foram tratadas")
    print("  com try/except e devolveram mensagem explicando o problema.")

    print("\n>>> READ final")
    mostrar()


def opcao_regra_logica(con, interativo=True):
    """Regra booleana, simplificação, tabela verdade e circuito."""
    cabecalho("3. REGRA BOOLEANA, CIRCUITO LÓGICO E AUTOMAÇÃO")

    print("Regra de decisão do SIFSM para liberar a irrigação do cultivo:\n")
    print("  AGR     = módulo agrícola em operação")
    print("  UMID    = umidade do solo abaixo de 35%")
    print("  SENSOR  = leitura do sensor considerada confiável")
    print("  RESERVA = carga da bateria acima de 15%")

    print("\n--- Simplificação ---")
    for linha in demonstrar_simplificacao():
        print(f"  {linha}")

    print("\n--- Tabela verdade ---")
    print(f"  {'AGR':>4} {'UMID':>5} {'SENS':>5} {'RES':>4} | {'IRRIGAR':>8} | {'BLOQUEAR':>8}")
    print("  " + "-" * 46)
    for a, u, s, r, saida in tabela_verdade():
        print(f"  {a:>4} {u:>5} {s:>5} {r:>4} | {saida:>8} | {int(not saida):>8}")

    divergencias = verificar_equivalencia()
    print(f"\n  Verificação das 16 combinações: {divergencias} divergência(s).")
    print("  As duas formas da regra são equivalentes, como a álgebra previu.")

    print("\n--- Aplicação ao dado real do banco ---")
    leitura = con.execute("""
        SELECT l.ciclo, l.valor FROM leituras l
        JOIN sensores s ON s.codigo_sensor = l.codigo_sensor
        WHERE s.grandeza = 'umidade' ORDER BY l.ciclo DESC LIMIT 1
    """).fetchone()
    status_agr = con.execute("SELECT status FROM modulos WHERE codigo = 'AGR'").fetchone()[0]
    carga = con.execute("""
        SELECT l.valor FROM leituras l
        JOIN sensores s ON s.codigo_sensor = l.codigo_sensor
        WHERE s.grandeza = 'carga_bateria' ORDER BY l.ciclo DESC LIMIT 1
    """).fetchone()

    if leitura and carga:
        ciclo, umidade = leitura
        bateria = carga[0]
        agr_ativo = status_agr == "ATIVO"
        umidade_baixa = umidade < UMIDADE_LIMITE
        sensor_ok = True
        reserva_ok = bateria > CARGA_MINIMA_PCT
        decisao = regra_irrigacao(agr_ativo, umidade_baixa, sensor_ok, reserva_ok)

        print(f"  Ciclo {ciclo}: umidade {umidade:.1f}%, bateria {bateria:.1f}%, "
              f"AGR em {rotulo(status_agr)}")
        print(f"  AGR={int(agr_ativo)}  UMID={int(umidade_baixa)}  "
              f"SENSOR={int(sensor_ok)}  RESERVA={int(reserva_ok)}")
        print(f"  Decisão do sistema: {'IRRIGAR' if decisao else 'BLOQUEAR'}")
        if not decisao:
            faltou = []
            if not agr_ativo:
                faltou.append("módulo em manutenção")
            if not umidade_baixa:
                faltou.append("umidade acima do limite")
            if not reserva_ok:
                faltou.append("bateria abaixo do piso")
            print(f"  Motivo do bloqueio (De Morgan): {', '.join(faltou)}.")

    print("\n--- Circuito e automação embarcada ---")
    print("  O diagrama do circuito está em graficos_ou_imagens/circuito_logico.png,")
    print("  com a porta AND de quatro entradas, o inversor do LED de bloqueio e")
    print("  o esquema de ligações da placa.")
    print("  O sketch equivalente para Arduino está em arduino_irrigacao.ino: quatro")
    print("  entradas digitais com pull-down de 10k, um LED verde para irrigação")
    print("  liberada, um LED vermelho para bloqueio e um relé na bomba.")


def opcao_estruturas(con):
    """Demonstra as cinco estruturas de dados aplicadas ao sistema."""
    cabecalho("4. ESTRUTURAS DE DADOS APLICADAS AO SISTEMA")

    # ---- FILA ----
    print("--- FILA: atendimento das solicitações da tripulação ---")
    fila = FilaSolicitacoes()
    pedidos = con.execute(
        "SELECT id, solicitante, codigo_modulo, descricao, urgencia FROM solicitacoes "
        "WHERE atendida = 0 ORDER BY id").fetchall()
    for _id, quem, mod, desc, urgencia in pedidos:
        fila.enfileirar({"id": _id, "solicitante": quem, "modulo": mod,
                         "descricao": desc, "urgencia": urgencia})
    print(f"  {len(fila)} solicitações na fila "
          f"({len(fila.prioritaria)} prioritárias, {len(fila.normal)} normais).")
    print("  Ordem de atendimento:")
    posicao = 1
    while len(fila):
        pedido = fila.atender()
        faixa = "prioritária" if pedido["urgencia"] >= 4 else "normal"
        print(f"    {posicao}. [{faixa:<11}] {pedido['solicitante']:<11} "
              f"{pedido['modulo']:<6} urgência {pedido['urgencia']}: {pedido['descricao']}")
        posicao += 1
    print("  Por que fila: o pedido mais antigo da faixa é atendido primeiro, o que")
    print("  evita que uma solicitação fique parada enquanto chegam outras novas.")

    # ---- PILHA ----
    print("\n--- PILHA: histórico de manutenção com desfazer ---")
    pilha = PilhaHistorico()
    for mod, acao, resp, data in con.execute(
            "SELECT codigo_modulo, acao, responsavel, data FROM manutencoes ORDER BY id"):
        pilha.empilhar({"modulo": mod, "acao": acao, "responsavel": resp, "data": data})
    print(f"  {len(pilha)} ações registradas. Topo da pilha (a mais recente):")
    topo = pilha.topo()
    print(f"    {topo['data']} | {topo['modulo']} | {topo['acao']} | {topo['responsavel']}")
    print("  Desempilhando para desfazer as duas últimas:")
    for _ in range(2):
        acao = pilha.desempilhar()
        print(f"    desfeita: {acao['acao']} ({acao['modulo']}, {acao['data']})")
    print(f"  Restam {len(pilha)} ações na pilha.")
    print("  Por que pilha: desfazer sempre começa pela ação mais recente, que é")
    print("  exatamente a ordem LIFO.")

    # ---- TABELA HASH ----
    print("\n--- TABELA HASH: busca de sensor em tempo constante ---")
    indice = IndiceSensores()
    for cod, mod, grandeza, unidade in con.execute(
            "SELECT codigo_sensor, codigo_modulo, grandeza, unidade FROM sensores"):
        indice.inserir(cod, mod, grandeza, unidade)
    print(f"  {len(indice)} sensores indexados por código.")
    for alvo in ["0x2A10", "0x3C01", "0x9999"]:
        achado = indice.buscar(alvo)
        if achado:
            print(f"    {alvo} -> módulo {achado['modulo']}, mede {achado['grandeza']} "
                  f"em {achado['unidade']} (balde {indice.posicao_hash(alvo)})")
        else:
            print(f"    {alvo} -> não cadastrado")
    print("  Por que hash: a busca por código não percorre a lista, vai direto ao")
    print("  balde calculado pela função de espalhamento, em O(1) no caso médio.")

    # ---- ÁRVORE ----
    print("\n--- ÁRVORE: hierarquia de criticidade dos módulos ---")
    arvore = ArvorePrioridades()
    modulos = con.execute(
        "SELECT codigo, nome, prioridade, consumo_kw FROM modulos "
        "ORDER BY prioridade DESC, codigo").fetchall()
    arvore.montar(modulos)
    for linha in arvore.percorrer():
        print(f"  {linha}")
    cortaveis = arvore.folhas_cortaveis()
    print(f"\n  Folhas do galho menos crítico: {len(cortaveis)} módulos.")
    print("  Por que árvore: o corte de carga desce a hierarquia de baixo para cima,")
    print("  então a estrutura já devolve a ordem correta de desligamento.")

    # ---- GRAFO ----
    print("\n--- GRAFO: rede física da colônia e rota de energia ---")
    grafo = GrafoColonia()
    codigos = [m[0] for m in modulos]
    conexoes = con.execute("SELECT origem, destino, distancia FROM conexoes").fetchall()
    grafo.carregar(codigos, conexoes)
    print(f"  {len(codigos)} vértices e {len(conexoes)} arestas, vindos da Fase 4.")

    distancia, anterior = grafo.dijkstra("ENE")
    print("\n  Dijkstra a partir de ENE (armazenamento de energia):")
    print(f"    {'destino':<8} | {'distância':>10} | caminho")
    print("    " + "-" * 56)
    for destino in sorted(distancia, key=lambda d: distancia[d]):
        if destino == "ENE":
            continue
        if distancia[destino] == GrafoColonia.INFINITO:
            print(f"    {destino:<8} | {'sem rota':>10} |")
            continue
        rota = " -> ".join(grafo.caminho(anterior, destino))
        print(f"    {destino:<8} | {distancia[destino]:>8.0f} m | {rota}")
    print("\n  Por que grafo: energia e dados viajam por cabos reais, e a pergunta")
    print("  'qual o caminho mais curto até o módulo X' só tem resposta sobre a")
    print("  topologia da rede, não sobre uma lista.")


def opcao_simulacao(con):
    """Simulação do balanço energético e integração matemática."""
    cabecalho("5. SIMULAÇÃO COMPUTACIONAL E INTEGRAÇÃO MATEMÁTICA")
    consumo = consumo_total_ativo(con)
    print(f"Consumo dos módulos ativos, lido do banco: {consumo:.1f} kW")
    sim.simular_balanco_energetico(consumo)
    sim.comparar_cenarios(consumo)

    print("\n--- Convolução: filtrando o sensor de umidade ---")
    serie = [linha[0] for linha in con.execute("""
        SELECT l.valor FROM leituras l
        JOIN sensores s ON s.codigo_sensor = l.codigo_sensor
        WHERE s.grandeza = 'umidade' ORDER BY l.ciclo
    """).fetchall()]
    if serie:
        bruto = np.array(serie)
        filtrado = sim.filtrar_sensor(bruto, janela=5)
        print(f"  Série de {len(bruto)} ciclos do sensor 0x2A10 (módulo AGR).")
        print(f"  Desvio padrão bruto ...... {bruto.std():6.2f}")
        print(f"  Desvio padrão filtrado ... {filtrado.std():6.2f}")
        print(f"  Redução de ruído ......... {(1 - filtrado.std() / bruto.std()) * 100:5.1f}%")
        print("  O alerta da Fase 5 dizia que esse sensor tinha leitura instável.")
        print("  A convolução com núcleo de média móvel resolve por software, sem")
        print("  precisar trocar o equipamento.")


def opcao_modelo_linear(con, salvar_grafico=True):
    """Regressão linear múltipla para estimar o consumo de um módulo."""
    cabecalho("6. MODELAGEM LINEAR E TOMADA DE DECISÃO")

    base = carregar_base()
    if base is None or base.empty:
        print("[ERRO] Base de análise indisponível.")
        return None

    print(f"Base de análise: {len(base)} linhas ({base['codigo_modulo'].nunique()} módulos "
          f"x {base['ciclo'].nunique()} ciclos).")

    print("\n--- Análise exploratória ---")
    colunas = ["consumo_kw", "ocupacao_pct", "temperatura_externa_c", "fator_luz"]
    print(base[colunas].describe().round(2).to_string())

    print("\n--- Correlação com o consumo ---")
    correlacao = base[colunas].corr()["consumo_kw"].drop("consumo_kw").sort_values(
        key=abs, ascending=False)
    for nome, valor in correlacao.items():
        forca = "forte" if abs(valor) > 0.6 else "moderada" if abs(valor) > 0.3 else "fraca"
        print(f"  {nome:<24} {valor:+6.3f}  ({forca})")

    # --- regressão múltipla ---
    atributos = ["consumo_base_kw", "ocupacao_pct", "temperatura_externa_c", "fator_luz"]
    X = base[atributos]
    y = base["consumo_kw"]
    X_treino, X_teste, y_treino, y_teste = train_test_split(
        X, y, test_size=0.25, random_state=42)

    modelo = LinearRegression().fit(X_treino, y_treino)
    previsto = modelo.predict(X_teste)

    mae = mean_absolute_error(y_teste, previsto)
    rmse = math.sqrt(mean_squared_error(y_teste, previsto))
    r2 = r2_score(y_teste, previsto)

    print(f"\n--- Modelo: consumo_kw ~ {' + '.join(atributos)} ---")
    print(f"Divisão: {len(X_treino)} linhas de treino e {len(X_teste)} de teste.")
    print(f"\n  MAE  = {mae:6.3f} kW   (erro típico)")
    print(f"  RMSE = {rmse:6.3f} kW   (penaliza os piores casos)")
    print(f"  R2   = {r2:6.4f}      (variação explicada)")

    print("\n--- Interpretação dos coeficientes ---")
    print(f"  intercepto ............... {modelo.intercept_:+7.3f} kW")
    leituras = {
        "consumo_base_kw": "cada kW de consumo cadastrado soma {:.3f} kW ao total",
        "ocupacao_pct": "cada 1% de ocupação a mais soma {:.3f} kW",
        "temperatura_externa_c": "cada grau a MAIS lá fora economiza {:.3f} kW de aquecimento",
        "fator_luz": "céu totalmente limpo (fator 1) economiza {:.2f} kW frente ao escuro",
    }
    esperado = {"consumo_base_kw": 1.000, "ocupacao_pct": 0.080,
                "temperatura_externa_c": -0.120, "fator_luz": -6.000}
    print(f"  {'variável':<24} {'coef.':>8} {'esperado':>9}   leitura física")
    print("  " + "-" * 92)
    for nome, coef in zip(atributos, modelo.coef_):
        print(f"  {nome:<24} {coef:+8.3f} {esperado[nome]:+9.3f}   "
              f"{leituras[nome].format(abs(coef))}")

    print("\n  A coluna 'esperado' traz os pesos reais que o gerador usou. O modelo")
    print("  recuperou os quatro a partir dos dados, sem conhecer a fórmula, o que")
    print("  confirma que a regressão está capturando a física e não o acaso.")

    print("\n--- Fator que prejudicaria a interpretação ---")
    correl_oc_prio = base["ocupacao_pct"].corr(base["prioridade"])
    print(f"  A ocupação e a prioridade do módulo têm correlação de {correl_oc_prio:+.3f},")
    print("  porque módulos críticos são mais ocupados. Colocar as duas juntas no")
    print("  modelo gera colinearidade: os coeficientes se dividem entre elas e")
    print("  param de ter leitura física (numa versão anterior, a prioridade")
    print("  aparecia com sinal negativo, sugerindo o absurdo de que módulo mais")
    print("  crítico gasta menos). A prioridade ficou de fora porque já está")
    print("  embutida no consumo cadastrado, que é a variável com significado direto.")

    print("\n--- Decisão apoiada pelo modelo ---")
    cenario = pd.DataFrame([{
        "consumo_base_kw": 24.7, "ocupacao_pct": 80.0,
        "temperatura_externa_c": -78.0, "fator_luz": 0.45,
    }])
    estimado = float(modelo.predict(cenario)[0])
    print("  Cenário de tempestade severa no módulo OXI (24,7 kW de base):")
    print(f"    ocupação 80%, externa -78 C, fator de luz 0,45")
    print(f"    consumo estimado: {estimado:.2f} kW por módulo")
    print("  Esse número alimenta a decisão de corte de carga da simulação: é o")
    print("  consumo que a colônia precisa cobrir no pior cenário previsto.")

    if salvar_grafico:
        _grafico_regressao(base, y_teste, previsto, correlacao)

    return {"modelo": modelo, "mae": mae, "rmse": rmse, "r2": r2,
            "atributos": atributos, "coeficientes": dict(zip(atributos, modelo.coef_))}


def _grafico_regressao(base, y_teste, previsto, correlacao):
    """Gráfico de apoio da regressão."""
    os.makedirs(PASTA_GRAFICOS, exist_ok=True)
    fig, eixos = plt.subplots(1, 3, figsize=(16, 4.6))

    eixos[0].scatter(y_teste, previsto, alpha=0.6, color="#C1440E", edgecolor="white")
    limites = [min(y_teste.min(), previsto.min()), max(y_teste.max(), previsto.max())]
    eixos[0].plot(limites, limites, "--", color="#1F3864", linewidth=2)
    eixos[0].set_xlabel("Consumo real (kW)")
    eixos[0].set_ylabel("Consumo previsto (kW)")
    eixos[0].set_title("Real x previsto (teste)")

    eixos[1].barh(correlacao.index, correlacao.values, color="#1F3864")
    eixos[1].axvline(0, color="gray", linewidth=1)
    eixos[1].set_xlabel("Correlação com o consumo")
    eixos[1].set_title("Força de cada variável")

    por_tipo = base.groupby("tipo_modulo")["consumo_kw"].mean().sort_values()
    eixos[2].barh([rotulo(t) for t in por_tipo.index], por_tipo.values, color="#C1440E")
    eixos[2].set_xlabel("Consumo médio (kW)")
    eixos[2].set_title("Consumo por tipo de módulo")

    fig.suptitle("SIFSM: modelagem linear do consumo", fontsize=13)
    fig.tight_layout()
    fig.savefig(os.path.join(PASTA_GRAFICOS, "02_modelo_consumo.png"), dpi=130)
    plt.close(fig)
    print("\n  [gráfico salvo] graficos_ou_imagens/02_modelo_consumo.png")


def opcao_agentes(con, perguntas=None):
    """Camada de IA: triagem, handoff, ferramentas, RAG e guardrails."""
    cabecalho("7. INTEGRAÇÃO DE IA E SISTEMAS MULTIAGENTES")

    print("Arquitetura: guardrail de entrada, agente triador, handoff para o")
    print("especialista, ferramentas determinísticas sobre o banco, RAG nos")
    print("registros e guardrail de saída exigindo fonte.")
    print("\nNenhuma API externa é chamada. As respostas saem de consultas SQL,")
    print("o que torna cada número verificável no banco.")

    sessao = ia.SessaoAgentes(operador="CMDT_SILVA")

    if perguntas is None:
        print("\nDigite uma pergunta (ENTER vazio para voltar).")
        print("Exemplos: consumo da colônia, umidade do cultivo, manutenção da antena.")
        while True:
            pergunta = entrada("\n  Pergunta > ")
            if not pergunta:
                break
            resultado = ia.atender(con, pergunta, sessao)
            ia.exibir_atendimento(resultado)
    else:
        for pergunta in perguntas:
            print("\n" + "-" * 78)
            print(f"  Operador: {pergunta}")
            resultado = ia.atender(con, pergunta, sessao)
            ia.exibir_atendimento(resultado)

    print("\n" + "-" * 78)
    print(f"  {sessao.resumo()}")
    print("\n  Responsabilidade humana: o sistema sugere e justifica, mas as duas")
    print("  últimas perguntas mostram o guardrail barrando ação irreversível e")
    print("  assunto fora de escopo. Quem decide desligar um módulo é a equipe.")


def opcao_arquitetura(con):
    """Relação do protótipo com arquitetura e aceleração computacional."""
    cabecalho("8. ARQUITETURA COMPUTACIONAL E DESEMPENHO")

    total_leituras = con.execute("SELECT COUNT(*) FROM leituras").fetchone()[0]

    print("--- Onde cada parte do SIFSM roda melhor ---")
    print(f"  {'etapa do sistema':<34} | {'unidade':<8} | motivo")
    print("  " + "-" * 92)
    etapas = [
        ("Consultas SQL e CRUD", "CPU", "trabalho sequencial, dominado por acesso a disco"),
        ("Integração numérica da simulação", "CPU/GPU", "vetorizável: cada ponto é independente"),
        ("Regressão linear múltipla", "CPU", "matriz pequena, resolvida direto por álgebra"),
        ("Dijkstra sobre o grafo", "CPU", "percurso com dependência entre passos"),
        ("Filtro de convolução do sensor", "GPU/NPU", "mesma operação repetida sobre a série"),
        ("Inferência de um modelo de IA real", "NPU/TPU", "multiplicação de matrizes em lote"),
    ]
    for etapa, unidade, motivo in etapas:
        print(f"  {etapa:<34} | {unidade:<8} | {motivo}")

    print("\n--- Hierarquia de memória e movimentação de dados ---")
    print(f"  O banco tem {total_leituras} leituras, algumas centenas de kilobytes.")
    print("  A base inteira cabe na memória RAM e boa parte dela cabe no cache L2,")
    print("  então o gargalo do SIFSM hoje não é cálculo, é o acesso ao disco.")
    print("  É por isso que o sistema cria índices nas colunas codigo_sensor e")
    print("  ciclo: eles reduzem a quantidade de páginas lidas do disco por consulta.")
    print("\n  Quando a colônia crescer para milhões de leituras, o custo passa a ser")
    print("  o transporte de dados entre memória e processador, não a operação em si.")
    print("  Esse é o gargalo de von Neumann, e a resposta não é um processador mais")
    print("  rápido: é levar menos dado, com agregação no próprio banco e colunas")
    print("  numéricas compactas.")

    print("\n--- Largura de banda: o número que decide o gargalo ---")
    print("  Uma consulta que varre as 384 leituras move cerca de 30 KB. Um disco")
    print("  SSD entrega algo como 500 MB/s e a memória RAM passa de 20 GB/s, ou")
    print("  seja, quarenta vezes mais. Enquanto o dado cabe na RAM, a largura de")
    print("  banda sobra e o processador fica esperando o disco.")
    print("  Com milhões de registros a conta inverte: o processador consegue")
    print("  calcular mais rápido do que a memória consegue entregar o dado, e")
    print("  aí a largura de banda vira o teto do sistema, não a frequência da CPU.")

    print("\n--- Arquiteturas modernas: ASICs e chiplets ---")
    print("  Um ASIC é um circuito desenhado para uma função só. A regra de")
    print("  irrigação do SIFSM é o exemplo perfeito: uma porta AND de quatro")
    print("  entradas resolvida em hardware dedicado gastaria uma fração do que")
    print("  gasta um microcontrolador de uso geral rodando o mesmo if.")
    print("  O custo é a rigidez, porque mudar o limite de umidade de 35% para")
    print("  40% exigiria refazer o chip, enquanto no Arduino é uma linha.")
    print("\n  Chiplets são blocos menores montados num mesmo encapsulamento, em vez")
    print("  de um único chip grande. Para a colônia o atrativo é logístico: um")
    print("  bloco defeituoso pode ser trocado sem substituir o processador")
    print("  inteiro, o que importa quando a peça de reposição vem da Terra.")

    print("\n--- Processamento paralelo ---")
    print("  A simulação energética avalia a potência em 400 instantes do sol, e")
    print("  cada ponto é independente dos outros. Isso é paralelismo de dados:")
    print("  o NumPy já resolve de forma vetorizada e uma GPU dividiria entre")
    print("  milhares de núcleos. O Dijkstra é o oposto, porque cada passo depende")
    print("  do anterior, então nem o melhor hardware paralelo ajudaria.")
    print("  Saber distinguir os dois casos é o que evita comprar aceleração que")
    print("  não vai ser usada.")

    print("\n--- Computação heterogênea na prática da colônia ---")
    print("  Um sistema embarcado simples no módulo agrícola já resolve a regra de")
    print("  irrigação, porque a decisão é uma porta AND de quatro entradas.")
    print("  Mandar esse dado para um servidor central gastaria energia de rádio")
    print("  para decidir o que um microcontrolador de poucos miliwatts decide no")
    print("  local. Processar na borda é decisão de arquitetura e de energia ao")
    print("  mesmo tempo.")

    print("\n--- Desempenho, energia e sustentabilidade ---")
    print("  Toda operação computacional sai do mesmo orçamento solar que abastece")
    print("  o suporte de vida. Um modelo de IA grande rodando continuamente na")
    print("  colônia competiria por energia com a produção de oxigênio.")
    print("  Foi por isso que a camada de IA do SIFSM usa funções determinísticas:")
    print("  entrega resposta auditável com consumo praticamente nulo.")


def opcao_sustentabilidade(con):
    """Reflexão socioambiental e de cidadania digital."""
    cabecalho("9. SUSTENTABILIDADE, CIDADANIA DIGITAL E IMPACTO SOCIOAMBIENTAL")

    consumo = consumo_total_ativo(con)
    resultado = sim.simular_balanco_energetico(consumo, exibir=False, salvar_grafico=False)

    print("--- Integração entre energia, dados, automação e simulação ---")
    print(f"  A colônia gera {resultado['energia_trapezios']:.0f} kWh por sol em céu")
    print(f"  limpo e consome {resultado['energia_consumida']:.0f} kWh. A margem é de")
    print(f"  apenas {resultado['saldo_kwh']:+.0f} kWh, pouco mais de 6% do consumo.")
    print("  É essa margem estreita que obriga a integrar as camadas: o sensor mede,")
    print("  o banco guarda, a regra decide e a simulação antecipa. Sem integração,")
    print("  a colônia só descobriria o problema quando a bateria já estivesse baixa.")

    print("\n--- Simulação como prevenção de desperdício ---")
    cenario = cenario_corte(con)
    print(f"  Hoje a colônia consome {cenario['atual']:.1f} kW, porque AGR e COM estão")
    print(f"  em manutenção. Nessa condição ela atravessa uma tempestade severa com")
    print(f"  {cenario['soc_atual']:.1f}% de carga mínima, sem precisar cortar nada.")
    print(f"\n  Quando os dois voltarem ao pleno, o consumo sobe para {cenario['pleno']:.1f} kW")
    if cenario["corte_pleno"]:
        print(f"  e a mesma tempestade exige cortar {cenario['corte_pleno']:.0f} kW de carga.")
        print(f"  Os módulos de prioridade 2 somam {cenario['disponivel']:.1f} kW e cobrem o corte")
        print("  sem tocar no suporte de vida.")
    print("  Saber disso antes evita um desligamento de emergência. Simular é mais")
    print("  barato que errar: nenhuma energia foi gasta para descobrir isso.")

    print("\n--- Redes inteligentes, armazenamento e resiliência ---")
    print("  A autonomia da colônia depende de três camadas trabalhando juntas: a")
    print("  física, que são painéis, bateria e cabos; a de controle, que é a regra")
    print("  booleana decidindo no módulo agrícola; e a analítica, que é o banco")
    print("  com a simulação e o modelo.")
    print("  Resiliência aqui tem nome e número: COM e COM-R formam um par")
    print("  redundante, assim como DAT e BKP. Mas a antena externa EXT está a 675")
    print("  metros por um caminho único, então uma falha em COM-R a desconecta.")
    print("  O grafo mostra essa fragilidade antes que ela vire incidente, e é")
    print("  isso que uma rede inteligente faz: conhece a própria topologia.")

    print("\n--- Inovação responsável: benefício contra risco ---")
    print("  Nem toda tecnologia disponível deveria entrar na colônia. O SIFSM")
    print("  recusou duas de propósito, e o motivo é o mesmo nos dois casos.")
    print("  Um modelo de linguagem rodando local daria respostas mais naturais,")
    print("  mas consumiria energia do mesmo orçamento do suporte de vida e")
    print("  responderia sem fonte verificável. Ficaram as funções determinísticas.")
    print("  Automatizar o desligamento de módulos na tempestade seria mais rápido")
    print("  que esperar aprovação humana, e é tecnicamente trivial. Não foi feito")
    print("  porque um erro de sensor desligaria oxigênio sem ninguém no circuito.")
    print("  Inovação responsável é isso: avaliar o que a tecnologia custa e o que")
    print("  ela arrisca, não só o que ela entrega.")

    print("\n--- Cidadania digital, privacidade e transparência ---")
    print("  O banco guarda quem pediu o quê, na tabela solicitacoes, com nome do")
    print("  solicitante. Isso é dado pessoal da tripulação e exige cuidado.")
    print("  O SIFSM registra apenas o identificador funcional (CMDT_SILVA,")
    print("  ENG_ROCHA, MED_ALVES), nunca dado de saúde ou conteúdo privado, e as")
    print("  solicitações de suporte médico guardam só o módulo e a urgência, sem")
    print("  descrever a condição de quem pediu.")
    print("  Transparência: toda resposta da camada de IA cita o registro do banco")
    print("  que a fundamenta, e o rastro da decisão fica visível na tela.")

    print("\n--- Economia dos dados e seus riscos ---")
    print("  Os dados de consumo por módulo revelam rotina de vida: quando a")
    print("  tripulação dorme, quando o laboratório trabalha, quantas pessoas estão")
    print("  em cada setor. Numa colônia pequena, isso identifica indivíduos mesmo")
    print("  sem nome na tabela. Por isso a ocupação é guardada como percentual")
    print("  agregado por módulo, e não como registro de presença individual.")

    print("\n--- Impacto ambiental do processamento ---")
    print("  Data centers consomem água e energia. Em Marte os dois são recursos")
    print("  que não se repõem. A decisão de processar na borda, usar um banco")
    print("  local em arquivo e evitar modelo pesado não é economia de código:")
    print("  é economia de litro de água e de quilowatt-hora.")

    print("\n--- Diversidade, inclusão e responsabilidade ---")
    print("  A fila de atendimento ordena por urgência declarada e ordem de chegada,")
    print("  nunca por cargo ou senioridade de quem pediu. A árvore de prioridades")
    print("  classifica módulos por função vital, não por importância das pessoas")
    print("  que os ocupam. São escolhas de projeto que impedem o sistema de")
    print("  reproduzir hierarquia social na distribuição de recursos.")
    print("  E toda recomendação crítica passa por validação humana, porque a")
    print("  responsabilidade por uma decisão que afeta vidas não é delegável.")


def opcao_analise_final(con, resultado_modelo=None):
    """Consolida os resultados e gera o painel final."""
    cabecalho("10. ANÁLISE FINAL DOS RESULTADOS E LIMITAÇÕES")

    consumo = consumo_total_ativo(con)
    balanco = sim.simular_balanco_energetico(consumo, exibir=False, salvar_grafico=False)
    abertos = con.execute("SELECT COUNT(*) FROM alertas WHERE resolvido = 0").fetchone()[0]
    criticos = con.execute(
        "SELECT COUNT(*) FROM alertas WHERE resolvido = 0 AND critico = 1").fetchone()[0]
    leituras = con.execute("SELECT COUNT(*) FROM leituras").fetchone()[0]

    print("--- Situação da colônia ---")
    print(f"  Módulos cadastrados .............. {con.execute('SELECT COUNT(*) FROM modulos').fetchone()[0]}")
    print(f"  Leituras no banco ................ {leituras}")
    print(f"  Alertas em aberto ................ {abertos} ({criticos} crítico)")
    print(f"  Consumo dos módulos ativos ....... {consumo:.1f} kW")
    print(f"  Energia gerada por sol ........... {balanco['energia_trapezios']:.0f} kWh")
    print(f"  Saldo em céu limpo ............... {balanco['saldo_kwh']:+.0f} kWh")

    if resultado_modelo:
        print(f"  Modelo de consumo ................ R2 {resultado_modelo['r2']:.4f}, "
              f"MAE {resultado_modelo['mae']:.2f} kW")

    cenario = cenario_corte(con)
    print(f"  Corte exigido na tempestade, hoje ..... "
          f"{cenario['corte_atual']:.0f} kW (carga mínima {cenario['soc_atual']:.1f}%)")
    if cenario["corte_pleno"] is not None:
        print(f"  Corte exigido no pleno ({cenario['pleno']:.1f} kW) .... "
              f"{cenario['corte_pleno']:.0f} kW")

    print("\n--- Recomendações do SIFSM ---")
    nomes = ", ".join(f"{c} ({kw:.1f} kW)" for c, _n, kw in cenario["cortaveis"])
    if cenario["corte_pleno"]:
        print(f"  1. Planejar corte de {cenario['corte_pleno']:.0f} kW para quando AGR e COM")
        print(f"     voltarem ao pleno. Candidatos de prioridade 2: {nomes},")
        print(f"     somando {cenario['disponivel']:.1f} kW disponíveis.")
    else:
        print("  1. Manter o plano de corte de carga pronto, mesmo sem necessidade")
        print(f"     imediata. Candidatos de prioridade 2: {nomes}.")
    print("  2. Concluir a manutenção da antena COM, pendente desde a Fase 5, e")
    print("     manter o tráfego crítico no enlace redundante até lá.")
    print("  3. Aplicar o filtro de convolução ao sensor de umidade do AGR em vez")
    print("     de substituir o equipamento, o que economiza peça e transporte.")
    print("  4. Toda decisão acima é sugestão: a validação é da equipe da colônia.")

    print("\n--- Limitações reconhecidas ---")
    print("  1. Os dados são simulados por um processo conhecido, o que favorece o")
    print("     modelo linear. Com telemetria real o R2 seria menor.")
    print("  2. A simulação trata o consumo como constante ao longo do sol e ignora")
    print("     perdas de conversão e temperatura do painel.")
    print("  3. A camada de IA usa funções determinísticas, não um modelo de")
    print("     linguagem: ela demonstra a arquitetura, não a capacidade de")
    print("     interpretar linguagem livre.")
    print("  4. O banco é SQLite em arquivo único, adequado ao protótipo mas sem")
    print("     concorrência de escrita, que um Oracle ou Postgres resolveria.")
    print("  5. O circuito lógico é representado e simulado, sem hardware real.")

    _painel_final(con)


def _painel_final(con):
    """Gera o painel de gráficos da análise final."""
    os.makedirs(PASTA_GRAFICOS, exist_ok=True)
    base = carregar_base()
    if base is None or base.empty:
        return

    fig, eixos = plt.subplots(1, 3, figsize=(16, 4.6))

    por_ciclo = base.groupby("ciclo").agg(
        consumo=("consumo_kw", "sum"), geracao=("geracao_solar_kw", "first"))
    eixos[0].plot(por_ciclo.index, por_ciclo["consumo"], marker="o",
                  color="#C1440E", label="Consumo total")
    eixos[0].plot(por_ciclo.index, por_ciclo["geracao"], marker="s",
                  color="#1F3864", label="Geração média")
    eixos[0].axvspan(10, 14, alpha=0.15, color="orange", label="Tempestade")
    eixos[0].set_xlabel("Ciclo")
    eixos[0].set_ylabel("Potência (kW)")
    eixos[0].set_title("Consumo x geração por ciclo")
    eixos[0].legend(fontsize=8)

    alertas = con.execute(
        "SELECT codigo_modulo, COUNT(*) FROM alertas GROUP BY codigo_modulo").fetchall()
    if alertas:
        eixos[1].bar([a[0] for a in alertas], [a[1] for a in alertas], color="#C1440E")
    eixos[1].set_xlabel("Módulo")
    eixos[1].set_ylabel("Alertas")
    eixos[1].set_title("Alertas por módulo")

    latencias = pd.DataFrame(con.execute("""
        SELECT l.ciclo, s.codigo_modulo, l.valor FROM leituras l
        JOIN sensores s ON s.codigo_sensor = l.codigo_sensor
        WHERE s.grandeza = 'latencia'
    """).fetchall(), columns=["ciclo", "modulo", "valor"])
    if not latencias.empty:
        for mod, cor in [("COM", "#C1440E"), ("COM-R", "#1F3864"), ("EXT", "#2E7D32")]:
            serie = latencias[latencias["modulo"] == mod].sort_values("ciclo")
            if not serie.empty:
                eixos[2].plot(serie["ciclo"], serie["valor"], marker=".", label=mod, color=cor)
    eixos[2].set_xlabel("Ciclo")
    eixos[2].set_ylabel("Latência (ms)")
    eixos[2].set_title("Herança da Fase 6: a antena COM")
    eixos[2].legend(fontsize=8)

    fig.suptitle("SIFSM: painel final da Aurora Siger", fontsize=13)
    fig.tight_layout()
    fig.savefig(os.path.join(PASTA_GRAFICOS, "03_painel_final.png"), dpi=130)
    plt.close(fig)
    print("\n  [gráfico salvo] graficos_ou_imagens/03_painel_final.png")


# =============================================================================
# INTERFACE DE TERMINAL
# =============================================================================
def entrada(mensagem, padrao=""):
    """Leitura segura do teclado, resistente a fim de entrada."""
    try:
        return input(mensagem).strip()
    except (EOFError, KeyboardInterrupt):
        print("\n[entrada encerrada]")
        return padrao


def limpar_terminal():
    """Limpa a tela ao voltar para o menu, só quando há terminal de verdade."""
    if not sys.stdout.isatty():
        return
    os.system("cls" if os.name == "nt" else "clear")


def banner():
    print("\n" + "=" * 78)
    print(" SIFSM: SISTEMA INTEGRADO DE FUTURO SUSTENTÁVEL EM MARTE".center(78))
    print(" Aurora Siger, Base Harmonia-7 | FIAP, Fase 7".center(78))
    print("=" * 78)


def menu_principal():
    print("\n" + "-" * 78)
    print(" MENU PRINCIPAL")
    print("-" * 78)
    print("  1 - Visão geral da colônia (banco de dados)")
    print("  2 - Cadastrar, consultar, alterar e excluir (CRUD)")
    print("  3 - Regra booleana, circuito lógico e automação")
    print("  4 - Estruturas de dados (fila, pilha, hash, árvore e grafo)")
    print("  5 - Simulação energética e integração matemática")
    print("  6 - Modelagem linear e tomada de decisão")
    print("  7 - Agentes de IA, ferramentas e guardrails")
    print("  8 - Arquitetura computacional e desempenho")
    print("  9 - Sustentabilidade e cidadania digital")
    print(" 10 - Análise final e gráficos")
    print(" 11 - Recriar o banco e os dados simulados")
    print("  0 - Sair")
    print("-" * 78)


def executar_demonstracao():
    """Modo --demo: roda tudo em sequência, sem digitação."""
    banner()
    print("\n>>> MODO DEMONSTRAÇÃO: executando todas as funcionalidades do SIFSM.")

    criar_banco()
    con = conectar()
    try:
        opcao_visao_geral(con)
        opcao_crud(con, roteiro=True)
        opcao_regra_logica(con, interativo=False)
        opcao_estruturas(con)
        opcao_simulacao(con)
        resultado = opcao_modelo_linear(con)
        opcao_agentes(con, perguntas=ia.PERGUNTAS_DEMO)
        opcao_arquitetura(con)
        opcao_sustentabilidade(con)
        opcao_analise_final(con, resultado)
    finally:
        con.close()

    cabecalho("DEMONSTRAÇÃO CONCLUÍDA")
    print("Todas as funcionalidades do SIFSM foram executadas com sucesso.")
    print("Gráficos disponíveis na pasta graficos_ou_imagens/.\n")


def main():
    """Laço principal do menu interativo."""
    if "--demo" in sys.argv:
        executar_demonstracao()
        return

    limpar_terminal()
    banner()
    criar_banco()

    con = conectar()
    resultado_modelo = None
    try:
        total = con.execute("SELECT COUNT(*) FROM modulos").fetchone()[0]
        print(f"\n[OK] Banco conectado: {total} módulos cadastrados.")

        while True:
            menu_principal()
            opcao = entrada("Escolha uma opção: ", padrao="0")

            if opcao == "1":
                opcao_visao_geral(con)
            elif opcao == "2":
                opcao_crud(con)
            elif opcao == "3":
                opcao_regra_logica(con)
            elif opcao == "4":
                opcao_estruturas(con)
            elif opcao == "5":
                opcao_simulacao(con)
            elif opcao == "6":
                resultado_modelo = opcao_modelo_linear(con)
            elif opcao == "7":
                opcao_agentes(con)
            elif opcao == "8":
                opcao_arquitetura(con)
            elif opcao == "9":
                opcao_sustentabilidade(con)
            elif opcao == "10":
                opcao_analise_final(con, resultado_modelo)
            elif opcao == "11":
                cabecalho("11. RECRIAR O BANCO E OS DADOS SIMULADOS")
                print("O banco é recriado a partir de script_banco.sql e as leituras")
                print("são geradas com semente fixa (42), então o resultado é sempre")
                print("o mesmo. Útil para voltar ao estado inicial depois do CRUD.")
                con.close()
                criar_banco(forcar=True)
                con = conectar()
                print("\n[OK] Banco recriado e reconectado.")
            elif opcao == "0":
                print("\nEncerrando o SIFSM. Boa missão, Aurora Siger.\n")
                break
            else:
                print("\n[AVISO] Opção inválida. Escolha um número do menu.")

            entrada("\nPressione ENTER para voltar ao menu...")
            limpar_terminal()
            banner()
    finally:
        con.close()


if __name__ == "__main__":
    main()
