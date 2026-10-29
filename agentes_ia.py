"""
===============================================================================
 SIFSM: Sistema Integrado de Futuro Sustentável em Marte
 Aurora Siger | Base Harmonia-7 | FIAP, Ciência da Computação, Fase 7
 Grupo: Gabriel, Lucas, Matheus, Miguel e Pedro
-------------------------------------------------------------------------------
 agentes_ia.py

 Camada de IA do SIFSM, implementada como um sistema MULTIAGENTES simulado.

 Nada aqui chama API externa nem usa modelo de linguagem: as respostas são
 construídas por funções determinísticas que consultam o banco de dados real
 da colônia. A escolha é deliberada e está explicada no relatório. O que
 interessa demonstrar é a ARQUITETURA, que é a mesma de um sistema com modelo
 de verdade no lugar das funções de resposta:

     solicitação
         |
     [GUARDRAIL DE ENTRADA]  bloqueia pedido fora de escopo ou inseguro
         |
     [AGENTE TRIADOR]        classifica o assunto e escolhe o especialista
         |
     [HANDOFF]               repassa com o contexto da sessão
         |
     [AGENTE ESPECIALISTA]   energia, ambiental, manutenção ou dados
         |                   usa FERRAMENTAS determinísticas sobre o banco
     [RAG]                   busca os registros que fundamentam a resposta
         |
     [GUARDRAIL DE SAÍDA]    exige fonte e barra ação autônoma crítica
         |
     resposta + rastro da decisão (tracing)

 A sessão guarda o histórico das interações, para que o agente mantenha
 contexto entre perguntas.
===============================================================================
"""

import re
import sqlite3
from datetime import datetime


# =============================================================================
# 1. GUARDRAILS
# =============================================================================
# Verbos de ação física irreversível. O SIFSM é um sistema de apoio: ele
# recomenda, mas nunca executa esse tipo de ação.
ACOES_BLOQUEADAS = [
    "desligar", "desligue", "corte", "cortar", "abrir a eclusa", "despressurizar",
    "evacuar", "desativar",
]

# Ações destrutivas sobre os próprios dados: bloqueadas sempre, mesmo em
# forma de pergunta, porque não existe motivo legítimo para pedi-las ao agente.
ACOES_SEMPRE_BLOQUEADAS = [
    "apagar o banco", "deletar tudo", "drop table", "truncate", "delete from",
]

# Marcas de que a frase é uma CONSULTA e não uma ORDEM. Perguntar "o que
# podemos desligar" é pedir recomendação, que é justamente o papel do
# sistema; "desligue o módulo" é mandar executar, o que ele nunca faz.
MARCAS_DE_PERGUNTA = [
    "?", "qual", "quais", "quanto", "quantos", "como", "o que", "por que",
    "onde", "quem", "devo", "devemos", "podemos", "posso", "poderia",
    "vale a pena", "é possível", "e possível", "seria",
]

# Assuntos que não pertencem ao escopo do sistema.
FORA_DE_ESCOPO = [
    "previsão do tempo na terra", "cotação", "bolsa", "futebol", "receita de",
    "piada", "música",
]


def guardrail_entrada(pergunta):
    """Verifica a solicitação ANTES de qualquer processamento.

    Devolve (liberado, motivo). Três checagens:
      1. pedido vazio ou curto demais para ser interpretado;
      2. pedido de ação física irreversível, que exige decisão humana;
      3. assunto fora do escopo da operação da colônia."""
    texto = pergunta.lower().strip()

    if len(texto) < 8:
        return False, "Pedido curto demais para ser interpretado com segurança."

    for termo in ACOES_SEMPRE_BLOQUEADAS:
        if termo in texto:
            return False, (f"Operação destrutiva sobre os dados ('{termo}'). "
                           "O agente não altera nem apaga o banco em nenhuma "
                           "hipótese: isso só acontece pelo menu de CRUD, com "
                           "operador identificado.")

    eh_pergunta = any(marca in texto for marca in MARCAS_DE_PERGUNTA)
    for termo in ACOES_BLOQUEADAS:
        if termo in texto and not eh_pergunta:
            return False, (f"O pedido é uma ordem de ação irreversível ('{termo}'). "
                           "O SIFSM recomenda, mas não executa: encaminhe ao "
                           "comando da colônia para validação humana.")

    for termo in FORA_DE_ESCOPO:
        if termo in texto:
            return False, (f"Assunto fora do escopo operacional ('{termo}'). "
                           "O sistema responde sobre energia, ambiente, "
                           "manutenção e dados da Aurora Siger.")

    acao_citada = next((t for t in ACOES_BLOQUEADAS if t in texto), None)
    if acao_citada:
        return True, (f"O pedido cita uma ação ('{acao_citada}'), mas na forma de "
                      "consulta: liberado como recomendação, não como execução.")
    return True, "Pedido dentro do escopo e sem ação irreversível."


def guardrail_saida(resposta, fontes):
    """Verifica a resposta ANTES de entregar ao operador.

    Regra principal: toda resposta precisa citar pelo menos um registro do
    banco. Resposta sem fonte é alucinação em potencial e não sai."""
    if not fontes:
        return False, ("Resposta sem fonte no banco de dados. Bloqueada para "
                       "evitar informação não verificável.")
    if len(resposta.strip()) < 15:
        return False, "Resposta vazia ou curta demais para ser útil."
    return True, f"Resposta fundamentada em {len(fontes)} registro(s) do banco."


# =============================================================================
# 2. FERRAMENTAS DETERMINÍSTICAS (as "tools" dos agentes)
# =============================================================================
# Cada ferramenta é uma função simples que consulta o banco e devolve dados
# verificáveis. O agente não inventa número: ele chama a ferramenta.

def ferramenta_consumo_por_modulo(con, codigo=None):
    """Consulta o consumo cadastrado dos módulos."""
    if codigo:
        sql = "SELECT codigo, nome, consumo_kw, prioridade, status FROM modulos WHERE codigo = ?"
        return con.execute(sql, (codigo,)).fetchall()
    sql = "SELECT codigo, nome, consumo_kw, prioridade, status FROM modulos ORDER BY consumo_kw DESC"
    return con.execute(sql).fetchall()


def ferramenta_alertas_abertos(con, apenas_criticos=False):
    """Lista os alertas ainda não resolvidos."""
    sql = ("SELECT id, codigo_modulo, tipo, critico, mensagem, data "
           "FROM alertas WHERE resolvido = 0")
    if apenas_criticos:
        sql += " AND critico = 1"
    sql += " ORDER BY critico DESC, data"
    return con.execute(sql).fetchall()


def ferramenta_ultima_leitura(con, grandeza):
    """Busca a leitura mais recente de uma grandeza, por módulo."""
    sql = """
        SELECT s.codigo_modulo, s.grandeza, s.unidade, l.valor, l.ciclo
        FROM leituras l
        JOIN sensores s ON s.codigo_sensor = l.codigo_sensor
        WHERE s.grandeza = ?
          AND l.ciclo = (SELECT MAX(ciclo) FROM leituras)
        ORDER BY l.valor DESC
    """
    return con.execute(sql, (grandeza,)).fetchall()


def ferramenta_historico_manutencao(con, codigo=None):
    """Consulta o histórico de manutenção, do mais recente para o mais antigo."""
    if codigo:
        sql = ("SELECT codigo_modulo, acao, responsavel, data FROM manutencoes "
               "WHERE codigo_modulo = ? ORDER BY id DESC")
        return con.execute(sql, (codigo,)).fetchall()
    sql = "SELECT codigo_modulo, acao, responsavel, data FROM manutencoes ORDER BY id DESC"
    return con.execute(sql).fetchall()


FERRAMENTAS = {
    "consumo_por_modulo": ferramenta_consumo_por_modulo,
    "alertas_abertos": ferramenta_alertas_abertos,
    "ultima_leitura": ferramenta_ultima_leitura,
    "historico_manutencao": ferramenta_historico_manutencao,
}


# =============================================================================
# 3. RAG SIMULADO: recupera do banco os trechos que fundamentam a resposta
# =============================================================================
def recuperar_contexto(con, pergunta, limite=4):
    """Busca por palavra-chave nas tabelas de texto do banco.

    É um RAG simplificado: no lugar de embeddings, usa correspondência de
    termos sobre mensagens de alerta, ações de manutenção e descrições de
    solicitação. O princípio é o mesmo, ou seja, a resposta é montada a
    partir de documentos recuperados da base, e não da memória do modelo."""
    termos = [t for t in re.findall(r"[a-zà-ú0-9\-]{4,}", pergunta.lower())]
    if not termos:
        return []

    achados = []
    consultas = [
        ("alertas", "SELECT 'alerta #' || id, codigo_modulo, mensagem, data FROM alertas WHERE LOWER(mensagem) LIKE ?"),
        ("manutenções", "SELECT 'manutenção #' || id, codigo_modulo, acao, data FROM manutencoes WHERE LOWER(acao) LIKE ?"),
        ("solicitações", "SELECT 'solicitação #' || id, codigo_modulo, descricao, data FROM solicitacoes WHERE LOWER(descricao) LIKE ?"),
    ]
    for termo in termos:
        for origem, sql in consultas:
            for linha in con.execute(sql, (f"%{termo}%",)).fetchall():
                registro = (origem, linha[0], linha[1], linha[2], linha[3])
                if registro not in achados:
                    achados.append(registro)
            if len(achados) >= limite:
                return achados[:limite]
    return achados[:limite]


# =============================================================================
# 4. AGENTE TRIADOR
# =============================================================================
PALAVRAS_POR_AGENTE = {
    "energia": ["energia", "consumo", "bateria", "carga", "solar", "kw", "painel",
                "gerador", "eletric", "potencia", "potência"],
    "ambiental": ["umidade", "temperatura", "luminosidade", "poeira", "tempestade",
                  "ambiente", "clima", "irrigação", "irrigacao", "cultivo", "água", "agua"],
    "manutencao": ["manutenção", "manutencao", "falha", "reparo", "antena", "defeito",
                   "degradação", "degradacao", "quebr", "técnico", "tecnico", "conserto"],
    "dados": ["dado", "banco", "registro", "backup", "armazenamento", "histórico",
              "historico", "consulta", "tabela", "latência", "latencia", "rede"],
}


def agente_triador(pergunta):
    """Classifica a solicitação e escolhe o especialista.

    Conta quantas palavras-chave de cada domínio aparecem no pedido e
    devolve o agente com mais ocorrências, junto da pontuação de cada um,
    que é o que torna a decisão auditável."""
    texto = pergunta.lower()
    pontos = {nome: 0 for nome in PALAVRAS_POR_AGENTE}
    for nome, palavras in PALAVRAS_POR_AGENTE.items():
        for palavra in palavras:
            if palavra in texto:
                pontos[nome] += 1

    melhor = max(pontos, key=pontos.get)
    if pontos[melhor] == 0:
        return "dados", pontos, "Nenhum domínio reconhecido: encaminhado ao agente de dados."
    return melhor, pontos, f"Domínio '{melhor}' com {pontos[melhor]} termo(s) reconhecido(s)."


# =============================================================================
# 5. AGENTES ESPECIALISTAS
# =============================================================================
def agente_energia(con, pergunta):
    """Responde sobre consumo, geração e reserva da colônia."""
    modulos = ferramenta_consumo_por_modulo(con)
    total = sum(linha[2] for linha in modulos if linha[4] == "ATIVO")
    maiores = modulos[:3]

    linhas = [
        f"Consumo somado dos módulos ativos: {total:.1f} kW.",
        "Maiores consumidores: " + ", ".join(
            f"{c} ({n}) com {kw:.1f} kW" for c, n, kw, _, _ in maiores) + ".",
    ]
    # só faz sentido sugerir desligar o que ainda está ligado
    baixa_prioridade = [l for l in modulos if l[3] <= 2 and l[4] == "ATIVO"]
    if baixa_prioridade:
        economia = sum(l[2] for l in baixa_prioridade)
        linhas.append(
            f"Corte possível sem afetar suporte de vida: {economia:.1f} kW, "
            + "desligando " + " e ".join(l[0] for l in baixa_prioridade)
            + " (prioridade cadastral 2).")
    fontes = [("modulos", f"{len(modulos)} registros da tabela modulos")]
    return " ".join(linhas), fontes, ["consumo_por_modulo"]


def agente_ambiental(con, pergunta):
    """Responde sobre umidade, temperatura, luminosidade e poeira."""
    umidade = ferramenta_ultima_leitura(con, "umidade")
    temperatura = ferramenta_ultima_leitura(con, "temperatura")
    fontes, ferramentas = [], ["ultima_leitura"]

    linhas = []
    if umidade:
        mod, _, unidade, valor, ciclo = umidade[0]
        linhas.append(f"Umidade do módulo {mod} no ciclo {ciclo}: {valor:.1f}{unidade}.")
        if valor < 35:
            linhas.append("Abaixo do limite de 35%: a regra de irrigação do SIFSM "
                          "é atendida e o sistema recomenda irrigar.")
        else:
            linhas.append("Acima do limite de 35%: irrigação não recomendada neste ciclo.")
        fontes.append(("leituras", f"sensor de umidade do módulo {mod}, ciclo {ciclo}"))
    if temperatura:
        mod, _, unidade, valor, ciclo = temperatura[0]
        linhas.append(f"Temperatura interna de {mod}: {valor:.1f}{unidade}.")
        fontes.append(("leituras", f"sensor de temperatura do módulo {mod}, ciclo {ciclo}"))

    if not linhas:
        linhas.append("Não há leituras ambientais registradas no banco.")
    return " ".join(linhas), fontes, ferramentas


def agente_manutencao(con, pergunta):
    """Responde sobre falhas, reparos e pendências técnicas."""
    abertos = ferramenta_alertas_abertos(con)
    historico = ferramenta_historico_manutencao(con)

    linhas = [f"Alertas em aberto: {len(abertos)}."]
    for _id, mod, tipo, critico, mensagem, data in abertos[:3]:
        marca = "CRÍTICO" if critico else "atenção"
        linhas.append(f"[{marca}] {mod}, {tipo}, desde {data}: {mensagem}")
    if historico:
        mod, acao, resp, data = historico[0]
        linhas.append(f"Última manutenção registrada: {acao} em {mod}, "
                      f"por {resp}, em {data}.")

    fontes = [("alertas", f"{len(abertos)} alertas não resolvidos"),
              ("manutencoes", f"{len(historico)} registros de histórico")]
    return " ".join(linhas), fontes, ["alertas_abertos", "historico_manutencao"]


def agente_dados(con, pergunta):
    """Responde sobre registros, rede e armazenamento."""
    latencias = ferramenta_ultima_leitura(con, "latencia")
    total_leituras = con.execute("SELECT COUNT(*) FROM leituras").fetchone()[0]

    linhas = [f"O banco tem {total_leituras} leituras registradas."]
    if latencias:
        pior = latencias[0]
        linhas.append(f"Maior latência no último ciclo: módulo {pior[0]} com "
                      f"{pior[3]:.1f} {pior[2]}, no ciclo {pior[4]}.")
        if len(latencias) > 1:
            melhor = latencias[-1]
            linhas.append(f"Menor latência: módulo {melhor[0]} com {melhor[3]:.1f} {melhor[2]}.")
    fontes = [("leituras", f"{total_leituras} registros")]
    return " ".join(linhas), fontes, ["ultima_leitura"]


ESPECIALISTAS = {
    "energia": ("Agente de Energia", agente_energia),
    "ambiental": ("Agente Ambiental", agente_ambiental),
    "manutencao": ("Agente de Manutenção", agente_manutencao),
    "dados": ("Agente de Dados", agente_dados),
}


# =============================================================================
# 6. SESSÃO: mantém o contexto entre perguntas
# =============================================================================
class SessaoAgentes:
    """Guarda o histórico da conversa e o rastro das decisões (tracing).

    Cada atendimento registra qual agente respondeu, quais ferramentas foram
    chamadas e quais registros do banco fundamentaram a resposta. É esse
    rastro que permite auditoria depois."""

    def __init__(self, operador="CMDT_SILVA"):
        self.operador = operador
        self.historico = []
        self.aberta_em = datetime.now().strftime("%Y-%m-%d %H:%M")

    def registrar(self, pergunta, agente, resposta, ferramentas, fontes, trace):
        self.historico.append({
            "n": len(self.historico) + 1,
            "pergunta": pergunta,
            "agente": agente,
            "resposta": resposta,
            "ferramentas": ferramentas,
            "fontes": fontes,
            "trace": trace,
        })

    def resumo(self):
        if not self.historico:
            return "Sessão sem interações registradas."
        agentes = {}
        for item in self.historico:
            agentes[item["agente"]] = agentes.get(item["agente"], 0) + 1
        partes = ", ".join(f"{nome}: {qtd}" for nome, qtd in agentes.items())
        return (f"Sessão de {self.operador}, aberta em {self.aberta_em}, com "
                f"{len(self.historico)} atendimento(s). Distribuição: {partes}.")


# =============================================================================
# 7. ORQUESTRAÇÃO
# =============================================================================
def atender(con, pergunta, sessao):
    """Executa o fluxo completo de atendimento e devolve o rastro da decisão."""
    trace = []

    liberado, motivo = guardrail_entrada(pergunta)
    trace.append(("guardrail_entrada", "liberado" if liberado else "BLOQUEADO", motivo))
    if not liberado:
        return {"bloqueado": True, "resposta": motivo, "trace": trace,
                "agente": "guardrail", "ferramentas": [], "fontes": []}

    destino, pontos, justificativa = agente_triador(pergunta)
    trace.append(("agente_triador", destino, justificativa))

    nome_agente, funcao = ESPECIALISTAS[destino]
    trace.append(("handoff", nome_agente, f"Contexto da sessão repassado ao {nome_agente}."))

    resposta, fontes, ferramentas = funcao(con, pergunta)
    trace.append(("ferramentas", ", ".join(ferramentas),
                  f"{len(ferramentas)} função determinística executada sobre o banco."))

    contexto = recuperar_contexto(con, pergunta)
    if contexto:
        trace.append(("rag", f"{len(contexto)} trecho(s)",
                      "Registros recuperados do banco para fundamentar a resposta."))
        fontes.extend([(origem, f"{ident} ({mod}): {texto[:60]}")
                       for origem, ident, mod, texto, _ in contexto])

    ok, motivo_saida = guardrail_saida(resposta, fontes)
    trace.append(("guardrail_saida", "liberado" if ok else "BLOQUEADO", motivo_saida))
    if not ok:
        return {"bloqueado": True, "resposta": motivo_saida, "trace": trace,
                "agente": nome_agente, "ferramentas": ferramentas, "fontes": fontes}

    sessao.registrar(pergunta, nome_agente, resposta, ferramentas, fontes, trace)
    return {"bloqueado": False, "resposta": resposta, "trace": trace,
            "agente": nome_agente, "ferramentas": ferramentas, "fontes": fontes,
            "pontos_triagem": pontos}


def exibir_atendimento(resultado):
    """Imprime a resposta junto do rastro completo da decisão."""
    print("\n  Rastro da decisão (tracing):")
    for etapa, saida, detalhe in resultado["trace"]:
        print(f"    {etapa:<18} -> {saida}")
        print(f"      {detalhe}")

    print(f"\n  Agente responsável: {resultado['agente']}")
    if resultado["bloqueado"]:
        print(f"\n  [BLOQUEADO PELO GUARDRAIL]")
        print(f"  {resultado['resposta']}")
        return

    print(f"\n  Resposta:")
    for linha in _quebrar(resultado["resposta"], 72):
        print(f"    {linha}")

    if resultado["fontes"]:
        print("\n  Fontes no banco de dados:")
        for tabela, detalhe in resultado["fontes"][:5]:
            print(f"    - {tabela}: {detalhe}")


def _quebrar(texto, largura):
    """Quebra o texto em linhas para caber no terminal."""
    palavras, linha, linhas = texto.split(), "", []
    for palavra in palavras:
        if len(linha) + len(palavra) + 1 > largura:
            linhas.append(linha)
            linha = palavra
        else:
            linha = f"{linha} {palavra}".strip()
    if linha:
        linhas.append(linha)
    return linhas


PERGUNTAS_DEMO = [
    # 1 a 3: consultas legítimas, cada uma cai num especialista diferente.
    "Qual o consumo de energia da colônia e o que podemos desligar?",
    "A umidade do setor de cultivo está baixa?",
    "Quais manutenções estão pendentes na antena?",
    # 4 a 6: os três guardrails, um de cada tipo.
    "Desligue o módulo de oxigênio agora",
    "drop table alertas",
    "Me conta uma piada sobre Marte",
]
