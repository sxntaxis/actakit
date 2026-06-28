#!/usr/bin/env python3
"""
Entity extraction module for Costa Rican municipal actas.

Extracts named entities from acta text: institutions, laws, official codes,
places, roles, and monetary amounts. Used by bootstrap_hilos.py for
automatic taxonomy generation and by the processing pipeline for signal
detection.
"""

import json
import os
import re
from typing import Dict, List, Set, Tuple


# Accent normalization map: accented chars -> regex class matching both
ACCENT_MAP = {
    'á': '[aá]', 'é': '[eé]', 'í': '[ií]', 'ó': '[oó]', 'ú': '[uú]', 'ü': '[uü]',
    'Á': '[AÁ]', 'É': '[EÉ]', 'Í': '[IÍ]', 'Ó': '[OÓ]', 'Ú': '[UÚ]', 'Ü': '[UÜ]',
    'ñ': '[nñ]', 'Ñ': '[NÑ]',
}


def accent_insensitive_pattern(text: str) -> str:
    """
    Convert a literal string to a regex pattern that matches both
    accented and unaccented versions of vowels and ñ.
    """
    result = []
    for ch in text:
        result.append(ACCENT_MAP.get(ch, re.escape(ch)))
    return ''.join(result)


# ── Costa Rican Institutions ──────────────────────────────────────────────

INSTITUTIONS = {
    # Oversight
    "CGR": "Contraloría General de la República",
    "DFOE": "División de Fiscalización Operativa y Evaluativa",
    "PGR": "Procuraduría General de la República",
    "TSE": "Tribunal Supremo de Elecciones",
    "SALA IV": "Sala Constitucional",
    "SALA IV CONSTITUCIONAL": "Sala Constitucional",
    "DEFENSORÍA DE LOS HABITANTES": "Defensoría de los Habitantes",

    # Economy / Commerce
    "MH": "Ministerio de Hacienda",
    "MEIC": "Ministerio de Economía Industria y Comercio",
    "INA": "Instituto Nacional de Aprendizaje",
    "ICT": "Instituto Costarricense de Turismo",
    "INDER": "Instituto de Desarrollo Rural",

    # Transport / Infrastructure
    "MOPT": "Ministerio de Obras Públicas y Transportes",
    "CONAVI": "Consejo Nacional de Vialidad",
    "CTP": "Consejo de Transporte Público",
    "ARESEP": "Autoridad Reguladora de los Servicios Públicos",
    "INCOP": "Instituto Costarricense de Puertos del Pacífico",
    "JAPDEVA": "Junta de Administración Portuaria y de Desarrollo Económico de la Vertiente Atlántica",
    "ICE": "Instituto Costarricense de Electricidad",
    "INCOFER": "Instituto Costarricense de Ferrocarriles",

    # Health
    "CCSS": "Caja Costarricense de Seguro Social",
    "MINSA": "Ministerio de Salud",
    "EBAIS": "Equipo Básico de Atención Integral en Salud",
    "CAP": "Clínica de Atención Primaria",
    "CRUZ ROJA": "Cruz Roja Costarricense",
    "IAFA": "Instituto sobre Alcoholismo y Farmacodependencia",
    "CONAPAM": "Consejo Nacional de la Persona Adulta Mayor",

    # Water
    "AYA": "Instituto Costarricense de Acueductos y Alcantarillados",
    "ASADA": "Asociación Administradora de Sistemas de Acueductos y Alcantarillados",
    "ASADAS": "Asociación Administradora de Sistemas de Acueductos y Alcantarillados",
    "SENARA": "Servicio Nacional de Aguas Subterráneas, Riego y Avenamiento",

    # Environment / Territory
    "MINAE": "Ministerio de Ambiente y Energía",
    "SETENA": "Secretaría Técnica Nacional Ambiental",
    "SINAC": "Sistema Nacional de Áreas de Conservación",
    "ACOPAC": "Área de Conservación Pacífico Central",
    "DIGECA": "Dirección de Gestión de Calidad Ambiental",
    "MIVAH": "Ministerio de Vivienda y Asentamientos Humanos",
    "INVU": "Instituto Nacional de Vivienda y Urbanismo",
    "BANHVI": "Banco Hipotecario de la Vivienda",
    "CNE": "Comisión Nacional de Emergencias",
    "SENASA": "Servicio Nacional de Salud Animal",
    "MAG": "Ministerio de Agricultura y Ganadería",

    # Social
    "IMAS": "Instituto Mixto de Ayuda Social",
    "PANI": "Patronato Nacional de la Infancia",
    "INAMU": "Instituto Nacional de las Mujeres",
    "CONAPDIS": "Consejo Nacional de Personas con Discapacidad",
    "JPS": "Junta de Protección Social",
    "DINADECO": "Dirección Nacional de Desarrollo de la Comunidad",
    "UNGL": "Unión Nacional de Gobiernos Locales",
    "IFAM": "Instituto de Fomento y Asesoría Municipal",

    # Education / Culture
    "MEP": "Ministerio de Educación Pública",
    "MCJ": "Ministerio de Cultura y Juventud",
    "CPJ": "Consejo de la Persona Joven",
    "CCPJ": "Comité Cantonal de la Persona Joven",
    "UNED": "Universidad Estatal a Distancia",
    # UNA excluded: too short, false-positives with Spanish article.
    # Covered via full name "Universidad Nacional" in INSTITUTION_PATTERNS.
    "TEC": "Instituto Tecnológico de Costa Rica",
    "ITCR": "Instituto Tecnológico de Costa Rica",
    "UCR": "Universidad de Costa Rica",

    # Other
    "MICITT": "Ministerio de Ciencia, Innovación, Tecnología y Telecomunicaciones",
    "OFIM": "Oficina de la Mujer",
    "COMAD": "Comité Municipal de Accesibilidad y Discapacidad",
    "COPROCOM": "Comisión para Promover la Competencia",
    "SUTEL": "Superintendencia de Telecomunicaciones",
    "INFOCOOP": "Instituto Nacional de Fomento Cooperativo",
    "ACAM": "Asociación de Compositores y Autores Musicales",
}

# Multi-word institution patterns (for regex matching)
INSTITUTION_PATTERNS = [
    "Contraloría General de la República",
    "Procuraduría General de la República",
    "Sala Constitucional",
    "Ministerio de Hacienda",
    "Ministerio de Economía",
    "Ministerio de Obras Públicas",
    "Ministerio de Salud",
    "Ministerio de Ambiente",
    "Ministerio de Educación Pública",
    "Ministerio de Cultura y Juventud",
    "Ministerio de Vivienda",
    "Ministerio de Agricultura",
    "Ministerio de Ciencia",
    "Caja Costarricense de Seguro Social",
    "Caja Costarricense del Seguro Social",
    "Instituto Costarricense de Acueductos",
    "Instituto Costarricense de Electricidad",
    "Instituto Costarricense de Puertos",
    "Instituto Costarricense de Turismo",
    "Instituto Nacional de Aprendizaje",
    "Instituto Nacional de Vivienda",
    "Instituto Mixto de Ayuda Social",
    "Instituto Nacional de las Mujeres",
    "Instituto de Fomento y Asesoría Municipal",
    "Instituto de Desarrollo Rural",
    "Consejo Nacional de Vialidad",
    "Consejo de Transporte Público",
    "Consejo Nacional de la Persona Joven",
    "Consejo Nacional de Emergencias",
    "Comisión Nacional de Emergencias",
    "Patronato Nacional de la Infancia",
    "Banco Hipotecario de la Vivienda",
    "Autoridad Reguladora de los Servicios Públicos",
    "Comité Cantonal de la Persona Joven",
    "Asociación de Desarrollo Integral",
    "Junta de Educación",
    "Junta Administrativa",
    "Fuerza Pública",
    "Policía Municipal",
    "Cruz Roja",
]

# Patterns by thematic category for entity→hilo mapping
INSTITUTION_CATEGORY = {
    # Oversight → Auditoria / Transparencia
    "CGR": "Auditoría y Control Interno",
    "DFOE": "Auditoría y Control Interno",
    "PGR": "Concejo Municipal y Funcionamiento",
    "TSE": "Concejo Municipal y Funcionamiento",

    # Economy
    "MEIC": "Economía Local, Comercio, Turismo y Emprendimientos",
    "INA": "Economía Local, Comercio, Turismo y Emprendimientos",
    "ICT": "Economía Local, Comercio, Turismo y Emprendimientos",
    "INDER": "Economía Local, Comercio, Turismo y Emprendimientos",

    # Transport
    "MOPT": "Movilidad, Red Vial y Transporte Público",
    "CONAVI": "Movilidad, Red Vial y Transporte Público",
    "CTP": "Movilidad, Red Vial y Transporte Público",
    "ARESEP": "Agua Potable, AyA y ASADAS",
    "INCOP": "Economía Local, Comercio, Turismo y Emprendimientos",
    "ICE": "Infraestructura Comunal y Espacios Públicos",
    "INCOFER": "Movilidad, Red Vial y Transporte Público",

    # Health
    "CCSS": "Salud Pública, CCSS, EBAIS y Campañas",
    "MINSA": "Salud Pública, CCSS, EBAIS y Campañas",
    "MS": "Salud Pública, CCSS, EBAIS y Campañas",
    "EBAIS": "Salud Pública, CCSS, EBAIS y Campañas",
    "CAP": "Salud Pública, CCSS, EBAIS y Campañas",
    "IAFA": "Personas en Situación de Calle y Adicciones",
    "CONAPAM": "Cuidados, Niñez y Personas Adultas Mayores",

    # Water
    "AYA": "Agua Potable, AyA y ASADAS",
    "ASADA": "Agua Potable, AyA y ASADAS",
    "ASADAS": "Agua Potable, AyA y ASADAS",
    "SENARA": "Agua Potable, AyA y ASADAS",

    # Environment
    "MINAE": "Ambiente, Conservación y Afectaciones",
    "SETENA": "Ambiente, Conservación y Afectaciones",
    "SINAC": "Ambiente, Conservación y Afectaciones",
    "DIGECA": "Ambiente, Conservación y Afectaciones",
    "SENASA": "Ambiente, Conservación y Afectaciones",
    "MAG": "Economía Local, Comercio, Turismo y Emprendimientos",

    # Territory
    "MIVAH": "Vivienda, Asentamientos y Urbanizaciones",
    "INVU": "Ordenamiento Territorial y Plan Regulador",
    "BANHVI": "Vivienda, Asentamientos y Urbanizaciones",
    "CNE": "Gestión del Riesgo, Emergencias y Aguas Pluviales",

    # Social
    "IMAS": "Cuidados, Niñez y Personas Adultas Mayores",
    "PANI": "Cuidados, Niñez y Personas Adultas Mayores",
    "INAMU": "Mujeres y Política de Género",
    "CONAPDIS": "Accesibilidad y Discapacidad",
    "JPS": "Salud Pública, CCSS, EBAIS y Campañas",
    "DINADECO": "Concejo Municipal y Funcionamiento",
    "UNGL": "Concejo Municipal y Funcionamiento",
    "IFAM": "Presupuesto, Finanzas, Tarifas y Planificación",
    "OFIM": "Mujeres y Política de Género",
    "COMAD": "Accesibilidad y Discapacidad",
    "COPROCOM": "Contratación, Activos y Mercado Municipal",

    # Education
    "MEP": "Educación, Becas e Infraestructura Educativa",
    "MCJ": "Cultura, Identidad, Memoria y Patrimonio",
    "CPJ": "Juventudes",
    "CCPJ": "Juventudes",
}


# ── Laws ──────────────────────────────────────────────────────────────────

LAW_PATTERNS = [
    (r'Ley\s+(?:N(?:o\.\s*|\.?\s*°?\s*|[uú]mero\s+))?(\d{3,5}(?:\.\d{1,4})?)', 'Ley N° {n}'),
    (r'expediente\s+(?:N\.?°?\s*)?(\d{2,3}\.\d{3})', 'Expediente {n}'),
]

LAW_CATEGORY = {
    "7794": "Concejo Municipal y Funcionamiento",
    "8422": "Concejo Municipal y Funcionamiento",
    "4240": "Ordenamiento Territorial y Plan Regulador",
    "8220": "Concejo Municipal y Funcionamiento",
    "8461": "Presupuesto, Finanzas, Tarifas y Planificación",
    "7755": "Presupuesto, Finanzas, Tarifas y Planificación",
    "7509": "Presupuesto, Finanzas, Tarifas y Planificación",
    "7600": "Accesibilidad y Discapacidad",
    "8261": "Juventudes",
    "9095": "Mujeres y Política de Género",
    "10235": "Mujeres y Política de Género",
    "10009": "Personas en Situación de Calle y Adicciones",
    "10236": "Vivienda, Asentamientos y Urbanizaciones",
    "9047": "Seguridad Ciudadana, Policía Municipal y Convivencia",
    "8892": "Movilidad, Red Vial y Transporte Público",
    "9976": "Movilidad, Red Vial y Transporte Público",
    "833": "Ordenamiento Territorial y Plan Regulador",
}


# ── Official codes ─────────────────────────────────────────────────────────

OFICIO_PATTERN = re.compile(
    r'(?:oficio|nota|notas?)\s+(?:N\.?°?\s*)?'
    r'([A-Z]{2,6}(?:-[A-Z]{1,6}){0,3}-\d{2,6}-\d{4})',
    re.IGNORECASE
)

SICOP_PATTERN = re.compile(
    r'(\d{4}[A-Z]{2,3}-?\d{6}-?\d{10})'
)

EXPEDIENTE_PATTERN = re.compile(
    r'[Ee]xpediente\s+(?:N\.?°?\s*)?(\d{2,3}\.\d{3})'
)

ACTA_REF_PATTERN = re.compile(
    r'Acta\s+N\.?°?\s*(\d{1,3})'
)


# ── Places ────────────────────────────────────────────────────────────────

# Common Costa Rican place patterns
PLACE_PATTERNS = [
    (r'[Dd]istrito\s+de\s+((?:[A-ZÁÉÍÓÚÜÑ][a-záéíóúñü]+(?:\s+(?:de|del|la|los|las|y|e)\s+)?[A-ZÁÉÍÓÚÜÑ][a-záéíóúñü]+){1,3})', 'Distrito {n}'),
    (r'[Cc]antón\s+de\s+((?:[A-ZÁÉÍÓÚÜÑ][a-záéíóúñü]+(?:\s+(?:de|del|la|los|las|y|e)\s+)?[A-ZÁÉÍÓÚÜÑ][a-záéíóúñü]+){1,3})', 'Cantón {n}'),
    (r'[Pp]rovincia\s+de\s+((?:[A-ZÁÉÍÓÚÜÑ][a-záéíóúñü]+(?:\s+(?:de|del|la|los|las|y|e)\s+)?[A-ZÁÉÍÓÚÜÑ][a-záéíóúñü]+){1,3})', '{n}'),
    (r'[Rr]uta\s+(\d{2,4})', 'Ruta {n}'),
    (r'\b[Rr][íi]o\s+((?:[A-ZÁÉÍÓÚÜÑ][a-záéíóúñü]+(?:\s+(?:de|del|la|los|las|y|e)\s+)?[A-ZÁÉÍÓÚÜÑ][a-záéíóúñü]+){1,3})', 'Río {n}'),
]

# Known district names in Costa Rica (most common)
KNOWN_DISTRICTS = {
    "Primero", "Segundo", "Tercero", "Cuarto", "Quinto",
    "Central", "San José", "Alajuela", "Cartago", "Heredia",
    "Guanacaste", "Puntarenas", "Limón",
    "San Francisco", "San Rafael", "San Isidro", "San Juan",
    "San Miguel", "San Pablo", "San Pedro", "San Antonio",
    "San Jerónimo", "San José de la Montaña",
    # Canton names
    "San José", "Escazú", "Desamparados", "Puriscal",
    "Tarrazú", "Aserrí", "Mora", "Goicoechea",
    "Santa Ana", "Alajuelita", "Coronado", "Acosta",
    "Tibás", "Moravia", "Montes de Oca", "Turrubares",
    "Dota", "Curridabat", "Pérez Zeledón", "León Cortés",
    "Alajuela", "San Ramón", "Grecia", "San Mateo",
    "Atenas", "Naranjo", "Palmares", "Poás",
    "Orotina", "San Carlos", "Zarcero", "Sarchí",
    "Upala", "Los Chiles", "Guatuso", "Río Cuarto",
    "Cartago", "Paraíso", "La Unión", "Jiménez",
    "Turrialba", "Alvarado", "Oreamuno", "El Guarco",
    "Heredia", "Barva", "Santo Domingo", "Santa Bárbara",
    "San Rafael", "San Isidro", "Belén", "Flores",
    "San Pablo", "Sarapiquí",
    "Liberia", "Nicoya", "Santa Cruz", "Bagaces",
    "Carrillo", "Cañas", "Abangares", "Tilarán",
    "Nandayure", "La Cruz", "Hojancha",
    "Puntarenas", "Esparza", "Buenos Aires", "Montes de Oro",
    "Osa", "Quepos", "Golfito", "Coto Brus",
    "Parrita", "Corredores", "Garabito", "Monteverde",
    "Limón", "Pococí", "Siquirres", "Talamanca",
    "Matina", "Guácimo",
}

# Local places loaded from external config (set via load_local_places())
LOCAL_PLACES: Set[str] = set()


def load_local_places(path: str = '') -> Set[str]:
    """Load local place names from a JSON file.

    Expected format: {"lugares": ["Nombre1", "Nombre2", ...]}
    These are added to the entity extraction patterns at runtime.
    """
    global LOCAL_PLACES
    if not path or not os.path.isfile(path):
        return set()
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    places = set(data.get('lugares', []))
    LOCAL_PLACES = places
    _rebuild_patterns()
    return places


def _rebuild_patterns():
    """Rebuild ALL_ENTITY_PATTERNS after loading local places."""
    global ALL_ENTITY_PATTERNS
    ALL_ENTITY_PATTERNS.clear()

    for acr in sorted(INSTITUTIONS.keys(), key=len, reverse=True):
        pattern = re.compile(r'\b' + re.escape(acr) + r'\b', re.IGNORECASE)
        ALL_ENTITY_PATTERNS.append(('institution', pattern, acr))

    for name in sorted(INSTITUTION_PATTERNS, key=len, reverse=True):
        pattern = re.compile(accent_insensitive_pattern(name), re.IGNORECASE)
        ALL_ENTITY_PATTERNS.append(('institution', pattern, name))

    for pat, template in LAW_PATTERNS:
        compiled = re.compile(pat, re.IGNORECASE)
        ALL_ENTITY_PATTERNS.append(('law', compiled, template))

    for pat, template in PLACE_PATTERNS:
        compiled = re.compile(pat, re.IGNORECASE)
        ALL_ENTITY_PATTERNS.append(('place', compiled, template))

    for dist in KNOWN_DISTRICTS:
        pattern = re.compile(r'\b' + re.escape(dist) + r'\b')
        ALL_ENTITY_PATTERNS.append(('place', pattern, dist))

    for place in LOCAL_PLACES:
        pattern = re.compile(r'\b' + re.escape(place) + r'\b')
        ALL_ENTITY_PATTERNS.append(('place_specific', pattern, place))

    for role in ROLE_PATTERNS:
        compiled = re.compile(role, re.IGNORECASE)
        ALL_ENTITY_PATTERNS.append(('role', compiled, role[:30]))


# ── Roles ─────────────────────────────────────────────────────────────────

ROLE_PATTERNS = [
    r'regidor[a]?\s+(propietario|suplente)?',
    r's[ií]ndico[a]?\s+(propietario|suplente)?',
    r'alcalde(?:\s+municipal)?',
    r'alcaldesa(?:\s+municipal)?',
    r'presidente\s+municipal',
    r'presidenta\s+municipal',
    r'vicepresident[ea]\s+municipal',
    r'gestor\s+(j[uú]ridico|administrativo)',
    r'auditor(?:a)?\s+interno',
    r'concejal[a]?\s+de\s+distrito',
    r'secretario[a]?\s+municipal',
    r'tesorero[a]?\s+municipal',
]

ROLE_CATEGORY = {
    "regidor": "Concejo Municipal y Funcionamiento",
    "síndico": "Concejo Municipal y Funcionamiento",
    "alcalde": "Concejo Municipal y Funcionamiento",
    "alcaldesa": "Concejo Municipal y Funcionamiento",
    "presidente municipal": "Concejo Municipal y Funcionamiento",
    "gestor jurídico": "Concejo Municipal y Funcionamiento",
    "auditor interno": "Auditoría y Control Interno",
    "concejal de distrito": "Concejo Municipal y Funcionamiento",
}


# ── Amounts ────────────────────────────────────────────────────────────────

MONTO_PATTERN = re.compile(
    r'¢\s*([\d]{1,3}(?:\.\d{3})*(?:,\d{2})?)'
)

DOLAR_PATTERN = re.compile(
    r'\$\s*([\d]{1,3}(?:,\d{3})*(?:\.\d{2})?)'
)


# ── Compile all regexes ───────────────────────────────────────────────────

ALL_ENTITY_PATTERNS: List[Tuple[str, re.Pattern, str]] = []

_rebuild_patterns()


# ── Extraction functions ──────────────────────────────────────────────────

def extract_entities(text: str) -> Dict[str, Set[str]]:
    """
    Extract all entities from a text fragment.
    
    Returns dict with keys: 'institutions', 'laws', 'places', 'roles',
    'oficios', 'expedientes', 'montos', 'all' (flattened set).
    """
    result = {
        'institutions': set(),
        'laws': set(),
        'places': set(),
        'roles': set(),
        'oficios': set(),
        'expedientes': set(),
        'montos': set(),
        'all_names': set(),  # human-readable names
    }
    
    if not text:
        return result
    
    # Match all entity patterns
    for etype, pattern, template in ALL_ENTITY_PATTERNS:
        for match in pattern.finditer(text):
            value = match.group(0).strip()
            if etype == 'institution':
                result['institutions'].add(value)
                result['all_names'].add(value)
            elif etype == 'law':
                law_key = f"Ley N° {match.group(1)}" if '{n}' in template else value
                result['laws'].add(law_key)
                result['all_names'].add(law_key)
            elif etype == 'place' or etype == 'place_specific':
                result['places'].add(value)
                result['all_names'].add(value)
            elif etype == 'role':
                result['roles'].add(value)
                result['all_names'].add(value)
    
    # Oficio codes
    for match in OFICIO_PATTERN.finditer(text):
        code = match.group(1).upper()
        result['oficios'].add(code)
        result['all_names'].add(f"Oficio {code}")
    
    # SICOP codes
    for match in SICOP_PATTERN.finditer(text):
        code = match.group(1)
        result['oficios'].add(code)
        result['all_names'].add(f"SICOP {code}")
    
    # Expediente codes
    for match in EXPEDIENTE_PATTERN.finditer(text):
        code = match.group(1)
        result['expedientes'].add(code)
        result['all_names'].add(f"Expediente {code}")
    
    # Monetary amounts
    for match in MONTO_PATTERN.finditer(text):
        result['montos'].add(f"¢{match.group(1)}")
    
    for match in DOLAR_PATTERN.finditer(text):
        result['montos'].add(f"${match.group(1)}")
    
    return result


def extract_entities_from_items(items: List[Dict]) -> List[Dict]:
    """Add entities to each item dict in-place, returning the list."""
    for item in items:
        text = item.get('body', '') or item.get('text', '') or ''
        item['entities'] = extract_entities(text)
    return items


def entity_to_category(entity_name: str) -> str:
    """Map a single entity name to a canonical hilo category."""
    ent_upper = entity_name.upper().strip()
    
    if ent_upper in INSTITUTION_CATEGORY:
        return INSTITUTION_CATEGORY[ent_upper]
    
    if ent_upper.startswith('LEY N°'):
        num = ent_upper.replace('LEY N° ', '')
        if num in LAW_CATEGORY:
            return LAW_CATEGORY[num]
    
    return ''


def infer_roles_from_text(text: str) -> List[str]:
    """Extract role mentions from text."""
    roles = []
    for pattern_str in ROLE_PATTERNS:
        if re.search(pattern_str, text, re.IGNORECASE):
            roles.append(pattern_str[:20])
    return roles


def extract_all(text: str) -> Dict[str, Set[str]]:
    """Convenience: return just the 'all' set."""
    return extract_entities(text)['all_names']


# ── Utility ────────────────────────────────────────────────────────────────

def build_entity_frequency(items: List[Dict]) -> Dict[str, int]:
    """Count how many items contain each entity."""
    freq = {}
    for item in items:
        entities = item.get('entities', {}).get('all_names', set())
        for e in entities:
            freq[e] = freq.get(e, 0) + 1
    return freq


def build_item_entity_matrix(items: List[Dict]) -> Tuple[List[str], List[str], List[List[int]]]:
    """
    Build binary matrix: items × entities.
    Returns (item_ids, entity_names, matrix).
    """
    all_entities = set()
    for item in items:
        all_entities.update(item.get('entities', {}).get('all_names', set()))
    
    entity_list = sorted(all_entities)
    item_ids = []
    matrix = []
    
    for item in items:
        item_ids.append(item.get('id', ''))
        item_entities = item.get('entities', {}).get('all_names', set())
        row = [1 if e in item_entities else 0 for e in entity_list]
        matrix.append(row)
    
    return item_ids, entity_list, matrix


def jaccard_similarity(set1: Set, set2: Set) -> float:
    """Jaccard similarity between two sets."""
    if not set1 and not set2:
        return 0.0
    intersection = set1 & set2
    union = set1 | set2
    return len(intersection) / len(union)


def entity_overlap(set1: Set, set2: Set) -> int:
    """Count shared entities."""
    return len(set1 & set2)
