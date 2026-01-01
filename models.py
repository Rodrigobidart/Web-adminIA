# models.py
import sqlalchemy
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Boolean, JSON, Date, Text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime
import bcrypt

# 1. Configuración del Motor (Usamos SQLite para empezar)
# Cuando subas a la web, cambiaremos esto por la URL de PostgreSQL
DATABASE_URL = "sqlite:///contabilidad.db" 

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# --- DEFINICIÓN DE TABLAS (MODELOS) ---

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, nullable=True)
    hashed_password = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True) # Para controlar la suscripción
    
    # Relación: Un usuario tiene muchas conciliaciones (v1 y v2)
    conciliaciones = relationship("Conciliacion", back_populates="propietario")
    conciliaciones_v2 = relationship("ConciliacionV2", back_populates="propietario")
    reglas_gasto = relationship("ReglaGasto", back_populates="propietario")


    # Métodos de seguridad para la contraseña
    def set_password(self, password):
        # Transforma "1234" en un hash seguro
        p_bytes = password.encode('utf-8')
        salt = bcrypt.gensalt()
        self.hashed_password = bcrypt.hashpw(p_bytes, salt).decode('utf-8')

    def check_password(self, password):
        # Verifica si la contraseña coincide con el hash
        p_bytes = password.encode('utf-8')
        h_bytes = self.hashed_password.encode('utf-8')
        return bcrypt.checkpw(p_bytes, h_bytes)

class Conciliacion(Base):
    __tablename__ = "conciliaciones"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id")) # Vínculo de seguridad
    
    periodo_mes = Column(Integer)
    periodo_anio = Column(Integer)
    fecha_cierre = Column(DateTime, default=datetime.utcnow)
    
    saldo_mayor = Column(Float)
    saldo_banco = Column(Float)
    diferencia = Column(Float)
    estado = Column(String) # "CERRADO OK", "CON DIFERENCIA"
    
    # Aquí guardaremos el DataFrame de la hoja de trabajo convertido a JSON/Dict
    # Esto permite recuperar la conciliación vieja tal cual estaba
    datos_hoja_trabajo = Column(JSON) 
    
    propietario = relationship("User", back_populates="conciliaciones")


# --- NUEVOS MODELOS PARA EL CONCILIADOR V2 ---

class ConciliacionV2(Base):
    """ Almacena una sesión de conciliación completa. """
    __tablename__ = "conciliaciones_v2"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    
    banco_nombre = Column(String, default="Mi Banco")
    periodo = Column(Date)
    
    saldo_inicial_banco = Column(Float, default=0.0)
    saldo_final_banco = Column(Float, default=0.0)
    saldo_inicial_mayor = Column(Float, default=0.0)
    saldo_final_mayor = Column(Float, default=0.0)
    
    estado = Column(String, default="en_progreso") # en_progreso, completada
    fecha_creacion = Column(DateTime, default=datetime.utcnow)
    
    propietario = relationship("User", back_populates="conciliaciones_v2")
    movimientos_banco = relationship("MovimientoBanco", back_populates="conciliacion", cascade="all, delete-orphan")
    movimientos_contables = relationship("MovimientoContable", back_populates="conciliacion", cascade="all, delete-orphan")

class MovimientoBanco(Base):
    """ Almacena una línea individual del extracto bancario. """
    __tablename__ = "movimientos_banco"
    id = Column(Integer, primary_key=True, index=True)
    conciliacion_id = Column(Integer, ForeignKey("conciliaciones_v2.id"))
    
    fecha = Column(Date)
    descripcion = Column(Text)
    monto = Column(Float)
    
    estado = Column(String, default="pendiente") # pendiente, conciliado_auto, conciliado_manual
    match_id = Column(Integer, nullable=True) # ID del movimiento contable con el que se corresponde
    
    conciliacion = relationship("ConciliacionV2", back_populates="movimientos_banco")

class MovimientoContable(Base):
    """ Almacena una línea individual del mayor contable. """
    __tablename__ = "movimientos_contable"
    id = Column(Integer, primary_key=True, index=True)
    conciliacion_id = Column(Integer, ForeignKey("conciliaciones_v2.id"))
    
    fecha = Column(Date)
    descripcion = Column(Text)
    monto = Column(Float)
    
    estado = Column(String, default="pendiente") # pendiente, conciliado_auto, conciliado_manual
    match_id = Column(Integer, nullable=True) # ID del movimiento de banco con el que se corresponde
    
    conciliacion = relationship("ConciliacionV2", back_populates="movimientos_contables")

class ReglaGasto(Base):
    """ Almacena reglas definidas por el usuario para auto-categorizar gastos. """
    __tablename__ = "reglas_gasto"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    
    texto_a_buscar = Column(String, unique=True, index=True)
    categoria_asignada = Column(String, default="Gasto Bancario")
    
    propietario = relationship("User", back_populates="reglas_gasto")


# --- FUNCIÓN PARA CREAR LA BASE DE DATOS ---
def init_db():
    Base.metadata.create_all(bind=engine)
    print("Base de datos creada/actualizada exitosamente.")

if __name__ == "__main__":
    init_db()
    # Crear un usuario de prueba
    db = SessionLocal()
    if not db.query(User).filter_by(username="admin").first():
        nuevo_usuario = User(username="admin", email="admin@estudio.com")
        nuevo_usuario.set_password("admin123")
        db.add(nuevo_usuario)
        db.commit()
        print("Usuario admin creado.")
    db.close()