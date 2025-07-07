# models.py
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class Paciente(BaseModel):
    nombre: str
    telefono: str
    correo: Optional[str] = None
    creado_en: datetime = Field(default_factory=datetime.utcnow)

class Cita(BaseModel):
    paciente_id: str
    servicio: str
    fecha: str  # ejemplo: "2025-07-10"
    hora: str   # ejemplo: "10:00"
    estado: str = "pendiente"  # puede ser: pendiente, confirmada, cancelada
    creado_en: datetime = Field(default_factory=datetime.utcnow)
