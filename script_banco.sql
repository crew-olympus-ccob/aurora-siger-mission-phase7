-- =============================================================================
-- SIFSM: Sistema Integrado de Futuro Sustentável em Marte
-- Aurora Siger | Base Harmonia-7 | FIAP, Ciência da Computação, Fase 7
-- Grupo: Gabriel, Lucas, Matheus, Miguel e Pedro
-- -----------------------------------------------------------------------------
-- script_banco.sql
-- Criação e carga inicial do banco de dados do SIFSM.
--
-- O banco usado no projeto é SQLite, que acompanha a biblioteca padrão do
-- Python (módulo sqlite3) e não exige servidor nem instalação. A modelagem,
-- os tipos, as chaves primárias e estrangeiras e as operações de CRUD seguem
-- o SQL padrão, então o mesmo script roda em Oracle com ajustes mínimos de
-- tipo (VARCHAR2 no lugar de TEXT, NUMBER no lugar de REAL).
--
-- Este arquivo é executado automaticamente por codigo_fonte.py na primeira
-- execução, pela função criar_banco(). Também pode ser rodado à mão:
--     sqlite3 aurora_siger.db < script_banco.sql
--
-- CONTINUIDADE: os módulos, prioridades e consumos vêm do cadastro oficial
-- da colônia, usado desde a Fase 5 (dados_colonia.json do NCAS) e mantido na
-- Fase 6 (SCIC). A rede física entre os módulos vem do grafo da Fase 4 (SIGIC).
-- =============================================================================

DROP TABLE IF EXISTS leituras;
DROP TABLE IF EXISTS solicitacoes;
DROP TABLE IF EXISTS manutencoes;
DROP TABLE IF EXISTS alertas;
DROP TABLE IF EXISTS sensores;
DROP TABLE IF EXISTS conexoes;
DROP TABLE IF EXISTS modulos;

-- -----------------------------------------------------------------------------
-- 1. MODULOS: o cadastro da colônia, herdado das fases anteriores
-- -----------------------------------------------------------------------------
CREATE TABLE modulos (
    codigo            TEXT PRIMARY KEY,
    nome              TEXT    NOT NULL,
    tipo              TEXT    NOT NULL,
    prioridade        INTEGER NOT NULL CHECK (prioridade BETWEEN 1 AND 5),
    consumo_kw        REAL    NOT NULL CHECK (consumo_kw >= 0),
    status            TEXT    NOT NULL DEFAULT 'ATIVO',
    origem_cadastro   TEXT    NOT NULL
);

-- -----------------------------------------------------------------------------
-- 2. CONEXOES: a rede física entre módulos (grafo da Fase 4, em metros)
-- -----------------------------------------------------------------------------
CREATE TABLE conexoes (
    origem    TEXT    NOT NULL,
    destino   TEXT    NOT NULL,
    distancia INTEGER NOT NULL CHECK (distancia > 0),
    PRIMARY KEY (origem, destino),
    FOREIGN KEY (origem)  REFERENCES modulos (codigo),
    FOREIGN KEY (destino) REFERENCES modulos (codigo)
);

-- -----------------------------------------------------------------------------
-- 3. SENSORES: cada módulo expõe sensores com código hexadecimal
--    O primeiro dígito do código identifica a família do módulo (ver Fase 6).
-- -----------------------------------------------------------------------------
CREATE TABLE sensores (
    codigo_sensor  TEXT PRIMARY KEY,
    codigo_modulo  TEXT NOT NULL,
    grandeza       TEXT NOT NULL,
    unidade        TEXT NOT NULL,
    ativo          INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (codigo_modulo) REFERENCES modulos (codigo)
);

-- -----------------------------------------------------------------------------
-- 4. LEITURAS: a telemetria por ciclo (sol marciano)
-- -----------------------------------------------------------------------------
CREATE TABLE leituras (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_sensor  TEXT    NOT NULL,
    ciclo          INTEGER NOT NULL CHECK (ciclo > 0),
    data           TEXT    NOT NULL,
    valor          REAL    NOT NULL,
    FOREIGN KEY (codigo_sensor) REFERENCES sensores (codigo_sensor)
);

CREATE INDEX idx_leituras_sensor ON leituras (codigo_sensor);
CREATE INDEX idx_leituras_ciclo  ON leituras (ciclo);

-- -----------------------------------------------------------------------------
-- 5. ALERTAS: ocorrências operacionais e ambientais (alvo do CRUD completo)
-- -----------------------------------------------------------------------------
CREATE TABLE alertas (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_modulo  TEXT    NOT NULL,
    tipo           TEXT    NOT NULL,
    critico        INTEGER NOT NULL DEFAULT 0 CHECK (critico IN (0, 1)),
    mensagem       TEXT    NOT NULL,
    data           TEXT    NOT NULL,
    resolvido      INTEGER NOT NULL DEFAULT 0 CHECK (resolvido IN (0, 1)),
    FOREIGN KEY (codigo_modulo) REFERENCES modulos (codigo)
);

-- -----------------------------------------------------------------------------
-- 6. MANUTENCOES: histórico de ações, lido como pilha (a última entra primeiro)
-- -----------------------------------------------------------------------------
CREATE TABLE manutencoes (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_modulo  TEXT NOT NULL,
    acao           TEXT NOT NULL,
    responsavel    TEXT NOT NULL,
    data           TEXT NOT NULL,
    FOREIGN KEY (codigo_modulo) REFERENCES modulos (codigo)
);

-- -----------------------------------------------------------------------------
-- 7. SOLICITACOES: pedidos da tripulação, atendidos em fila por prioridade
-- -----------------------------------------------------------------------------
CREATE TABLE solicitacoes (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    solicitante    TEXT    NOT NULL,
    codigo_modulo  TEXT    NOT NULL,
    descricao      TEXT    NOT NULL,
    urgencia       INTEGER NOT NULL DEFAULT 3 CHECK (urgencia BETWEEN 1 AND 5),
    data           TEXT    NOT NULL,
    atendida       INTEGER NOT NULL DEFAULT 0 CHECK (atendida IN (0, 1)),
    FOREIGN KEY (codigo_modulo) REFERENCES modulos (codigo)
);

-- =============================================================================
-- CARGA INICIAL
-- =============================================================================

-- Os oito primeiros módulos vêm do cadastro da Fase 5; os quatro seguintes
-- foram acrescentados na Fase 6 e são mantidos aqui.
INSERT INTO modulos (codigo, nome, tipo, prioridade, consumo_kw, status, origem_cadastro) VALUES
    ('HAB',   'Habitação',                'habitacao',      4, 18.5, 'ATIVO',      'Fase 5'),
    ('MED',   'Suporte Médico',           'suporte_medico', 5, 12.3, 'ATIVO',      'Fase 5'),
    ('OXI',   'Produção de Oxigênio',     'suporte_vida',   5, 24.7, 'ATIVO',      'Fase 5'),
    ('CTR',   'Centro de Controle',       'controle',       4, 15.1, 'ATIVO',      'Fase 5'),
    ('ENE',   'Armazenamento de Energia', 'energia',        5,  5.4, 'ATIVO',      'Fase 5'),
    ('AGR',   'Agricultura',              'agricultura',    2, 21.0, 'MANUTENCAO', 'Fase 5'),
    ('LAB',   'Laboratório Científico',   'laboratorio',    2, 13.8, 'ATIVO',      'Fase 5'),
    ('COM',   'Comunicação',              'comunicacao',    5,  9.6, 'MANUTENCAO', 'Fase 5'),
    ('COM-R', 'Enlace Redundante',        'comunicacao',    3,  8.9, 'ATIVO',      'Fase 6'),
    ('DAT',   'Armazenamento de Dados',   'armazenamento',  4, 11.2, 'ATIVO',      'Fase 6'),
    ('BKP',   'Backup Redundante',        'armazenamento',  3,  7.8, 'ATIVO',      'Fase 6'),
    ('EXT',   'Antena Externa Remota',    'comunicacao',    3,  6.5, 'ATIVO',      'Fase 6');

-- A rede física da colônia, com as distâncias em metros definidas na Fase 4.
-- As quatro últimas ligam os módulos criados na Fase 6 à topologia original.
INSERT INTO conexoes (origem, destino, distancia) VALUES
    ('HAB', 'MED',  50), ('HAB', 'OXI',  30), ('HAB', 'CTR',  80),
    ('HAB', 'ENE',  55), ('HAB', 'COM',  75), ('CTR', 'ENE',  40),
    ('CTR', 'COM',  60), ('CTR', 'LAB',  70), ('ENE', 'OXI',  35),
    ('ENE', 'AGR',  90), ('ENE', 'MED',  45), ('OXI', 'MED',  40),
    ('AGR', 'LAB',  65),
    ('COM', 'COM-R', 25), ('CTR', 'DAT',  35), ('DAT', 'BKP',  55),
    ('COM-R', 'EXT', 550);

-- Sensores por módulo. O primeiro dígito hexadecimal indica a família:
-- 1 habitação, 2 agricultura, 3 comunicação e controle, 4 laboratório,
-- 5 suporte médico, 6 armazenamento, 7 suporte vital e energia.
INSERT INTO sensores (codigo_sensor, codigo_modulo, grandeza, unidade) VALUES
    ('0x1A3F', 'HAB',   'consumo',       'kW'),
    ('0x1A40', 'HAB',   'temperatura',   'C'),
    ('0x2A10', 'AGR',   'umidade',       '%'),
    ('0x2A11', 'AGR',   'luminosidade',  'lux'),
    ('0x2A12', 'AGR',   'consumo',       'kW'),
    ('0x3C01', 'COM',   'latencia',      'ms'),
    ('0x3C02', 'COM-R', 'latencia',      'ms'),
    ('0x3D11', 'CTR',   'consumo',       'kW'),
    ('0x3E40', 'EXT',   'latencia',      'ms'),
    ('0x4E30', 'LAB',   'consumo',       'kW'),
    ('0x5F09', 'MED',   'consumo',       'kW'),
    ('0x6A77', 'DAT',   'carga_dados',   'GB'),
    ('0x6A78', 'BKP',   'carga_dados',   'GB'),
    ('0x7A05', 'ENE',   'carga_bateria', '%'),
    ('0x7A06', 'ENE',   'geracao_solar', 'kW'),
    ('0x7B12', 'OXI',   'consumo',       'kW');

-- Alertas herdados: as três recomendações que a Fase 6 deixou em aberto.
INSERT INTO alertas (codigo_modulo, tipo, critico, mensagem, data, resolvido) VALUES
    ('COM', 'Degradação progressiva', 1,
     'Antena com erro crescente de 1,58 ponto percentual por ciclo desde a Fase 5.',
     '2026-09-26', 0),
    ('COM-R', 'Reconfiguração de rota', 0,
     'Assumir tráfego crítico enquanto a antena principal estiver em manutenção.',
     '2026-09-26', 0),
    ('AGR', 'Manutenção preventiva', 0,
     'Sensor de umidade do setor de cultivo com leitura instável.',
     '2026-09-28', 0);

-- Histórico inicial de manutenção, que alimenta a pilha de ações.
INSERT INTO manutencoes (codigo_modulo, acao, responsavel, data) VALUES
    ('CTR', 'Substituição de placa de comunicação interna', 'ENG_ROCHA',  '2026-08-28'),
    ('OXI', 'Verificação de rotina nos compressores',       'ENG_ROCHA',  '2026-08-30'),
    ('COM', 'Diagnóstico de perda intermitente de sinal',   'CMDT_SILVA', '2026-09-01');

-- Fila inicial de solicitações da tripulação.
INSERT INTO solicitacoes (solicitante, codigo_modulo, descricao, urgencia, data, atendida) VALUES
    ('MED_ALVES',  'MED', 'Reposição de kit de primeiros socorros',        5, '2026-09-27', 0),
    ('ENG_ROCHA',  'AGR', 'Revisar irrigação do setor de cultivo norte',   3, '2026-09-27', 0),
    ('CMDT_SILVA', 'COM', 'Agendar janela de manutenção da antena',        4, '2026-09-28', 0),
    ('ENG_ROCHA',  'LAB', 'Calibrar bancada de análise de solo',           2, '2026-09-29', 0);
