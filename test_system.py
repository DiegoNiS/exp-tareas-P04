import os
import tempfile
import unittest
from datetime import date, datetime, timedelta
import json
from app import create_app


class TestGestionTareasExhaustivo(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_tareas.db")
        self.app = create_app(self.db_path)
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_r1_crear_tarea_exito_y_campos(self):
        payload = {
            "titulo": "  Comprar pan  ",
            "descripcion": "  Pan integral  ",
            "prioridad": "alta",
            "fecha_limite": (date.today() + timedelta(days=2)).isoformat(),
            "campo_extra": "ignorar",
            "id": 999,
            "completada": True,
            "creada_en": "2020-01-01T00:00:00"
        }
        res = self.client.post("/api/tareas", json=payload)
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertEqual(data["id"], 1)
        self.assertEqual(data["titulo"], "Comprar pan")
        self.assertEqual(data["descripcion"], "Pan integral")
        self.assertEqual(data["prioridad"], "alta")
        self.assertEqual(data["fecha_limite"], (date.today() + timedelta(days=2)).isoformat())
        self.assertFalse(data["completada"])
        self.assertIn("creada_en", data)
        self.assertNotEqual(data["creada_en"], "2020-01-01T00:00:00")
        self.assertEqual(set(data.keys()), {"id", "titulo", "descripcion", "prioridad", "fecha_limite", "completada", "creada_en"})

    def test_r2_titulo(self):
        # Falta título
        res = self.client.post("/api/tareas", json={})
        self.assertEqual(res.status_code, 400)
        self.assertIn("error", res.get_json())

        # No es texto
        for bad_val in (123, True, False, None, [], {}):
            res = self.client.post("/api/tareas", json={"titulo": bad_val})
            self.assertEqual(res.status_code, 400)
            self.assertIn("error", res.get_json())

        # Menor a 3 caracteres tras strip
        res = self.client.post("/api/tareas", json={"titulo": "  ab  "})
        self.assertEqual(res.status_code, 400)
        res = self.client.post("/api/tareas", json={"titulo": "   "})
        self.assertEqual(res.status_code, 400)

        # 3 caracteres
        res = self.client.post("/api/tareas", json={"titulo": " abc "})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.get_json()["titulo"], "abc")

        # 100 caracteres
        t100 = "a" * 100
        res = self.client.post("/api/tareas", json={"titulo": t100})
        self.assertEqual(res.status_code, 201)

        # 101 caracteres
        t101 = "a" * 101
        res = self.client.post("/api/tareas", json={"titulo": t101})
        self.assertEqual(res.status_code, 400)

    def test_r3_descripcion(self):
        # Opcional sin enviar -> ""
        res = self.client.post("/api/tareas", json={"titulo": "Tarea 1"})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.get_json()["descripcion"], "")

        # Opcional null -> ""
        res = self.client.post("/api/tareas", json={"titulo": "Tarea 2", "descripcion": None})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.get_json()["descripcion"], "")

        # No es texto
        for bad_val in (123, True, [], {}):
            res = self.client.post("/api/tareas", json={"titulo": "Tarea 3", "descripcion": bad_val})
            self.assertEqual(res.status_code, 400)

        # 500 caracteres tras strip
        d500 = " " + ("x" * 500) + " "
        res = self.client.post("/api/tareas", json={"titulo": "Tarea 4", "descripcion": d500})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(len(res.get_json()["descripcion"]), 500)

        d501 = "x" * 501
        res = self.client.post("/api/tareas", json={"titulo": "Tarea 5", "descripcion": d501})
        self.assertEqual(res.status_code, 400)

    def test_r4_prioridad(self):
        # Opcional por defecto media
        res = self.client.post("/api/tareas", json={"titulo": "Tarea prio"})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.get_json()["prioridad"], "media")

        # alta, media, baja
        for p in ("alta", "media", "baja"):
            res = self.client.post("/api/tareas", json={"titulo": f"Tarea {p}", "prioridad": p})
            self.assertEqual(res.status_code, 201)
            self.assertEqual(res.get_json()["prioridad"], p)

        # Cualquier otro valor -> 400
        for p in ("Alta", "MEDIA", "bAJAA", "", None, "urgente", 123):
            res = self.client.post("/api/tareas", json={"titulo": "Tarea inv", "prioridad": p})
            self.assertEqual(res.status_code, 400)

    def test_r5_fecha_limite(self):
        # No enviada o null -> null
        res = self.client.post("/api/tareas", json={"titulo": "Tarea sin fecha"})
        self.assertEqual(res.status_code, 201)
        self.assertIsNone(res.get_json()["fecha_limite"])

        res = self.client.post("/api/tareas", json={"titulo": "Tarea null", "fecha_limite": None})
        self.assertEqual(res.status_code, 201)
        self.assertIsNone(res.get_json()["fecha_limite"])

        # Fecha de hoy
        hoy = date.today().isoformat()
        res = self.client.post("/api/tareas", json={"titulo": "Tarea hoy", "fecha_limite": hoy})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.get_json()["fecha_limite"], hoy)

        # Fecha anterior a hoy -> 400
        ayer = (date.today() - timedelta(days=1)).isoformat()
        res = self.client.post("/api/tareas", json={"titulo": "Tarea ayer", "fecha_limite": ayer})
        self.assertEqual(res.status_code, 400)

        # Fecha no real -> 400
        res = self.client.post("/api/tareas", json={"titulo": "Tarea 30 feb", "fecha_limite": "2026-02-30"})
        self.assertEqual(res.status_code, 400)

        # Formato incorrecto -> 400
        res = self.client.post("/api/tareas", json={"titulo": "Tarea mal formato", "fecha_limite": "10/12/2026"})
        self.assertEqual(res.status_code, 400)

    def test_r6_listar_tareas(self):
        res = self.client.get("/api/tareas")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json(), [])

        self.client.post("/api/tareas", json={"titulo": "Primero"})
        self.client.post("/api/tareas", json={"titulo": "Segundo"})

        res = self.client.get("/api/tareas")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["id"], 1)
        self.assertEqual(data[1]["id"], 2)

    def test_r7_buscar_y_filtrar(self):
        t1 = self.client.post("/api/tareas", json={"titulo": "Preparar informe", "descripcion": "Financiero"}).get_json()
        t2 = self.client.post("/api/tareas", json={"titulo": "Comprar leche", "descripcion": "Informe mensual"}).get_json()
        t3 = self.client.post("/api/tareas", json={"titulo": "Lavar auto", "descripcion": "Exterior"}).get_json()

        self.client.post(f"/api/tareas/{t2['id']}/completar")

        # q sin mayúsculas
        res = self.client.get("/api/tareas?q=INFORME")
        self.assertEqual(res.status_code, 200)
        ids = [t["id"] for t in res.get_json()]
        self.assertEqual(ids, [t1["id"], t2["id"]])

        # q con espacios
        res = self.client.get("/api/tareas?q=   ")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.get_json()), 3)

        # estado pendiente
        res = self.client.get("/api/tareas?estado=pendiente")
        self.assertEqual(res.status_code, 200)
        ids = [t["id"] for t in res.get_json()]
        self.assertEqual(ids, [t1["id"], t3["id"]])

        # estado completada
        res = self.client.get("/api/tareas?estado=completada")
        self.assertEqual(res.status_code, 200)
        ids = [t["id"] for t in res.get_json()]
        self.assertEqual(ids, [t2["id"]])

        # combinación q + estado
        res = self.client.get("/api/tareas?q=INFORME&estado=pendiente")
        self.assertEqual(res.status_code, 200)
        ids = [t["id"] for t in res.get_json()]
        self.assertEqual(ids, [t1["id"]])

        # estado inválido
        res = self.client.get("/api/tareas?estado=otro")
        self.assertEqual(res.status_code, 400)
        res = self.client.get("/api/tareas?estado=")
        self.assertEqual(res.status_code, 400)

    def test_r8_consultar_tarea(self):
        t = self.client.post("/api/tareas", json={"titulo": "Consultar"}).get_json()
        res = self.client.get(f"/api/tareas/{t['id']}")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["id"], t["id"])

        res = self.client.get("/api/tareas/9999")
        self.assertEqual(res.status_code, 404)
        self.assertIn("error", res.get_json())

        res = self.client.get("/api/tareas/no-numero")
        self.assertEqual(res.status_code, 404)
        self.assertIn("error", res.get_json())

    def test_r9_editar_tarea(self):
        t = self.client.post("/api/tareas", json={"titulo": "Original", "prioridad": "baja"}).get_json()
        tid = t["id"]

        # Edición válida parcial
        res = self.client.put(f"/api/tareas/{tid}", json={"titulo": "Modificado"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["titulo"], "Modificado")
        self.assertEqual(res.get_json()["prioridad"], "baja")

        # Sin ninguno de los 4 campos
        res = self.client.put(f"/api/tareas/{tid}", json={"extra": 1})
        self.assertEqual(res.status_code, 400)

        # Atómico: campo inválido no modifica nada
        res = self.client.put(f"/api/tareas/{tid}", json={"titulo": "Nuevo Valido", "prioridad": "invalida"})
        self.assertEqual(res.status_code, 400)
        consultada = self.client.get(f"/api/tareas/{tid}").get_json()
        self.assertEqual(consultada["titulo"], "Modificado")

        # Tarea completada responde 409
        self.client.post(f"/api/tareas/{tid}/completar")
        res = self.client.put(f"/api/tareas/{tid}", json={"titulo": "Intentar editar"})
        self.assertEqual(res.status_code, 409)

        # Prioridad de errores: 404 antes que 409 o 400
        res = self.client.put("/api/tareas/9999", json={"titulo": "x"})
        self.assertEqual(res.status_code, 404)

        # 409 antes que 400
        res = self.client.put(f"/api/tareas/{tid}", json={"titulo": "ab"})
        self.assertEqual(res.status_code, 409)

    def test_r10_marcar_como_completada(self):
        t = self.client.post("/api/tareas", json={"titulo": "Completar me"}).get_json()
        tid = t["id"]

        res = self.client.post(f"/api/tareas/{tid}/completar")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()["completada"])

        res = self.client.post(f"/api/tareas/{tid}/completar")
        self.assertEqual(res.status_code, 409)

        res = self.client.post("/api/tareas/9999/completar")
        self.assertEqual(res.status_code, 404)

    def test_r11_eliminar_tarea_y_no_reutilizar_id(self):
        t1 = self.client.post("/api/tareas", json={"titulo": "Tarea 1"}).get_json()
        t2 = self.client.post("/api/tareas", json={"titulo": "Tarea 2"}).get_json()

        res = self.client.delete(f"/api/tareas/{t1['id']}")
        self.assertEqual(res.status_code, 204)
        self.assertEqual(res.data, b"")

        res = self.client.get(f"/api/tareas/{t1['id']}")
        self.assertEqual(res.status_code, 404)

        t3 = self.client.post("/api/tareas", json={"titulo": "Tarea 3"}).get_json()
        self.assertGreater(t3["id"], t2["id"])
        self.assertNotEqual(t3["id"], t1["id"])

        res = self.client.delete("/api/tareas/9999")
        self.assertEqual(res.status_code, 404)

    def test_r12_formato_errores(self):
        # JSON malformado
        res = self.client.post("/api/tareas", data="malformed json{", content_type="application/json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("error", res.get_json())

        # No es un objeto JSON (lista)
        res = self.client.post("/api/tareas", json=["lista"])
        self.assertEqual(res.status_code, 400)
        self.assertIn("error", res.get_json())

        # No es objeto JSON en PUT (creando la tarea primero para que exista)
        t = self.client.post("/api/tareas", json={"titulo": "Para put no json"}).get_json()
        res = self.client.put(f"/api/tareas/{t['id']}", json="cadena")
        self.assertEqual(res.status_code, 400)
        self.assertIn("error", res.get_json())

        # Malformed JSON en PUT
        res = self.client.put(f"/api/tareas/{t['id']}", data="invalid json{", content_type="application/json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("error", res.get_json())

        # Sin body
        res = self.client.post("/api/tareas", data="", content_type="application/json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("error", res.get_json())

    def test_r13_persistencia(self):
        t = self.client.post("/api/tareas", json={"titulo": "Persistente"}).get_json()

        app2 = create_app(self.db_path)
        client2 = app2.test_client()

        res = client2.get(f"/api/tareas/{t['id']}")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["titulo"], "Persistente")

    def test_r14_pagina_web(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("Gestión de Tareas", html)
        self.assertIn("form-crear", html)
        self.assertIn("filtro-q", html)
        self.assertIn("tabla-tareas-body", html)


if __name__ == "__main__":
    unittest.main()
