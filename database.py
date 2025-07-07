from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017")
db = client["consultorio"]
citas_collection = db["citas"]
historial_collection = db["historial_pacientes"]
encuestas_collection = db["encuestas_satisfaccion"]
