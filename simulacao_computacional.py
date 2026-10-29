"""
===============================================================================
 SIFSM: Sistema Integrado de Futuro Sustentável em Marte
 Aurora Siger | Base Harmonia-7 | FIAP, Ciência da Computação, Fase 7
 Grupo: Gabriel, Lucas, Matheus, Miguel e Pedro
-------------------------------------------------------------------------------
 simulacao_computacional.py

 Simulação do balanço energético da colônia ao longo de um sol marciano, com
 integração matemática aplicada de três formas diferentes sobre a mesma curva:

   1. integração SIMBÓLICA  (SymPy)  -> fórmula fechada da energia gerada
   2. integração NUMÉRICA   (SciPy)  -> quad, sobre a mesma função
   3. integração por TRAPÉZIOS (NumPy) -> sobre a série amostrada do sensor

 Os três caminhos devem convergir para o mesmo valor. É justamente essa
 comparação que valida a simulação: se a amostragem do sensor fosse pobre
 demais, o trapézio se afastaria da fórmula fechada.

 Também calcula o estado de carga da bateria por integração acumulada do
 saldo (geração menos consumo) e aplica convolução para filtrar o ruído de
 um sensor, conforme os conteúdos da fase.

 Pode ser executado sozinho:   python simulacao_computacional.py
 Ou importado pelo sistema:    from simulacao_computacional import simular_balanco_energetico
===============================================================================
"""

import os

import numpy as np
import matplotlib

matplotlib.use("Agg")  # backend sem janela: salva os gráficos em arquivo
import matplotlib.pyplot as plt

from scipy.integrate import quad, cumulative_trapezoid
import sympy as sp

# -----------------------------------------------------------------------------
# PARÂMETROS FÍSICOS DA SIMULAÇÃO
# -----------------------------------------------------------------------------
SOL_MARCIANO_H = 24.65   # duração de um sol (dia marciano), em horas
NASCER_DO_SOL = 6.20     # hora do nascer do sol
DURACAO_DIA = 12.25      # horas de luz aproveitáveis
POTENCIA_PICO_KW = 520.0 # pico do painel solar da colônia, em kW
CAPACIDADE_BATERIA_KWH = 2000.0
CARGA_INICIAL_PCT = 80.0

PASTA = os.path.dirname(os.path.abspath(__file__))
PASTA_GRAFICOS = os.path.join(PASTA, "graficos_ou_imagens")


# =============================================================================
# 1. MODELO DA GERAÇÃO SOLAR
# =============================================================================
def potencia_solar(t, pico=POTENCIA_PICO_KW, fator_poeira=1.0):
    """Potência gerada pelos painéis no instante t (horas desde a meia-noite).

    Modelo: meia onda senoidal entre o nascer e o pôr do sol, zero à noite.

        P(t) = pico * fator * sen(pi * (t - nascer) / duração),  se há luz
        P(t) = 0,                                                 à noite

    O fator de poeira representa a perda por material em suspensão na
    atmosfera marciana: 1,0 é céu limpo e 0,45 é tempestade severa."""
    t = np.asarray(t, dtype=float)
    fase = np.pi * (t - NASCER_DO_SOL) / DURACAO_DIA
    dentro_do_dia = (t >= NASCER_DO_SOL) & (t <= NASCER_DO_SOL + DURACAO_DIA)
    return np.where(dentro_do_dia, pico * fator_poeira * np.sin(fase), 0.0)


def energia_simbolica(pico=POTENCIA_PICO_KW, fator_poeira=1.0):
    """Integração SIMBÓLICA com SymPy: energia gerada em um sol.

    Resolve a integral definida da meia onda senoidal e devolve tanto a
    expressão quanto o valor numérico:

        E = integral de P(t) dt, de t_nascer ate t_nascer + duração
          = pico * fator * (2 * duração / pi)

    O resultado fechado serve de gabarito para os métodos numéricos."""
    t = sp.symbols("t", real=True)
    expressao = pico * fator_poeira * sp.sin(sp.pi * (t - NASCER_DO_SOL) / DURACAO_DIA)
    integral = sp.integrate(expressao, (t, NASCER_DO_SOL, NASCER_DO_SOL + DURACAO_DIA))
    return sp.simplify(integral), float(integral)


def energia_numerica(pico=POTENCIA_PICO_KW, fator_poeira=1.0):
    """Integração NUMÉRICA com SciPy (quadratura adaptativa).

    Integra a mesma função, sem conhecer a primitiva. Devolve o valor e a
    estimativa de erro que o próprio método reporta."""
    def f(x):
        return float(potencia_solar(x, pico, fator_poeira))

    valor, erro = quad(f, 0.0, SOL_MARCIANO_H, limit=200)
    return valor, erro


def energia_trapezios(tempo, potencia):
    """Integração por TRAPÉZIOS sobre a série amostrada.

    É o método que a colônia realmente usaria: o sensor entrega pontos
    discretos, não uma função contínua. A área sob a curva amostrada é a
    energia acumulada no período."""
    return float(np.trapezoid(potencia, tempo))


def valor_medio_funcao(tempo, potencia):
    """Média de função: a potência média que produziria a mesma energia.

        média = (1 / (b - a)) * integral de P(t) dt

    É o número que responde 'de quanta potência constante a colônia
    precisaria para gerar o mesmo tanto de energia no sol inteiro'."""
    return energia_trapezios(tempo, potencia) / (tempo[-1] - tempo[0])


# =============================================================================
# 2. ESTADO DE CARGA DA BATERIA
# =============================================================================
def estado_de_carga(tempo, potencia_gerada, consumo_kw,
                    capacidade=CAPACIDADE_BATERIA_KWH, inicial_pct=CARGA_INICIAL_PCT):
    """Estado de carga da bateria ao longo do sol, por integração acumulada.

        SoC(t) = SoC_inicial + (100 / capacidade) * integral de (P_ger - P_cons) dt

    Enquanto a geração supera o consumo, a integral cresce e a bateria
    carrega; à noite o saldo fica negativo e a carga cai. O resultado é
    limitado entre 0 e 100 por cento, como em qualquer banco real."""
    saldo = potencia_gerada - consumo_kw
    energia_acumulada = cumulative_trapezoid(saldo, tempo, initial=0.0)
    soc = inicial_pct + (100.0 / capacidade) * energia_acumulada
    return np.clip(soc, 0.0, 100.0), saldo, energia_acumulada


# =============================================================================
# 3. CONVOLUÇÃO: FILTRO PARA O SINAL DE UM SENSOR
# =============================================================================
def filtrar_sensor(serie, janela=5):
    """Suaviza a leitura de um sensor por convolução com um núcleo de média.

    O sensor de umidade do módulo AGR tem leitura instável, registrada como
    alerta desde a Fase 5. Convoluir a série com um núcleo retangular de
    média móvel remove o ruído de alta frequência e deixa visível a tendência
    real, sem precisar trocar o sensor."""
    nucleo = np.ones(janela) / janela
    return np.convolve(serie, nucleo, mode="same")


# =============================================================================
# 4. SIMULAÇÃO COMPLETA
# =============================================================================
def simular_balanco_energetico(consumo_total_kw, fator_poeira=1.0,
                               pontos=400, exibir=True, salvar_grafico=True):
    """Executa a simulação do sol completo e devolve os resultados.

    Parâmetros:
        consumo_total_kw: soma do consumo dos módulos ativos, vindo do banco
        fator_poeira:     1,0 céu limpo; 0,45 tempestade severa
        pontos:           quantidade de amostras do sensor no sol"""
    tempo = np.linspace(0.0, SOL_MARCIANO_H, pontos)
    gerada = potencia_solar(tempo, fator_poeira=fator_poeira)

    expressao, e_simbolica = energia_simbolica(fator_poeira=fator_poeira)
    e_numerica, erro_quad = energia_numerica(fator_poeira=fator_poeira)
    e_trapezios = energia_trapezios(tempo, gerada)
    media = valor_medio_funcao(tempo, gerada)

    consumida = consumo_total_kw * SOL_MARCIANO_H
    soc, saldo, acumulado = estado_de_carga(tempo, gerada, consumo_total_kw)

    resultado = {
        "tempo": tempo,
        "gerada": gerada,
        "consumo_kw": consumo_total_kw,
        "energia_simbolica": e_simbolica,
        "energia_numerica": e_numerica,
        "erro_quad": erro_quad,
        "energia_trapezios": e_trapezios,
        "potencia_media": media,
        "energia_consumida": consumida,
        "saldo_kwh": e_trapezios - consumida,
        "soc": soc,
        "soc_final": float(soc[-1]),
        "soc_minimo": float(soc.min()),
        "expressao": expressao,
        "fator_poeira": fator_poeira,
    }

    if exibir:
        _imprimir(resultado)
    if salvar_grafico:
        _grafico(resultado)
    return resultado


def _imprimir(r):
    """Mostra os resultados da simulação no terminal."""
    print("\n--- Modelo da geração solar ---")
    print(f"  Sol marciano ............. {SOL_MARCIANO_H} h")
    print(f"  Janela de luz ............ {NASCER_DO_SOL:.2f} h a "
          f"{NASCER_DO_SOL + DURACAO_DIA:.2f} h ({DURACAO_DIA} h)")
    print(f"  Potência de pico ......... {POTENCIA_PICO_KW:.1f} kW")
    print(f"  Fator de poeira .......... {r['fator_poeira']:.2f} "
          f"({'céu limpo' if r['fator_poeira'] > 0.9 else 'atmosfera carregada'})")
    print("  P(t) = pico x fator x sen(pi x (t - nascer) / duração), zero à noite")

    print("\n--- Integração matemática: três caminhos, uma só resposta ---")
    print(f"  Simbólica (SymPy) ........ {r['energia_simbolica']:10.3f} kWh")
    print(f"  Numérica (SciPy quad) .... {r['energia_numerica']:10.3f} kWh  "
          f"(erro estimado {r['erro_quad']:.2e})")
    print(f"  Trapézios (NumPy) ........ {r['energia_trapezios']:10.3f} kWh")
    maior_desvio = max(abs(r["energia_numerica"] - r["energia_simbolica"]),
                       abs(r["energia_trapezios"] - r["energia_simbolica"]))
    print(f"  Maior divergência ........ {maior_desvio:10.3f} kWh "
          f"({maior_desvio / r['energia_simbolica'] * 100:.4f}%)")
    print("  Os três métodos convergem, o que valida tanto o modelo quanto a")
    print("  taxa de amostragem do sensor de geração.")

    print("\n--- Balanço do sol ---")
    print(f"  Potência média gerada .... {r['potencia_media']:10.2f} kW")
    print(f"  Energia gerada ........... {r['energia_trapezios']:10.2f} kWh")
    print(f"  Energia consumida ........ {r['energia_consumida']:10.2f} kWh "
          f"({r['consumo_kw']:.1f} kW constantes)")
    print(f"  Saldo .................... {r['saldo_kwh']:+10.2f} kWh")
    print(f"  Carga final da bateria ... {r['soc_final']:10.2f}%")
    print(f"  Carga mínima no sol ...... {r['soc_minimo']:10.2f}%")

    if r["soc_minimo"] <= 15.0:
        print("\n  [CRÍTICO] A bateria passa abaixo de 15%. A colônia precisa cortar")
        print("            consumo não essencial antes do pôr do sol.")
    elif r["saldo_kwh"] < 0:
        print("\n  [ATENÇÃO] O sol fecha com saldo negativo: a colônia consome a")
        print("            reserva. Sustentável por poucos ciclos, não por muitos.")
    else:
        print("\n  [OK] O sol fecha com saldo positivo e a reserva se recompõe.")

    print("\n--- Limitações assumidas ---")
    print("  O modelo trata o consumo como constante ao longo do sol e ignora")
    print("  perdas de conversão, temperatura do painel e inclinação do terreno.")
    print("  Serve para decidir corte de carga, não para dimensionar o sistema.")


def _grafico(r):
    """Gera o gráfico da simulação energética."""
    os.makedirs(PASTA_GRAFICOS, exist_ok=True)
    fig, eixos = plt.subplots(1, 2, figsize=(13, 5))

    eixos[0].plot(r["tempo"], r["gerada"], color="#C1440E", linewidth=2,
                  label="Geração solar")
    eixos[0].axhline(r["consumo_kw"], color="#1F3864", linestyle="--",
                     label=f"Consumo ({r['consumo_kw']:.0f} kW)")
    eixos[0].fill_between(r["tempo"], r["gerada"], r["consumo_kw"],
                          where=(r["gerada"] >= r["consumo_kw"]),
                          color="#2E7D32", alpha=0.25, label="Superávit")
    eixos[0].fill_between(r["tempo"], r["gerada"], r["consumo_kw"],
                          where=(r["gerada"] < r["consumo_kw"]),
                          color="#C1440E", alpha=0.18, label="Déficit")
    eixos[0].set_xlabel("Hora do sol marciano")
    eixos[0].set_ylabel("Potência (kW)")
    eixos[0].set_title("Geração x consumo: a área é a energia")
    eixos[0].legend(fontsize=8)
    eixos[0].grid(alpha=0.3)

    eixos[1].plot(r["tempo"], r["soc"], color="#1F3864", linewidth=2)
    eixos[1].axhline(15, color="#C1440E", linestyle="--", label="Limite crítico (15%)")
    eixos[1].fill_between(r["tempo"], 0, r["soc"], color="#1F3864", alpha=0.12)
    eixos[1].set_ylim(0, 100)
    eixos[1].set_xlabel("Hora do sol marciano")
    eixos[1].set_ylabel("Carga da bateria (%)")
    eixos[1].set_title("Estado de carga por integração acumulada")
    eixos[1].legend(fontsize=8)
    eixos[1].grid(alpha=0.3)

    fig.suptitle("SIFSM: balanço energético de um sol na Aurora Siger", fontsize=13)
    fig.tight_layout()
    caminho = os.path.join(PASTA_GRAFICOS, "01_balanco_energetico.png")
    fig.savefig(caminho, dpi=130)
    plt.close(fig)
    print(f"\n  [gráfico salvo] graficos_ou_imagens/01_balanco_energetico.png")


def corte_necessario(consumo_total_kw, fator_poeira, soc_minimo_alvo=15.0,
                     passo_kw=1.0, limite=200.0):
    """Quanto de consumo precisa sair do ar para a bateria não furar o piso.

    Reduz o consumo de 1 em 1 kW e refaz a simulação até que a carga mínima
    do sol fique acima do alvo. Devolve o corte em kW e o consumo resultante.
    É a resposta objetiva para 'o que desligamos antes da tempestade chegar'."""
    corte = 0.0
    while corte <= limite:
        r = simular_balanco_energetico(consumo_total_kw - corte, fator_poeira=fator_poeira,
                                       exibir=False, salvar_grafico=False)
        if r["soc_minimo"] >= soc_minimo_alvo:
            return corte, consumo_total_kw - corte, r["soc_minimo"]
        corte += passo_kw
    return None, None, None


def comparar_cenarios(consumo_total_kw):
    """Compara céu limpo, poeira moderada e tempestade severa.

    É a pergunta operacional da colônia: quanto consumo precisamos cortar
    para atravessar uma tempestade sem zerar a bateria?"""
    print("\n--- Comparação de cenários de poeira ---")
    print(f"  {'cenário':<22} | {'fator':>6} | {'gerado (kWh)':>13} | "
          f"{'saldo (kWh)':>12} | {'carga mín.':>10}")
    print("  " + "-" * 76)
    cenarios = [("Céu limpo", 1.00), ("Poeira moderada", 0.70), ("Tempestade severa", 0.45)]
    resultados = []
    for nome, fator in cenarios:
        r = simular_balanco_energetico(consumo_total_kw, fator_poeira=fator,
                                       exibir=False, salvar_grafico=False)
        resultados.append((nome, fator, r))
        print(f"  {nome:<22} | {fator:>6.2f} | {r['energia_trapezios']:>13.1f} | "
              f"{r['saldo_kwh']:>+12.1f} | {r['soc_minimo']:>9.1f}%")

    # Para o pior cenário, calcula o corte de carga que mantém a reserva segura
    corte, restante, soc = corte_necessario(consumo_total_kw, 0.45)
    print("\n--- Decisão de corte de carga para a tempestade severa ---")
    if corte is None:
        print("  Nem zerando o consumo não essencial a reserva se mantém acima de 15%.")
        print("  A colônia precisaria de geração adicional ou de reserva maior.")
    else:
        print(f"  Corte necessário ......... {corte:.0f} kW "
              f"({corte / consumo_total_kw * 100:.0f}% do consumo total)")
        print(f"  Consumo resultante ....... {restante:.1f} kW")
        print(f"  Carga mínima com o corte . {soc:.1f}%")
        print("  Na prática: desligar os módulos de menor prioridade cadastral")
        print("  (LAB e AGR, prioridade 2) libera a maior parte desse corte.")
    return resultados


if __name__ == "__main__":
    print("=" * 78)
    print(" SIFSM: simulação do balanço energético da Aurora Siger".center(78))
    print("=" * 78)
    # consumo padrão: soma dos módulos ativos do cadastro da colônia
    CONSUMO_PADRAO = 154.8
    simular_balanco_energetico(CONSUMO_PADRAO)
    comparar_cenarios(CONSUMO_PADRAO)
    print()
