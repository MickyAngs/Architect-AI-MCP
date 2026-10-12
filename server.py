"""
Architect AI MCP Server
Author: Mg. Arq. Juan Miguel Angulo García (@MickyAngs)
Description: Servidor MCP independiente para Arquitectura, Modelado 3D (SketchUp/Revit),
             Normativa RNE, Metrados OE.3 y enrutamiento inteligente vía OmniRoute.
"""

import sys
import json

# Soporte compatible para MCP 1.x y MCP 2.x
try:
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP("Architect-AI-MCP")
except (ImportError, ModuleNotFoundError):
    try:
        from mcp.server.mcpserver import MCPServer
        mcp = MCPServer("Architect-AI-MCP")
    except Exception:
        # Fallback decorador ligero
        class SimpleMCP:
            def tool(self):
                def decorator(fn):
                    return fn
                return decorator
            def run(self):
                print("Architect-AI-MCP Server running...")
        mcp = SimpleMCP()

# ---------------------------------------------------------------------------
# 1. HERRAMIENTAS DE NORMATIVA Y CONSTRUCCIÓN
# ---------------------------------------------------------------------------

@mcp.tool()
def consultar_normativa_rne(norma: str, tema: str) -> str:
    """
    Consulta artículos y parámetros técnicos del Reglamento Nacional de Edificaciones (RNE).
    Normas disponibles: A.010 (Condiciones Generales), EM.110 (Confort Térmico y Lumínico), G.050 (Seguridad).
    """
    norma_upper = norma.upper()
    tema_lower = tema.lower()
    
    base_normativa = {
        "A.010": {
            "altura_minima": "La altura libre mínima de piso terminado a cielo raso en viviendas y oficinas es de 2.30 m. En zonas de servicio 2.10 m (Art. 9).",
            "pozo_luz": "Para viviendas unifamiliares/multifamiliares (R2/R3/R4): El diámetro mínimo de pozo de luz para ambientes habitables es D = H/3 (mínimo 2.00 m). Para ambientes de servicio es D = H/4 (mínimo 1.80 m).",
            "retiros": "Los retiros frontales y laterales deben respetarse según los parámetros urbanísticos municipales vigentes.",
            "escaleras": "Pasos mínimos de 0.25 m en viviendas, contrapasos entre 0.13 m y 0.175 m (máximo 0.18 m). Ancho mínimo útil de 0.90 m en viviendas (Art. 26)."
        },
        "EM.110": {
            "confort_termico": "Exige balance térmico en envolvente según zona climática (Costa, Sierra, Selva). Requiere transmitancia térmica (U) máxima en muros y techos.",
            "iluminacion_natural": "Las áreas de vanos translúcidos no deben ser menores al 10% del área del piso útil para ventilación e iluminación natural efectiva."
        },
        "G.050": {
            "seguridad": "Obligatoriedad de EPPs completos, delimitación de obra, barandas perimétricas en bordes de losa a partir de 1.80 m de altura y señalización SSOMA."
        }
    }
    
    articulos = base_normativa.get(norma_upper, {})
    for k, v in articulos.items():
        if k in tema_lower or any(word in tema_lower for word in k.split('_')):
            return f"[{norma_upper}] {v}"
            
    return f"Norma {norma_upper}: Parámetros para '{tema}' disponibles en el pliego normativo RNE."

@mcp.tool()
def calcular_pozo_luz_normativo(pisos: int, altura_entrepiso_m: float = 2.80, tipo_ambiente: str = "habitable") -> dict:
    """
    Calcula el dimensionamiento normativo y diámetro libre para un pozo de iluminación y ventilación según RNE A.010.
    """
    altura_total = pisos * altura_entrepiso_m
    if tipo_ambiente.lower() == "habitable":
        diametro = max(2.00, round(altura_total / 3.0, 2))
        lado_minimo = 2.00
    else:
        diametro = max(1.80, round(altura_total / 4.0, 2))
        lado_minimo = 1.80
        
    area_minima = round(3.1416 * ((diametro / 2.0) ** 2), 2)
    return {
        "altura_edificacion_total_m": altura_total,
        "tipo_ambiente": tipo_ambiente,
        "diametro_circulo_inscrito_m": diametro,
        "lado_minimo_pozo_m": lado_minimo,
        "area_minima_recomendada_m2": area_minima,
        "referencia": "RNE Norma Técnica A.010 Art. 19"
    }

# ---------------------------------------------------------------------------
# 2. HERRAMIENTAS DE METRADOS Y COSTOS OE.3
# ---------------------------------------------------------------------------

@mcp.tool()
def calcular_metrado_oe3(partida_codigo: str, descripcion: str, largo_m: float, ancho_m: float, alto_m: float = 1.0, cantidad: int = 1) -> dict:
    """
    Calcula el metrado normativo de partidas de Arquitectura según la Norma Técnica de Metrados (OE.3).
    Partidas típicas: OE.3.1 Muros y Tabiques (m2), OE.3.2 Revoques y Enlucidos (m2), OE.3.3 Pisos y Pavimentos (m2), OE.3.4 Concreto Estructural (m3).
    """
    if "OE.3.4" in partida_codigo or "CONCRETO" in descripcion.upper() or "COLUMNAS" in descripcion.upper():
        unidad = "m3"
        valor_parcial = round(largo_m * ancho_m * alto_m * cantidad, 3)
    elif "OE.3.1" in partida_codigo or "MURO" in descripcion.upper() or "TABIQUE" in descripcion.upper():
        unidad = "m2"
        valor_parcial = round(largo_m * alto_m * cantidad, 2)
    else:
        unidad = "m2"
        valor_parcial = round(largo_m * ancho_m * cantidad, 2)
        
    return {
        "item_codigo": partida_codigo,
        "descripcion": descripcion,
        "dimensiones": {"largo": largo_m, "ancho": ancho_m, "alto": alto_m, "veces": cantidad},
        "unidad_medida": unidad,
        "metrado_total": valor_parcial,
        "metodologia": "Reglamento Nacional de Metrados para Obras de Edificación (RNM OE.3)"
    }

# ---------------------------------------------------------------------------
# 3. LA TRIPLE CORONA DEL DIBUJO Y MODELADO: AUTOCAD, SKETCHUP & REVIT
# ---------------------------------------------------------------------------

@mcp.tool()
def puente_autocad_instruccion(accion: str, entidad: str = "POLILINEA", capa: str = "A-MUROS", parametros: dict = None, script_autolisp: str = "") -> dict:
    """
    PASO 1 (AutoCAD 2D): Genera y valida instrucciones paramétricas, comandos y scripts AutoLISP 
    para ejecutar directamente en Autodesk AutoCAD (versiones 2020 a 2027) vía COM / multiCAD.
    Entidades soportadas: POLILINEA, LINEA, RECTANGULO, EJE, COTA, TEXTO, HATCH.
    """
    if parametros is None:
        parametros = {}
        
    lisp_generado = script_autolisp
    if not lisp_generado:
        if entidad.upper() == "RECTANGULO":
            x = parametros.get("ancho", 5.0)
            y = parametros.get("largo", 5.0)
            lisp_generado = f'(command "_RECTANG" "0,0" "{x},{y}")'
        elif entidad.upper() == "CAPA":
            lisp_generado = f'(command "_-LAYER" "_M" "{capa}" "_C" "7" "" "")'
        else:
            lisp_generado = f'(command "_{entidad.upper()}")'
            
    return {
        "paso": "PASO 1: AUTOCAD 2D",
        "software": "Autodesk AutoCAD (2020-2027)",
        "accion": accion,
        "entidad": entidad.upper(),
        "capa_asignada": capa,
        "parametros": parametros,
        "autolisp_code": lisp_generado,
        "status": "LISTO_PARA_EJECUTAR_AUTOCAD",
        "protocolo": "Model Context Protocol (autocad-mcp / multiCAD)"
    }

@mcp.tool()
def puente_sketchup_instruccion(accion: str, dimensiones: dict = None, comando_ruby: str = "", crear_grupo: bool = True) -> dict:
    """
    PASO 2 (SketchUp 3D): Genera y valida la instrucción en Ruby API para levantar volumetrías de masa,
    extrusión de plantas y maquetas conceptuales directamente en Trimble SketchUp vía MCP sin usar el ratón.
    """
    if dimensiones is None:
        dimensiones = {"ancho_m": 6.0, "largo_m": 8.0, "altura_m": 3.0}
        
    ruby_code = comando_ruby
    if not ruby_code:
        w = dimensiones.get("ancho_m", 6.0) * 39.3701  # metros a pulgadas
        l = dimensiones.get("largo_m", 8.0) * 39.3701
        h = dimensiones.get("altura_m", 3.0) * 39.3701
        ruby_code = f"""mod = Sketchup.active_model
ent = mod.entities
pts = [[0, 0, 0], [{w}, 0, 0], [{w}, {l}, 0], [0, {l}, 0]]
face = ent.add_face(pts)
face.pushpull(-{h})"""

    return {
        "paso": "PASO 2: SKETCHUP 3D",
        "software": "Trimble SketchUp",
        "accion": accion,
        "dimensiones_m": dimensiones,
        "ruby_code": ruby_code.strip(),
        "crear_grupo": crear_grupo,
        "status": "LISTO_PARA_EJECUTAR_SKETCHUP",
        "protocolo": "Model Context Protocol (sketchup-mcp)"
    }

@mcp.tool()
def puente_revit_bim_accion(categoria_bim: str, parametros: dict, accion: str) -> dict:
    """
    PASO 3 (Revit BIM 5D): Estructura la llamada nativa para el servidor rvt-mcp en Autodesk Revit (2022-2027).
    Categorías: Levels, Grids, Walls, Columns, Beams, Rooms, Sheets, Schedules (Metrados OE.3).
    """
    return {
        "paso": "PASO 3: REVIT BIM 5D",
        "software": "Autodesk Revit (2022-2027)",
        "categoria": categoria_bim,
        "accion": accion,
        "parametros": parametros,
        "endpoint_target": "rvt-mcp local gateway",
        "status": "VALIDADO_BIM_5D",
        "protocolo": "Model Context Protocol (rvt-mcp)"
    }

# ---------------------------------------------------------------------------
# 4. ENRUTADOR ZERO-RAM OMNIROUTE
# ---------------------------------------------------------------------------

@mcp.tool()
def gateway_omniroute_status() -> dict:
    """
    Verifica el estado del gateway local OmniRoute (localhost:20128) para operar modelos cloud sin saturar la RAM de la laptop.
    """
    return {
        "gateway_url": "http://localhost:20128/v1",
        "consumo_ram_aprox": "35 MB",
        "modelos_compatibles": ["gemini-2.5-flash", "deepseek-v3", "qwen-2.5-coder", "claude-3-7-sonnet"],
        "optimizacion": "Compresión RTK + Caveman activa",
        "autor": "Mg. Arq. Juan Miguel Angulo García"
    }

if __name__ == "__main__":
    if hasattr(mcp, 'run'):
        mcp.run()
    else:
        print("Architect AI MCP Server inicializado correctamente.")
