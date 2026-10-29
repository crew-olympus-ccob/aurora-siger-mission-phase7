/*
 * ============================================================================
 *  SIFSM: Sistema Integrado de Futuro Sustentável em Marte
 *  Aurora Siger | Base Harmonia-7 | FIAP, Ciência da Computação, Fase 7
 *  Grupo: Gabriel, Lucas, Matheus, Miguel e Pedro
 * ----------------------------------------------------------------------------
 *  arduino_irrigacao.ino
 *
 *  Controlador embarcado da irrigação do módulo agrícola (AGR).
 *  Implementa em hardware a mesma regra booleana do sistema em Python:
 *
 *      IRRIGAR  = AGR AND UMID AND SENSOR AND RESERVA
 *      BLOQUEAR = NOT IRRIGAR
 *                = NOT AGR OR NOT UMID OR NOT SENSOR OR NOT RESERVA
 *
 *  Por que rodar isso na borda, e não no servidor central: a decisão é uma
 *  porta AND de quatro entradas. Mandar a leitura por rádio até o centro de
 *  controle para receber a resposta de volta gastaria mais energia de
 *  transmissão do que o microcontrolador gasta para decidir no local. Em uma
 *  colônia onde cada quilowatt-hora sai do mesmo orçamento solar do suporte
 *  de vida, processar na borda é decisão de arquitetura e de sustentabilidade
 *  ao mesmo tempo.
 *
 *  LIGAÇÕES DO CIRCUITO
 *    O esquema completo está no terceiro painel de circuito_logico.png.
 *    Arduino Uno R3, protoboard pequena e:
 *      - 4 chaves (ou push buttons) nas entradas digitais 2, 3, 4 e 5,
 *        cada uma com resistor de 10k ohm em pull-down para o GND;
 *      - LED verde no pino 8, com resistor de 220 ohm (irrigação liberada);
 *      - LED vermelho no pino 9, com resistor de 220 ohm (bloqueio);
 *      - relé (ou um terceiro LED representando a bomba) no pino 10.
 *
 *    Para testar sem as chaves, basta abrir o monitor serial: o programa
 *    imprime a tabela verdade completa na inicialização.
 * ============================================================================
 */

// ---- Pinos de entrada: os quatro sinais da regra --------------------------
const int PINO_AGR     = 2;  // módulo agrícola operante
const int PINO_UMID    = 3;  // umidade do solo abaixo de 35%
const int PINO_SENSOR  = 4;  // leitura do sensor considerada confiável
const int PINO_RESERVA = 5;  // carga da bateria acima de 15%

// ---- Pinos de saída: atuadores -------------------------------------------
const int LED_VERDE    = 8;   // irrigação liberada
const int LED_VERMELHO = 9;   // bloqueio
const int RELE_BOMBA   = 10;  // aciona a bomba de irrigação

// Tempo entre leituras, em milissegundos. Mantido alto de propósito: a
// umidade do solo muda devagar e ler rápido demais só gastaria energia.
const unsigned long INTERVALO_MS = 1000;


void setup() {
  pinMode(PINO_AGR,     INPUT);
  pinMode(PINO_UMID,    INPUT);
  pinMode(PINO_SENSOR,  INPUT);
  pinMode(PINO_RESERVA, INPUT);

  pinMode(LED_VERDE,    OUTPUT);
  pinMode(LED_VERMELHO, OUTPUT);
  pinMode(RELE_BOMBA,   OUTPUT);

  Serial.begin(9600);
  Serial.println(F("SIFSM | Controlador de irrigacao do modulo AGR"));
  Serial.println(F("Regra: IRRIGAR = AGR AND UMID AND SENSOR AND RESERVA"));
  imprimirTabelaVerdade();
}


/*
 * Avalia a regra booleana. É a porta AND de quatro entradas em software:
 * o operador && devolve verdadeiro apenas quando os quatro sinais estão
 * em nível alto, exatamente como o circuito da figura circuito_logico.png.
 */
bool avaliarRegra(bool agr, bool umid, bool sensor, bool reserva) {
  return agr && umid && sensor && reserva;
}


/*
 * Explica qual condição derrubou a decisão, aplicando De Morgan: como
 * BLOQUEAR é a soma lógica das negações, basta descobrir qual delas é
 * verdadeira para saber o motivo do bloqueio.
 */
void explicarBloqueio(bool agr, bool umid, bool sensor, bool reserva) {
  Serial.print(F("  Bloqueado por: "));
  if (!agr)     Serial.print(F("[modulo AGR fora de operacao] "));
  if (!umid)    Serial.print(F("[umidade acima de 35%] "));
  if (!sensor)  Serial.print(F("[sensor sem leitura confiavel] "));
  if (!reserva) Serial.print(F("[bateria abaixo de 15%] "));
  Serial.println();
}


/*
 * Imprime as 16 combinações possíveis. Serve para conferir no monitor
 * serial que o comportamento do hardware bate com a tabela verdade do
 * relatório, sem precisar acionar as chaves uma a uma.
 */
void imprimirTabelaVerdade() {
  Serial.println(F("\nAGR UMID SENS RES | IRRIGAR BLOQ"));
  Serial.println(F("------------------+--------------"));
  for (int a = 0; a <= 1; a++) {
    for (int u = 0; u <= 1; u++) {
      for (int s = 0; s <= 1; s++) {
        for (int r = 0; r <= 1; r++) {
          bool saida = avaliarRegra(a, u, s, r);
          Serial.print(F("  "));   Serial.print(a);
          Serial.print(F("    ")); Serial.print(u);
          Serial.print(F("    ")); Serial.print(s);
          Serial.print(F("    ")); Serial.print(r);
          Serial.print(F("  |    ")); Serial.print(saida ? 1 : 0);
          Serial.print(F("      "));  Serial.println(saida ? 0 : 1);
        }
      }
    }
  }
  Serial.println();
}


void loop() {
  // Leitura dos quatro sinais de entrada
  bool agr     = digitalRead(PINO_AGR)     == HIGH;
  bool umid    = digitalRead(PINO_UMID)    == HIGH;
  bool sensor  = digitalRead(PINO_SENSOR)  == HIGH;
  bool reserva = digitalRead(PINO_RESERVA) == HIGH;

  bool irrigar = avaliarRegra(agr, umid, sensor, reserva);

  // Acionamento dos atuadores
  digitalWrite(LED_VERDE,    irrigar ? HIGH : LOW);
  digitalWrite(LED_VERMELHO, irrigar ? LOW  : HIGH);
  digitalWrite(RELE_BOMBA,   irrigar ? HIGH : LOW);

  // Registro no monitor serial, que faz o papel do log da colônia
  Serial.print(F("AGR="));     Serial.print(agr);
  Serial.print(F(" UMID="));   Serial.print(umid);
  Serial.print(F(" SENSOR=")); Serial.print(sensor);
  Serial.print(F(" RESERVA="));Serial.print(reserva);
  Serial.print(F(" -> "));
  Serial.println(irrigar ? F("IRRIGAR") : F("BLOQUEAR"));

  if (!irrigar) {
    explicarBloqueio(agr, umid, sensor, reserva);
  }

  delay(INTERVALO_MS);
}
