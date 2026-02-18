from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import anthropic
import os
import sqlite3
from datetime import datetime
import json

app = Flask(__name__, static_folder='.')
CORS(app)

# API Key desde variable de entorno (seguro)
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

# Inicializar base de datos
def init_db():
    conn = sqlite3.connect('clasificaciones.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto TEXT NOT NULL,
            fabricante TEXT,
            categoria_salcobrand TEXT,
            tipo_envase TEXT,
            tiene_envase_secundario TEXT,
            razonamiento TEXT,
            riesgo_merma TEXT,
            fuente_web TEXT,
            fecha_clasificacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            usuario TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/api/clasificar', methods=['POST'])
def clasificar():
    try:
        data = request.json
        producto = data.get('producto', '')
        fabricante = data.get('fabricante', '')
        
        if not producto:
            return jsonify({'error': 'Producto requerido'}), 400
        
        # Llamar a Anthropic API
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        
        prompt = f"""Clasifica este producto para Salcobrand: "{producto}" {f'Fabricante: {fabricante}' if fabricante else ''}

**PASO 1: BÚSQUEDA WEB (OBLIGATORIO)**
Busca el producto en la web para obtener:
- Imágenes del producto
- Tipo de envase (roll-on, barra, aerosol, líquido, etc.)
- Si viene en caja (envase secundario)
- Precio y marca

**PASO 2: CLASIFICAR SEGÚN REGLAS**

Categorías:
- CosMe: Líquidos/cremas en envase primario (shampoos, desodorantes roll-on, desodorantes barra)
- CosCa: Productos en caja/envase secundario (líneas premium, dermatológicos)
- CosPe: Pequeños rígidos resistentes (cepillos, labiales, maquillaje)
- DumMa: Bolsas frágiles (pañales, toallas higiénicas)
- InFla: Perfumes, colonias, aerosoles/spray

CRÍTICO:
- Desodorante ROLL-ON → CosMe
- Desodorante BARRA → CosMe
- Desodorante SPRAY/AEROSOL → InFla
- TODO perfume/colonia → InFla
- Productos dermatológicos en caja (ISDIN, La Roche-Posay, Eucerin, Bioderma, Vichy, Cetaphil) → CosCa

Responde SOLO JSON:
{{
  "categoria_salcobrand": "CosMe|CosCa|CosPe|DumMa|InFla",
  "tipo_envase": "tipo",
  "tiene_envase_secundario": "Sí|No",
  "razonamiento": "breve explicación basada en web search",
  "riesgo_merma": "Alto|Medio|Bajo",
  "fuente_web": "info clave de la web"
}}"""
        
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            tools=[{
                "type": "web_search_20250305",
                "name": "web_search"
            }],
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )
        
        # Extraer respuesta
        texto = ''
        for block in message.content:
            if block.type == 'text':
                texto += block.text
        
        # Limpiar y parsear JSON
        texto = texto.replace('```json', '').replace('```', '').strip()
        resultado = json.loads(texto)
        
        # Guardar en base de datos
        conn = sqlite3.connect('clasificaciones.db')
        c = conn.cursor()
        c.execute('''
            INSERT INTO productos 
            (producto, fabricante, categoria_salcobrand, tipo_envase, tiene_envase_secundario, 
             razonamiento, riesgo_merma, fuente_web, usuario)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            producto,
            fabricante or 'N/A',
            resultado.get('categoria_salcobrand'),
            resultado.get('tipo_envase'),
            resultado.get('tiene_envase_secundario'),
            resultado.get('razonamiento'),
            resultado.get('riesgo_merma'),
            resultado.get('fuente_web'),
            'usuario'
        ))
        conn.commit()
        conn.close()
        
        return jsonify({
            'producto': producto,
            'fabricante': fabricante or 'N/A',
            **resultado
        })
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/productos', methods=['GET'])
def obtener_productos():
    try:
        conn = sqlite3.connect('clasificaciones.db')
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('SELECT * FROM productos ORDER BY fecha_clasificacion DESC LIMIT 1000')
        rows = c.fetchall()
        conn.close()
        
        productos = []
        for row in rows:
            productos.append({
                'id': row['id'],
                'producto': row['producto'],
                'fabricante': row['fabricante'],
                'categoria_salcobrand': row['categoria_salcobrand'],
                'tipo_envase': row['tipo_envase'],
                'tiene_envase_secundario': row['tiene_envase_secundario'],
                'razonamiento': row['razonamiento'],
                'riesgo_merma': row['riesgo_merma'],
                'fuente_web': row['fuente_web'],
                'fecha_clasificacion': row['fecha_clasificacion']
            })
        
        return jsonify(productos)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/limpiar', methods=['DELETE'])
def limpiar_productos():
    try:
        conn = sqlite3.connect('clasificaciones.db')
        c = conn.cursor()
        c.execute('DELETE FROM productos')
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
