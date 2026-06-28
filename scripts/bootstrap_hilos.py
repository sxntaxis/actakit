#!/usr/bin/env python3
"""
Bootstrap system for automatic hilo taxonomy generation.

Multi-pass orchestrator:
  1. Load seed taxonomy (24 universal hilos for CR municipalities).
  2. Parse processed actas into items (episodios).
  3. Extract entities from each item.
  4. Classify items via seed taxonomy signals.
  5. Cluster unclassified items by entity co-occurrence.
  6. Generate report + optional enrutamiento.yaml.

Usage:
  python bootstrap_hilos.py --actas-dir ./data/procesadas/ [--output ./bootstrap/]
"""

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Set, Tuple

from entity_index import (
    extract_entities,
    entity_overlap,
    jaccard_similarity,
    build_entity_frequency,
    load_local_places,
    INSTITUTION_CATEGORY,
)

# ── Seed Taxonomy ─────────────────────────────────────────────────────────
# Universal seed for any Costa Rican municipality.
# Structure: hilo_name -> { 'senales': [str], 'entities': [str] }

SEED_HILOS = {

    # ── Bloque: Gestion Interna y Administracion ──
    "Concejo Municipal y Funcionamiento": {
        "senales": [
            "sesion extraordinaria",
            "sesion ordinaria",
            "citacion a regidores",
            "ausencia de regidor",
            "licencia de regidor",
            "juramentacion de",
            "comision municipal",
            "comision especifica",
            "comision de salud",
            "comision de ambiente",
            "comision de presupuesto",
            "mocion de orden",
            "mocion de fondo",
            "votacion de",
            "quorum",
            "orden del dia",
            "agenda de la sesion",
            "convocatoria a sesion",
            "acta anterior",
            "aprobacion del acta",
            "conformacion de comisiones",
            "presidencia municipal",
            "vicepresidencia municipal",
            "regidor propietario",
            "regidor suplente",
            "sindico propietario",
            "sindico suplente",
            "secretario municipal",
            "alcalde municipal",
            "informe de comision",
            "dictamen de comision",
        ],
        "entities": ["CGR", "PGR", "TSE", "DINADECO", "UNGL"],
    },

    "Auditoría y Control Interno": {
        "senales": [
            "auditoria interna",
            "informe de auditoria",
            "auditor interno",
            "auditora interna",
            "control interno",
            "hallazgo de auditoria",
            "recomendacion de auditoria",
            "plan de mejoramiento",
            "seguimiento de recomendaciones",
            "informe final de auditoria",
            "labor de auditoria",
            "oficio auditoria",
        ],
        "entities": ["CGR", "DFOE"],
    },

    "Presupuesto, Finanzas, Tarifas y Planificación": {
        "senales": [
            "presupuesto municipal",
            "presupuesto extraordinario",
            "modificacion presupuestaria",
            "ejecucion presupuestaria",
            "liquidacion presupuestaria",
            "plan de gastos",
            "partida presupuestaria",
            "transferencia de partida",
            "impuesto municipal",
            "impuesto de bienes inmuebles",
            "tasa municipal",
            "tasa de recoleccion",
            "tarifa municipal",
            "canon municipal",
            "patente municipal",
            "patente comercial",
            "renovacion de patente",
            "presupuesto participativo",
            "plan operativo anual",
            "plan de desarrollo",
            "plan estrategico",
            "plan cantonal",
            "plan de inversion",
            "POA",
            "plan de desarrollo humano",
        ],
        "entities": ["MH", "IFAM"],
    },

    "Contratación, Activos y Mercado Municipal": {
        "senales": [
            "contratacion administrativa",
            "licitacion publica",
            "licitacion abreviada",
            "contratacion directa",
            "proveedor unico",
            "pliego de condiciones",
            "adjudicacion de",
            "compra municipal",
            "remate municipal",
            "subasta municipal",
            "concesion de",
            "arrendamiento municipal",
            "comodato",
            "donacion a la municipalidad",
            "adquisicion de",
            "compra verde",
            "SICOP",
            "cartel de licitacion",
            "evaluacion de ofertas",
            "contrato municipal",
        ],
        "entities": ["COPROCOM"],
    },

    "Transparencia, Datos, Tecnología y Comunicación": {
        "senales": [
            "transparencia",
            "rendicion de cuentas",
            "acceso a la informacion",
            "portal unico",
            "datos abiertos",
            "informacion publica",
            "libro de actas",
            "publicacion de",
            "sitio web municipal",
            "transparencia municipal",
        ],
        "entities": [],
    },

    "Capacitación, Talento Humano y Jornadas": {
        "senales": [
            "capacitacion a funcionarios",
            "capacitacion a regidores",
            "recurso humano",
            "funcionario municipal",
            "personal municipal",
            "empleado municipal",
            "jornada laboral",
            "horario de atencion",
            "horario de oficina",
            "vacaciones",
            "aguinaldo",
            "salario municipal",
            "escalafon municipal",
            "manual de puestos",
            "evaluacion de desempeno",
            "ausencia del personal",
            "permiso laboral",
        ],
        "entities": [],
    },

    # ── Bloque: Servicios Publicos e Infraestructura ──
    "Agua Potable, AyA y ASADAS": {
        "senales": [
            "agua potable",
            "servicio de agua",
            "acueducto municipal",
            "acueducto rural",
            "ASADA",
            "ASADAS",
            "AyA",
            "calidad del agua",
            "cloro residual",
            "analisis de agua",
            "tanque de agua",
            "pozo municipal",
            "naciente",
            "tuberia de agua",
            "red de distribucion",
            "corte de agua",
            "racionamiento de agua",
            "morosidad ASADA",
            "subsidio de agua",
            "medidor de agua",
            "microcuenca",
            "cuenca hidrografica",
            "alcantarillado sanitario",
            "tratamiento de aguas",
            "planta de tratamiento",
            "aguas residuales",
        ],
        "entities": ["AYA", "ASADA", "ASADAS", "ARESEP", "SENARA"],
    },

    "Movilidad, Red Vial y Transporte Público": {
        "senales": [
            "red vial",
            "camino municipal",
            "calle municipal",
            "carretera",
            "puente",
            "baden",
            "alcantarilla",
            "cuneta",
            "lastre",
            "asfalto",
            "reparacion de camino",
            "mantenimiento de camino",
            "mejora de calle",
            "construccion de puente",
            "puente peatonal",
            "aceras",
            "paso peatonal",
            "senalizacion vial",
            "calle publica",
            "camino vecinal",
            "ruta nacional",
            "transporte publico",
            "ruta de autobus",
            "parada de autobus",
            "taxi",
            "circulacion vehicular",
            "transito",
            "trafico",
            "estacionamiento",
            "velocidad",
            "red vial cantonal",
            "plan vial",
            "inversion vial",
        ],
        "entities": ["MOPT", "CONAVI", "CTP", "INCOFER"],
    },

    "Infraestructura Comunal y Espacios Públicos": {
        "senales": [
            "salon comunal",
            "parque",
            "plaza",
            "cancha deportiva",
            "polideportivo",
            "gimnasio municipal",
            "centro civico",
            "cementerio municipal",
            "mercado municipal",
            "feria del agricultor",
            "terminal de autobuses",
            "estadio municipal",
            "piscina municipal",
            "biblioteca municipal",
            "centro cultural",
            "casa de la cultura",
            "mantenimiento de parque",
            "construccion de salon",
            "juego infantil",
            "area recreativa",
            "espacio publico",
            "iluminacion de",
            "banco de parque",
        ],
        "entities": ["ICE"],
    },

    "Vivienda, Asentamientos y Urbanizaciones": {
        "senales": [
            "vivienda de interes social",
            "bonus de vivienda",
            "bono de vivienda",
            "asentamiento",
            "urbanizacion",
            "loteo",
            "fraccionamiento",
            "tugurio",
            "precario",
            "invasion",
            "terreno municipal",
            "lote municipal",
            "vivienda digna",
            "asentamiento informal",
            "catastro municipal",
            "avaluo",
        ],
        "entities": ["MIVAH", "INVU", "BANHVI"],
    },

    "Ordenamiento Territorial y Plan Regulador": {
        "senales": [
            "plan regulador",
            "ordenamiento territorial",
            "uso del suelo",
            "zona urbana",
            "zona rural",
            "desarrollo urbano",
            "construccion",
            "permiso de construccion",
            "visado",
            "catastro",
            "terreno",
            "lote",
            "finca",
            "zona maritimo terrestre",
            "zona maritimo-terrestre",
            "concesion de zona maritimo",
            "terreno publico",
            "franja costera",
            "camino publico",
            "servidumbre",
            "plusvalia",
            "plusvalia municipal",
        ],
        "entities": ["INVU", "SETENA", "MINAE"],
    },

    "Gestión del Riesgo, Emergencias y Aguas Pluviales": {
        "senales": [
            "emergencia",
            "inundacion",
            "tormenta",
            "deslizamiento",
            "derrrumbe",
            "huracan",
            "tormenta tropical",
            "comite de emergencia",
            "comision de emergencia",
            "plan de emergencia",
            "albergue",
            "evacuacion",
            "amenaza natural",
            "riesgo",
            "zona de riesgo",
            "quebrada",
            "rio",
            "cauce",
            "aguas pluviales",
            "drenaje pluvial",
            "alcantarilla pluvial",
            "desbordamiento",
            "cuerpo de bomberos",
            "cruz roja",
        ],
        "entities": ["CNE"],
    },

    # ── Bloque: Desarrollo Social y Calidad de Vida ──
    "Salud Pública, CCSS, EBAIS y Campañas": {
        "senales": [
            "EBAIS",
            "CCSS",
            "clinica",
            "hospital",
            "centro de salud",
            "campana de salud",
            "jornada de salud",
            "vacunacion",
            "dengue",
            "zika",
            "chikungunya",
            "leptospira",
            "fumigacion",
            "abate",
            "eliminacion de criaderos",
            "promocion de la salud",
            "salud mental",
            "nutricion",
            "seguro social",
            "atencion primaria",
            "citas medicas",
            "medicamentos",
            "farmacia",
            "cap",
        ],
        "entities": ["CCSS", "MINSA", "MS", "EBAIS", "CAP", "JPS"],
    },

    "Educación, Becas e Infraestructura Educativa": {
        "senales": [
            "escuela",
            "colegio",
            "institucion educativa",
            "beca municipal",
            "beca de estudio",
            "transporte escolar",
            "comedor escolar",
            "infraestructura educativa",
            "mantenimiento de escuela",
            "construccion de aula",
            "cierre de matricula",
            "junta de educacion",
            "junta administrativa",
            "matricula",
            "centro educativo",
            "alfabetizacion",
            "educacion de adultos",
        ],
        "entities": ["MEP"],
    },

    "Cultura, Identidad, Memoria y Patrimonio": {
        "senales": [
            "actividad cultural",
            "festival",
            "fiesta patronal",
            "tradicion",
            "patrimonio historico",
            "patrimonio cultural",
            "museo municipal",
            "biblioteca",
            "taller cultural",
            "curso de arte",
            "musica",
            "danza",
            "teatro",
            "pintura",
            "artesania",
            "identidad cantonal",
            "simbolo local",
            "bandera cantonal",
            "escudo cantonal",
            "anecdotas costumbristas",
            "memoria historica",
            "historia local",
            "personaje historico",
            "reina del canton",
            "desfile de",
        ],
        "entities": ["MCJ"],
    },

    "Juventudes": {
        "senales": [
            "persona joven",
            "juventud",
            "CCPJ",
            "comite cantonal de la persona joven",
            "centro civico por la paz",
            "espacio juvenil",
            "taller juvenil",
            "programa juvenil",
            "proyecto juvenil",
            "liderazgo juvenil",
            "prevencion violencia juvenil",
        ],
        "entities": ["CPJ", "CCPJ"],
    },

    "Mujeres y Política de Género": {
        "senales": [
            "mujer",
            "oficina de la mujer",
            "OFIM",
            "igualdad de genero",
            "violencia de genero",
            "violencia domestica",
            "acoso",
            "discriminacion",
            "empoderamiento femenino",
            "taller de genero",
            "casa de la mujer",
            "ruta de atencion",
            "denuncia por violencia",
            "patronato de la mujer",
            "politica de genero",
            "equidad de genero",
        ],
        "entities": ["INAMU", "OFIM"],
    },

    "Cuidados, Niñez y Personas Adultas Mayores": {
        "senales": [
            "persona adulta mayor",
            "adulto mayor",
            "persona mayor",
            "nino",
            "nina",
            "infancia",
            "adolescencia",
            "PANI",
            "IMAS",
            "cuido",
            "hogar de ancianos",
            "centro de cuido",
            "jornada de atencion",
            "beneficio social",
            "ayuda social",
            "bono de",
            "subsidio",
            "pobreza",
            "vulnerabilidad",
            "exclusion social",
        ],
        "entities": ["PANI", "IMAS", "CONAPAM"],
    },

    "Personas en Situación de Calle y Adicciones": {
        "senales": [
            "situacion de calle",
            "persona en condicion de calle",
            "habitante de calle",
            "adiccion",
            "drogas",
            "farmacodependencia",
            "alcoholismo",
            "consumo de drogas",
            "narcotrafico",
            "microtrafico",
            "prevencion de adicciones",
            "rehabilitacion",
            "IAFA",
            "centro de atencion",
        ],
        "entities": ["IAFA"],
    },

    "Accesibilidad y Discapacidad": {
        "senales": [
            "accesibilidad",
            "discapacidad",
            "persona con discapacidad",
            "COMAD",
            "comite municipal de accesibilidad",
            "rampa",
            "barrera arquitectonica",
            "senalizacion inclusiva",
            "transporte accesible",
            "espacio inclusivo",
            "CONAPDIS",
        ],
        "entities": ["CONAPDIS", "COMAD"],
    },

    "Deporte y Recreación": {
        "senales": [
            "deporte",
            "actividad deportiva",
            "torneo",
            "campeonato",
            "clase de deporte",
            "escuela deportiva",
            "entrenamiento",
            "competencia deportiva",
            "juego deportivo",
            "olimpiada",
            "cancha",
            "gimnasio",
            "piscina",
            "equipo deportivo",
            "asociacion deportiva",
            "club deportivo",
            "junta deportiva",
        ],
        "entities": [],
    },

    # ── Bloque: Economia Local ──
    "Economía Local, Comercio, Turismo y Emprendimientos": {
        "senales": [
            "comercio local",
            "pequeno negocio",
            "emprendedor",
            "emprendimiento",
            "feria del agricultor",
            "mercado municipal",
            "turismo",
            "desarrollo turistico",
            "atractivo turistico",
            "hotel",
            "restaurante",
            "PYME",
            "MIPYME",
            "exportacion",
            "artesania local",
            "producto local",
            "encadenamiento productivo",
            "desarrollo economico",
            "inversion local",
            "empleo",
            "generacion de empleo",
            "polo turistico",

        ],
        "entities": ["MEIC", "ICT", "INA", "INDER", "MAG", "INCOP"],
    },

    # ── Bloque: Seguridad y Convivencia ──
    "Seguridad Ciudadana, Policía Municipal y Convivencia": {
        "senales": [
            "seguridad",
            "policia municipal",
            "vigilancia",
            "patrullaje",
            "camaras de seguridad",
            "camara de vigilancia",
            "prevencion del delito",
            "violencia",
            "asalto",
            "robo",
            "hurto",
            "vandalismo",
            "seguridad comunitaria",
            "comite de seguridad",
            "convivencia pacifica",
            "conflicto vecinal",
            "mediacion",
            "conciliacion",
            "juez de paz",
            "juzgado",
            "fiscalia",
            "faltas y contravenciones",
            "ruidos",
            "animal domestico",
            "perro",
            "mascota",
            "animal callejero",
            "especies exoticas",
        ],
        "entities": [],
    },

    # ── Bloque: Ambiente y Territorio ──
    "Ambiente, Conservación y Afectaciones": {
        "senales": [
            "ambiente",
            "conservacion",
            "reforestacion",
            "arbol",
            "bosque",
            "manglar",
            "humedal",
            "cuenca",
            "quebrada",
            "rio",
            "playa",
            "contaminacion",
            "desechos solidos",
            "basura",
            "reciclaje",
            "separacion de residuos",
            "relleno sanitario",
            "vertedero",
            "desecho especial",
            "desecho peligroso",
            "quema",
            "tala",
            "monocultivo",
            "plaguicida",
            "agroquimico",
            "cambio climatico",
            "huella de carbono",
            "carbono neutral",
            "energia renovable",
            "limpia de",
            "jornada de limpieza",
            "playa limpia",
            "reserva biologica",
            "parque nacional",
            "area protegida",
            "vida silvestre",
            "fauna",
            "flora",
            "animal silvestre",
            "especie invasora",
        ],
        "entities": ["MINAE", "SETENA", "SINAC", "DIGECA", "SENASA"],
    },
}


# ── Classification ────────────────────────────────────────────────────────

SIGNAL_CACHE = {}


def compile_signals(hilo_name):
    """Compile senales for a hilo into regex patterns."""
    if hilo_name in SIGNAL_CACHE:
        return SIGNAL_CACHE[hilo_name]
    patterns = []
    for s in SEED_HILOS[hilo_name]["senales"]:
        patterns.append(re.compile(re.escape(s), re.IGNORECASE))
    SIGNAL_CACHE[hilo_name] = patterns
    return patterns


def classify_item(text, hilo_name):
    """Check if a text matches any signal of a hilo."""
    patterns = compile_signals(hilo_name)
    for p in patterns:
        if p.search(text):
            return True
    return False


def classify_with_seed(text):
    """Return all seed hilos that match this text."""
    matches = []
    for hilo_name in SEED_HILOS:
        if classify_item(text, hilo_name):
            matches.append(hilo_name)
    return matches


# ── Acta Parsing (Format A — canonical) ────────────────────────────────────

# Canonical format (per _formato-intermedio.md):
#   ### → Hilo: `Bloque/Hilo`
#   #### YYYY-MM-DD — <Título del episodio>
HILO_HEADER = re.compile(r'^### → Hilo: `([^`]+)`\s*(?:\(condensado\))?\s*$')
EPISODE_HEADER = re.compile(r'^#### (\d{4}-\d{2}-\d{2}) — (.+)$')
ACTA_HEADER = re.compile(r'^Acta\s+N(?:\.?\s*°?\s*|o\.?\s*)?(\d+)', re.IGNORECASE)


def parse_acta_file(filepath):
    """
    Parse a processed acta Markdown file into items using Format A.

    Each item = one episodio with hilo, date, and body.

    Returns list of dicts with keys: id, hilo, date, title, body, file.
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    items = []
    current_acta_num = None
    current_hilo = None
    current_episode = None
    current_body_lines = []
    in_episodes = False

    for line in lines:
        stripped = line.rstrip('\n')

        if stripped == '## Episodios':
            in_episodes = True
            continue

        if not in_episodes:
            m = ACTA_HEADER.search(stripped)
            if m:
                current_acta_num = m.group(1)
            continue

        # Stop at next top-level section
        if re.match(r'^## ', stripped) and stripped != '## Episodios':
            break

        m = HILO_HEADER.match(stripped)
        if m:
            if current_episode is not None:
                body = '\n'.join(current_body_lines).strip()
                item_id = f"A{current_acta_num or '?'}_{current_episode['title'][:30]}"
                items.append({
                    'id': item_id,
                    'hilo': current_hilo or '',
                    'date': current_episode['date'],
                    'title': current_episode['title'],
                    'body': body,
                    'file': os.path.basename(filepath),
                })
            current_hilo = m.group(1).strip()
            current_episode = None
            current_body_lines = []
            continue

        m = EPISODE_HEADER.match(stripped)
        if m:
            if current_episode is not None:
                body = '\n'.join(current_body_lines).strip()
                item_id = f"A{current_acta_num or '?'}_{current_episode['title'][:30]}"
                items.append({
                    'id': item_id,
                    'hilo': current_hilo or '',
                    'date': current_episode['date'],
                    'title': current_episode['title'],
                    'body': body,
                    'file': os.path.basename(filepath),
                })
            current_episode = {'date': m.group(1), 'title': m.group(2)}
            current_body_lines = []
            continue

        if current_episode is not None:
            current_body_lines.append(stripped)

    if current_episode is not None:
        body = '\n'.join(current_body_lines).strip()
        item_id = f"A{current_acta_num or '?'}_{current_episode['title'][:30]}"
        items.append({
            'id': item_id,
            'hilo': current_hilo or '',
            'date': current_episode['date'],
            'title': current_episode['title'],
            'body': body,
            'file': os.path.basename(filepath),
        })

    return items


def parse_actas_directory(actas_dir):
    """Parse all processed acta Markdown files in directory."""
    all_items = []
    for fname in sorted(os.listdir(actas_dir)):
        if fname.endswith('.md'):
            fpath = os.path.join(actas_dir, fname)
            try:
                items = parse_acta_file(fpath)
                all_items.extend(items)
            except Exception as e:
                print(f"  \u26a0 Error parsing {fname}: {e}", file=sys.stderr)
    return all_items


# ── Clustering ────────────────────────────────────────────────────────────

def cluster_by_entities(items, min_shared=2, min_jaccard=0.15):
    """
    Cluster items by entity co-occurrence.

    Transitive merge: two items belong to same cluster if they share
    at least min_shared entities OR have Jaccard >= min_jaccard.

    Returns list of clusters, each cluster is a list of item indices.
    """
    n = len(items)
    if n == 0:
        return []

    entity_sets = []
    for item in items:
        ents = item.get('entities', {}).get('all_names', set())
        entity_sets.append(ents)

    adj = {i: {i} for i in range(n)}
    for i in range(n):
        for j in range(i + 1, n):
            if not entity_sets[i] or not entity_sets[j]:
                continue
            shared = entity_overlap(entity_sets[i], entity_sets[j])
            jacc = jaccard_similarity(entity_sets[i], entity_sets[j])
            if shared >= min_shared or jacc >= min_jaccard:
                adj[i].add(j)
                adj[j].add(i)

    visited = set()
    clusters = []
    for i in range(n):
        if i in visited:
            continue
        cluster = []
        stack = [i]
        while stack:
            node = stack.pop()
            if node in visited:
                continue
            visited.add(node)
            cluster.append(node)
            for neighbor in adj[node]:
                if neighbor not in visited:
                    stack.append(neighbor)
        if len(cluster) >= 2:
            clusters.append(cluster)

    return clusters


# ── Analysis ──────────────────────────────────────────────────────────────

def analyze_cluster(cluster_items):
    """
    Analyze a cluster to determine its characteristics.
    """
    all_entities = set()
    entity_freq = Counter()
    for item in cluster_items:
        entities = item.get('entities', {}).get('all_names', set())
        all_entities.update(entities)
        for e in entities:
            entity_freq[e] += 1

    top_entities = entity_freq.most_common(10)

    candidate_categories = Counter()
    for e in all_entities:
        if e.upper() in INSTITUTION_CATEGORY:
            cat = INSTITUTION_CATEGORY[e.upper()]
            candidate_categories[cat] += 1

    seed_matches = Counter()
    for item in cluster_items:
        text = item.get('body', '') + ' ' + (item.get('title', '') or '')
        for hilo_name in SEED_HILOS:
            if classify_item(text, hilo_name):
                seed_matches[hilo_name] += 1

    return {
        'size': len(cluster_items),
        'entities': all_entities,
        'top_entities': top_entities,
        'candidate_categories': candidate_categories.most_common(5),
        'seed_matches': seed_matches.most_common(5),
        'suggested_name': _suggest_name(cluster_items, all_entities, candidate_categories),
    }


def _suggest_name(cluster_items, all_entities, candidate_categories):
    """Generate a suggested hilo name for a cluster."""
    if candidate_categories:
        return candidate_categories[0][0]

    texts = [it.get('title', '') for it in cluster_items if it.get('title')]
    if texts:
        words = ' '.join(texts).split()
        bigrams = Counter()
        for i in range(len(words) - 1):
            bigrams[f"{words[i]} {words[i+1]}"] += 1
        if bigrams:
            return bigrams.most_common(1)[0][0][:60]

    return "Tema por definir"


# ── Report Generation ─────────────────────────────────────────────────────

def generate_bootstrap_report(
    items, classified, unclassified,
    entity_freq, hilo_counts, clusters,
    cluster_results, singletons, output_dir,
):
    """Generate a detailed bootstrap report."""
    report_path = os.path.join(output_dir, 'bootstrap_report.md')

    coverage = len(classified) / len(items) * 100 if items else 0

    lines = []
    lines.append("# Reporte de Bootstrap de Hilos")
    lines.append("")
    lines.append(f"- **Acta origen:** {items[0].get('file', 'N/A') if items else 'N/A'}")
    lines.append(f"- **Total episodios:** {len(items)}")
    lines.append(f"- **Clasificados:** {len(classified)} ({coverage:.1f}%)")
    lines.append(f"- **No clasificados:** {len(unclassified)}")
    lines.append(f"- **Clusters formados:** {len(clusters)}")
    lines.append(f"- **Singletons:** {len(singletons)}")
    lines.append("")

    lines.append("## Distribucion por Hilo")
    lines.append("")
    lines.append("| Hilo | Episodios | % |")
    lines.append("|------|-----------|---|")
    for hilo_name, count in hilo_counts.most_common():
        pct = count / len(items) * 100
        lines.append(f"| {hilo_name} | {count} | {pct:.1f}% |")
    lines.append("")

    lines.append("## Entidades Principales (Top 20)")
    lines.append("")
    lines.append("| Entidad | Frecuencia |")
    lines.append("|---------|------------|")
    for name, count in entity_freq.most_common(20):
        lines.append(f"| {name} | {count} |")
    lines.append("")

    if cluster_results:
        lines.append("## Clusters Detectados")
        lines.append("")
        for cr in cluster_results:
            lines.append(f"### Cluster {cr['cluster']} ({cr['size']} items)")
            lines.append(f"")
            lines.append(f"- **Nombre sugerido:** {cr['suggested_name']}")
            if cr['top_entities']:
                top_ents = ', '.join(f"{e}({c})" for e, c in cr['top_entities'][:5])
                lines.append(f"- **Entidades:** {top_ents}")
            if cr['candidate_categories']:
                cats = ', '.join(f"{c}({v})" for c, v in cr['candidate_categories'][:3])
                lines.append(f"- **Categorias candidatas:** {cats}")
            if cr['seed_matches']:
                matches = ', '.join(f"{h}({c})" for h, c in cr['seed_matches'][:3])
                lines.append(f"- **Coincidencias semilla:** {matches}")
            lines.append("")

    if singletons:
        lines.append("## Items No Agrupados (Singletons)")
        lines.append("")
        for i in singletons[:20]:
            item = unclassified[i]
            title = item.get('title', 'sin titulo')[:60]
            ents = list(item.get('entities', {}).get('all_names', set()))[:3]
            lines.append(f"- {title} | entidades: {', '.join(ents)}")
        if len(singletons) > 20:
            lines.append(f"- ... y {len(singletons) - 20} mas")
        lines.append("")

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print(f"\n  → Reporte guardado: {report_path}")
    return report_path


# ── Main Orchestrator ─────────────────────────────────────────────────────

def run_bootstrap(
    actas_dir,
    output_dir,
    min_shared=2,
    min_jaccard=0.15,
    verbose=False,
):
    """Run the full bootstrap pipeline."""
    os.makedirs(output_dir, exist_ok=True)

    print("=" * 60)
    print("  PIPELINE ACTAS --- Bootstrap de Hilos")
    print("=" * 60)
    print()

    # Step 1: Parse actas
    print("Parsing actas...")
    items = parse_actas_directory(actas_dir)
    print(f"  -> {len(items)} episodios encontrados en {actas_dir}")
    if not items:
        print("  No se encontraron episodios. Revisa la ruta o el formato.")
        return {'items': [], 'classified': 0, 'unclassified': 0, 'clusters': [], 'report': ''}

    # Step 2: Extract entities
    print("Extrayendo entidades...")
    for item in items:
        text = item.get('body', '') + ' ' + (item.get('title', '') or '')
        item['entities'] = extract_entities(text)
    print("  -> Entidades extraidas")

    entity_freq = build_entity_frequency(items)
    top_global = entity_freq.most_common(20)
    print("  -> Top entidades globales:")
    for name, count in top_global:
        print(f"     {name}: {count}")

    # Step 3: Classify with seed
    print()
    print("Clasificando con taxonomia semilla...")
    for item in items:
        text = item.get('body', '') + ' ' + (item.get('title', '') or '')
        item['seed_hilos'] = classify_with_seed(text)

    classified = [it for it in items if it['seed_hilos']]
    unclassified = [it for it in items if not it['seed_hilos']]
    coverage = len(classified) / len(items) * 100 if items else 0

    print(f"  -> Clasificados: {len(classified)}/{len(items)} ({coverage:.1f}%)")
    print(f"  -> No clasificados: {len(unclassified)}")

    hilo_counts = Counter()
    for item in classified:
        for h in item['seed_hilos']:
            hilo_counts[h] += 1
    print("  -> Distribucion:")
    for hilo_name, count in hilo_counts.most_common():
        print(f"     {hilo_name}: {count}")

    # Step 4: Suggest signal additions
    print()
    print("Senales sugeridas para taxonomia semilla:")
    for hilo_name in sorted(SEED_HILOS.keys()):
        hilo_items = [it for it in classified if hilo_name in it['seed_hilos']]
        if not hilo_items:
            continue
        existing_entities = set(SEED_HILOS[hilo_name].get('entities', []))
        item_entities = set()
        for it in hilo_items:
            item_entities.update(it.get('entities', {}).get('all_names', set()))
        new_entities = item_entities - existing_entities
        if new_entities:
            top_new = sorted(new_entities, key=lambda e: entity_freq[e], reverse=True)[:5]
            print(f"  {hilo_name}: anadir entidades -> {', '.join(top_new)}")

    # Step 5: Cluster unclassified items
    print()
    print("Agrupando no clasificados por co-ocurrencia de entidades...")
    if unclassified:
        clusters = cluster_by_entities(unclassified, min_shared, min_jaccard)
        print(f"  -> {len(clusters)} clusters formados")

        cluster_results = []
        for i, indices in enumerate(clusters):
            cluster_items = [unclassified[j] for j in indices]
            analysis = analyze_cluster(cluster_items)
            cluster_results.append({
                'cluster': i + 1,
                'size': analysis['size'],
                'suggested_name': analysis['suggested_name'],
                'top_entities': analysis['top_entities'],
                'candidate_categories': analysis['candidate_categories'],
                'seed_matches': analysis['seed_matches'],
                'items': [unclassified[j]['id'] for j in indices],
            })

            print(f"  Cluster {i+1} ({analysis['size']} items):")
            print(f"     Nombre sugerido: {analysis['suggested_name']}")
            if analysis['top_entities']:
                ents = ', '.join(f"{e}({c})" for e, c in analysis['top_entities'][:5])
                print(f"     Entidades: {ents}")
            if analysis['seed_matches']:
                hc = [h for h, _ in analysis['seed_matches'][:3]]
                print(f"     Posibles hilos existentes: {', '.join(hc)}")

        clustered_indices = set()
        for indices in clusters:
            clustered_indices.update(indices)
        singletons = [i for i in range(len(unclassified)) if i not in clustered_indices]
        if singletons:
            print(f"  {len(singletons)} items no agrupados (singletons):")
            for i in singletons[:10]:
                item = unclassified[i]
                title = item.get('title', 'sin titulo')[:60]
                ents = list(item.get('entities', {}).get('all_names', set()))[:3]
                print(f"     - {title} | entidades: {', '.join(ents)}")
            if len(singletons) > 10:
                print(f"     ... y {len(singletons) - 10} mas")
    else:
        clusters = []
        cluster_results = []
        singletons = []
        print("  -> No hay items no clasificados.")

    # Step 6: Generate report
    print()
    print("Generando reporte...")
    report_path = generate_bootstrap_report(
        items, classified, unclassified,
        entity_freq, hilo_counts, clusters,
        cluster_results, singletons, output_dir,
    )

    # Step 7: Export JSON summary
    summary = {
        'total_items': len(items),
        'classified': len(classified),
        'unclassified': len(unclassified),
        'coverage_pct': round(coverage, 1),
        'hilo_distribution': dict(hilo_counts.most_common()),
        'clusters': cluster_results,
        'singletons_count': len(singletons),
        'top_entities': [{'name': n, 'count': c} for n, c in top_global],
    }

    summary_path = os.path.join(output_dir, 'bootstrap_summary.json')
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"  -> Resumen guardado: {summary_path}")

    print()
    print("=" * 60)
    print("  Bootstrap completado.")
    print("  Proximo paso: revisa el reporte y genera el enrutamiento con")
    print(f"    python generate_enrutamiento.py --input {output_dir}/bootstrap_summary.json")
    print("=" * 60)

    return summary


# ── CLI ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Bootstrap de hilos para pipeline de actas municipales"
    )
    parser.add_argument(
        '--actas-dir', required=True,
        help='Directorio con actas procesadas (formato Markdown)'
    )
    parser.add_argument(
        '--output', default='./bootstrap',
        help='Directorio de salida (default: ./bootstrap)'
    )
    parser.add_argument(
        '--min-shared', type=int, default=2,
        help='Minimo de entidades compartidas para cluster (default: 2)'
    )
    parser.add_argument(
        '--min-jaccard', type=float, default=0.15,
        help='Minimo indice Jaccard para cluster (default: 0.15)'
    )
    parser.add_argument(
        '--verbose', '-v', action='store_true',
        help='Modo verbose'
    )
    parser.add_argument(
        '--lugares', default='',
        help='Archivo JSON con lugares locales del canton (generado por setup_municipio.py)'
    )

    args = parser.parse_args()

    if not os.path.isdir(args.actas_dir):
        print(f"Error: {args.actas_dir} no es un directorio valido.")
        sys.exit(1)

    if args.lugares:
        if os.path.isfile(args.lugares):
            n = len(load_local_places(args.lugares))
            print(f"Lugares locales cargados: {n}")
        else:
            print(f"Advertencia: no se encontro {args.lugares}")

    run_bootstrap(
        actas_dir=args.actas_dir,
        output_dir=args.output,
        min_shared=args.min_shared,
        min_jaccard=args.min_jaccard,
        verbose=args.verbose,
    )


if __name__ == '__main__':
    main()
