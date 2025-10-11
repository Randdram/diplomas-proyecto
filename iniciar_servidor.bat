@echo off
echo ===================================================
echo 🚀 Iniciando Portal Escolar - Diplomas Proyecto
echo ===================================================

REM Activar entorno virtual
call .venv\Scripts\activate.bat

REM Verificar dependencias
echo 🔍 Verificando dependencias...
pip install -r requirements.txt >nul

REM Iniciar servidor
echo ✅ Iniciando servidor Uvicorn...
python -m uvicorn api_verificacion:app --reload

pause
