"""
Sistema web de gestión de tareas.
Contrato técnico y especificación: ver ESPECIFICACION.md.
"""
from datetime import datetime
import os
import re
import sqlite3
from typing import Any, Dict, Optional

from flask import Flask, g, jsonify, render_template, request


def get_db(db_path: str) -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(db_path)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON;")
    return g.db


def init_db(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tareas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo TEXT NOT NULL,
                descripcion TEXT NOT NULL DEFAULT '',
                prioridad TEXT NOT NULL DEFAULT 'media',
                fecha_limite TEXT,
                completada INTEGER NOT NULL DEFAULT 0,
                creada_en TEXT NOT NULL
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def serialize_tarea(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "titulo": row["titulo"],
        "descripcion": row["descripcion"],
        "prioridad": row["prioridad"],
        "fecha_limite": row["fecha_limite"],
        "completada": bool(row["completada"]),
        "creada_en": row["creada_en"],
    }


def validate_fecha(fecha_str: str) -> Optional[str]:
    """Valida formato AAAA-MM-DD, fecha real del calendario y no anterior a hoy."""
    if not isinstance(fecha_str, str) or isinstance(fecha_str, bool):
        return "La fecha límite debe ser una cadena de texto"
    stripped = fecha_str.strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", stripped):
        return "La fecha límite debe tener el formato AAAA-MM-DD"
    try:
        parsed = datetime.strptime(stripped, "%Y-%m-%d").date()
    except ValueError:
        return "La fecha límite no corresponde a una fecha real del calendario"
    if parsed < datetime.now().date():
        return "La fecha límite no puede ser anterior a la fecha actual"
    return None


def create_app(db_path: str = "tareas.db") -> Flask:
    app = Flask(__name__)
    app.config["DB_PATH"] = db_path

    # Inicializar tablas SQLite según R13 y sección 3
    init_db(db_path)

    @app.teardown_appcontext
    def close_db(error: Optional[BaseException]) -> None:
        db = g.pop("db", None)
        if db is not None:
            db.close()

    # Manejadores de errores para respuestas JSON consistentes en la API (R12)
    @app.errorhandler(400)
    def handle_400(e):
        if request.path.startswith("/api/"):
            desc = getattr(e, "description", "Solicitud inválida")
            return jsonify({"error": desc}), 400
        return e

    @app.errorhandler(404)
    def handle_404(e):
        if request.path.startswith("/api/"):
            desc = getattr(e, "description", "Recurso no encontrado")
            return jsonify({"error": desc}), 404
        return e

    @app.errorhandler(405)
    def handle_405(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Método no permitido"}), 405
        return e

    @app.errorhandler(409)
    def handle_409(e):
        if request.path.startswith("/api/"):
            desc = getattr(e, "description", "Conflicto")
            return jsonify({"error": desc}), 409
        return e

    # R14: Página web en /
    @app.route("/", methods=["GET"])
    def index():
        return render_template("index.html")

    # R1: Crear una tarea
    @app.route("/api/tareas", methods=["POST"])
    def crear_tarea():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "El cuerpo debe ser un objeto JSON válido"}), 400

        # R2: Título obligatorio, texto, 3-100 caracteres tras recortar
        if "titulo" not in data:
            return jsonify({"error": "El título es obligatorio"}), 400
        titulo_raw = data["titulo"]
        if not isinstance(titulo_raw, str) or isinstance(titulo_raw, bool):
            return jsonify({"error": "El título debe ser una cadena de texto"}), 400
        titulo = titulo_raw.strip()
        if not (3 <= len(titulo) <= 100):
            return jsonify({"error": "El título debe tener entre 3 y 100 caracteres"}), 400

        # R3: Descripción opcional, por defecto ""
        if "descripcion" not in data or data["descripcion"] is None:
            descripcion = ""
        else:
            desc_raw = data["descripcion"]
            if not isinstance(desc_raw, str) or isinstance(desc_raw, bool):
                return jsonify({"error": "La descripción debe ser una cadena de texto"}), 400
            descripcion = desc_raw.strip()
            if len(descripcion) > 500:
                return jsonify({"error": "La descripción no puede superar los 500 caracteres"}), 400

        # R4: Prioridad opcional, por defecto "media"
        if "prioridad" not in data:
            prioridad = "media"
        else:
            prio_raw = data["prioridad"]
            if prio_raw not in ("alta", "media", "baja") or not isinstance(prio_raw, str):
                return jsonify({"error": "La prioridad debe ser exactamente 'alta', 'media' o 'baja'"}), 400
            prioridad = prio_raw

        # R5: Fecha límite opcional, por defecto null
        if "fecha_limite" not in data or data["fecha_limite"] is None:
            fecha_limite = None
        else:
            err = validate_fecha(data["fecha_limite"])
            if err:
                return jsonify({"error": err}), 400
            fecha_limite = data["fecha_limite"].strip()

        # Asignados por el sistema (se ignoran si el cliente los envía)
        completada = 0
        creada_en = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

        db = get_db(app.config["DB_PATH"])
        cursor = db.cursor()
        cursor.execute(
            """
            INSERT INTO tareas (titulo, descripcion, prioridad, fecha_limite, completada, creada_en)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (titulo, descripcion, prioridad, fecha_limite, completada, creada_en),
        )
        db.commit()
        tarea_id = cursor.lastrowid

        cursor.execute("SELECT * FROM tareas WHERE id = ?", (tarea_id,))
        row = cursor.fetchone()
        return jsonify(serialize_tarea(row)), 201

    # R6 y R7: Listar tareas, buscar y filtrar
    @app.route("/api/tareas", methods=["GET"])
    def listar_tareas():
        q = request.args.get("q")
        estado = request.args.get("estado")

        # R7: Validar parámetro estado si está presente
        if estado is not None and estado not in ("pendiente", "completada"):
            return jsonify({"error": "El parámetro estado debe ser 'pendiente' o 'completada'"}), 400

        db = get_db(app.config["DB_PATH"])
        cursor = db.cursor()
        cursor.execute("SELECT * FROM tareas ORDER BY id ASC")
        rows = cursor.fetchall()
        tareas = [serialize_tarea(r) for r in rows]

        # Filtrar por estado si se especificó
        if estado is not None:
            es_completada = (estado == "completada")
            tareas = [t for t in tareas if t["completada"] == es_completada]

        # Filtrar por q (titulo o descripcion sin distinguir mayúsculas/minúsculas)
        if q is not None:
            q_clean = q.strip()
            if q_clean != "":
                q_lower = q_clean.lower()
                tareas = [
                    t for t in tareas
                    if q_lower in t["titulo"].lower() or q_lower in t["descripcion"].lower()
                ]

        return jsonify(tareas), 200

    # R8: Consultar una tarea
    @app.route("/api/tareas/<id>", methods=["GET"])
    def consultar_tarea(id):
        try:
            tarea_id = int(id)
        except ValueError:
            return jsonify({"error": "Tarea no encontrada"}), 404

        db = get_db(app.config["DB_PATH"])
        cursor = db.cursor()
        cursor.execute("SELECT * FROM tareas WHERE id = ?", (tarea_id,))
        row = cursor.fetchone()
        if row is None:
            return jsonify({"error": "Tarea no encontrada"}), 404

        return jsonify(serialize_tarea(row)), 200

    # R9: Editar una tarea
    @app.route("/api/tareas/<id>", methods=["PUT"])
    def editar_tarea(id):
        try:
            tarea_id = int(id)
        except ValueError:
            return jsonify({"error": "Tarea no encontrada"}), 404

        db = get_db(app.config["DB_PATH"])
        cursor = db.cursor()
        cursor.execute("SELECT * FROM tareas WHERE id = ?", (tarea_id,))
        row = cursor.fetchone()

        # Orden de prioridad de errores (R9): 404 -> 409 -> 400
        if row is None:
            return jsonify({"error": "Tarea no encontrada"}), 404

        if bool(row["completada"]):
            return jsonify({"error": "Una tarea completada no se puede editar"}), 409

        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "El cuerpo debe ser un objeto JSON válido"}), 400

        campos_validos = {"titulo", "descripcion", "prioridad", "fecha_limite"}
        campos_enviados = set(data.keys()) & campos_validos
        if not campos_enviados:
            return jsonify({"error": "Debe enviar al menos uno de los campos editables: titulo, descripcion, prioridad, fecha_limite"}), 400

        updates = []
        params = []

        if "titulo" in data:
            titulo_raw = data["titulo"]
            if not isinstance(titulo_raw, str) or isinstance(titulo_raw, bool):
                return jsonify({"error": "El título debe ser una cadena de texto"}), 400
            titulo = titulo_raw.strip()
            if not (3 <= len(titulo) <= 100):
                return jsonify({"error": "El título debe tener entre 3 y 100 caracteres"}), 400
            updates.append("titulo = ?")
            params.append(titulo)

        if "descripcion" in data:
            desc_raw = data["descripcion"]
            if desc_raw is None:
                descripcion = ""
            elif not isinstance(desc_raw, str) or isinstance(desc_raw, bool):
                return jsonify({"error": "La descripción debe ser una cadena de texto"}), 400
            else:
                descripcion = desc_raw.strip()
                if len(descripcion) > 500:
                    return jsonify({"error": "La descripción no puede superar los 500 caracteres"}), 400
            updates.append("descripcion = ?")
            params.append(descripcion)

        if "prioridad" in data:
            prio_raw = data["prioridad"]
            if prio_raw not in ("alta", "media", "baja") or not isinstance(prio_raw, str):
                return jsonify({"error": "La prioridad debe ser exactamente 'alta', 'media' o 'baja'"}), 400
            updates.append("prioridad = ?")
            params.append(prio_raw)

        if "fecha_limite" in data:
            fl_raw = data["fecha_limite"]
            if fl_raw is None:
                fecha_limite = None
            else:
                err = validate_fecha(fl_raw)
                if err:
                    return jsonify({"error": err}), 400
                fecha_limite = fl_raw.strip()
            updates.append("fecha_limite = ?")
            params.append(fecha_limite)

        params.append(tarea_id)
        sql = f"UPDATE tareas SET {', '.join(updates)} WHERE id = ?"
        cursor.execute(sql, params)
        db.commit()

        cursor.execute("SELECT * FROM tareas WHERE id = ?", (tarea_id,))
        row_actualizada = cursor.fetchone()
        return jsonify(serialize_tarea(row_actualizada)), 200

    # R10: Marcar como completada
    @app.route("/api/tareas/<id>/completar", methods=["POST"])
    def completar_tarea(id):
        try:
            tarea_id = int(id)
        except ValueError:
            return jsonify({"error": "Tarea no encontrada"}), 404

        db = get_db(app.config["DB_PATH"])
        cursor = db.cursor()
        cursor.execute("SELECT * FROM tareas WHERE id = ?", (tarea_id,))
        row = cursor.fetchone()

        if row is None:
            return jsonify({"error": "Tarea no encontrada"}), 404

        if bool(row["completada"]):
            return jsonify({"error": "La tarea ya está completada"}), 409

        cursor.execute("UPDATE tareas SET completada = 1 WHERE id = ?", (tarea_id,))
        db.commit()

        cursor.execute("SELECT * FROM tareas WHERE id = ?", (tarea_id,))
        row_completada = cursor.fetchone()
        return jsonify(serialize_tarea(row_completada)), 200

    # R11: Eliminar una tarea
    @app.route("/api/tareas/<id>", methods=["DELETE"])
    def eliminar_tarea(id):
        try:
            tarea_id = int(id)
        except ValueError:
            return jsonify({"error": "Tarea no encontrada"}), 404

        db = get_db(app.config["DB_PATH"])
        cursor = db.cursor()
        cursor.execute("SELECT * FROM tareas WHERE id = ?", (tarea_id,))
        row = cursor.fetchone()

        if row is None:
            return jsonify({"error": "Tarea no encontrada"}), 404

        cursor.execute("DELETE FROM tareas WHERE id = ?", (tarea_id,))
        db.commit()

        return "", 204

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
